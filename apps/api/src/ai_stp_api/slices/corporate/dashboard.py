"""Bounded Corporate Hub health queries over canonical operational records."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from sqlalchemy import and_, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.dashboard import (
    CiReason,
    CiStatus,
    CorporateCiCheckRequest,
    CorporateCiCheckView,
    DashboardCell,
    DashboardQuery,
    DashboardQueryRequest,
    DashboardResult,
    DashboardScope,
    DashboardView,
    DashboardViewList,
    DashboardViewRequest,
)
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp, parse_timestamp
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.dashboard_models import CorporateCiCheck, CorporateDashboardView
from ai_stp_platform.heartbeat_models import InstallationHeartbeat
from ai_stp_platform.heartbeat_service import DEFAULT_STALE_AFTER, evaluate_health
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateTeam,
    CorporateTeamMember,
    OrganizationMembership,
)
from ai_stp_platform.telemetry_policy_models import TelemetryEvent
from ai_stp_platform.telemetry_privacy_service import record_privileged_access

router = APIRouter(tags=["corporate"])
_MAX_SOURCE_ROWS = 1000
_DATASET_DIMENSIONS = {
    "ci": frozenset(
        {
            "state",
            "project",
            "team",
            "account",
            "device",
            "harness",
            "setup",
            "day",
            "checked_at",
            "reason",
        }
    ),
    "heartbeat": frozenset({"state", "team", "account", "device", "day", "checked_at"}),
    "provider": frozenset(
        {"state", "team", "account", "device", "harness", "provider", "day", "checked_at"}
    ),
}


def _ts(value: datetime) -> str:
    return format_timestamp(value if value.tzinfo else value.replace(tzinfo=UTC))


def _ci_view(row: CorporateCiCheck) -> CorporateCiCheckView:
    return CorporateCiCheckView(
        organization_id=row.organization_id,
        project_id=row.project_id,
        account_id=row.account_id,
        device_id=row.device_id,
        harness=row.harness,
        setup_id=row.setup_id,
        status=cast(CiStatus, row.status),
        reason=cast(CiReason, row.reason),
        checked_at=_ts(row.checked_at),
        received_at=_ts(row.received_at),
        revision=row.revision,
    )


@router.put(
    "/corporate/organizations/{organization_id}/dashboard/ci-check",
    response_model=CorporateCiCheckView,
)
async def write_ci_check(
    organization_id: OrganizationId,
    payload: CorporateCiCheckRequest,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CorporateCiCheckView:
    await service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.read",
        scope_kind="project",
        scope_id=payload.project_id,
    )
    if ctx.device_id != payload.device_id or ctx.account_id != payload.account_id:
        raise ApiError(ErrorCategory.PERMISSION, "CI check must be bound to the session device")
    project = await db.scalar(
        select(CorporateProject).where(
            CorporateProject.organization_id == organization_id,
            CorporateProject.id == payload.project_id,
            CorporateProject.state == "active",
        )
    )
    if project is None:
        raise ApiError(ErrorCategory.PERMISSION, "project access denied")
    now = datetime.now(UTC)
    checked_at = parse_timestamp(payload.checked_at)
    if checked_at > now + timedelta(minutes=5):
        raise ApiError(ErrorCategory.VALIDATION, "CI check time is beyond accepted skew")
    row = await db.get(
        CorporateCiCheck,
        (organization_id, payload.project_id, payload.device_id, payload.harness),
        with_for_update=True,
    )
    if row is None:
        row = CorporateCiCheck(
            organization_id=organization_id,
            project_id=payload.project_id,
            account_id=payload.account_id,
            device_id=payload.device_id,
            harness=payload.harness,
            setup_id=payload.setup_id,
            status=payload.status,
            reason=payload.reason,
            checked_at=checked_at,
            received_at=now,
            revision=1,
        )
        db.add(row)
    elif checked_at > (
        row.checked_at if row.checked_at.tzinfo else row.checked_at.replace(tzinfo=UTC)
    ):
        row.setup_id = payload.setup_id
        row.status = payload.status
        row.reason = payload.reason
        row.checked_at = checked_at
        row.received_at = now
        row.revision += 1
    await db.flush()
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="dashboard.ci_check.write",
        target_table="corporate_ci_check",
        target_id=payload.project_id,
        payload={"revision": row.revision},
    )
    await db.commit()
    return _ci_view(row)


def _validate_query(query: DashboardQuery, *, diagnostics: bool) -> list[str]:
    selected = list(
        dict.fromkeys([*query.dimensions, *query.group_by, *query.pivot_rows, *query.pivot_columns])
    )
    if len(selected) > 8 or any(
        dimension not in _DATASET_DIMENSIONS[query.dataset]
        for dimension in [*selected, *(item.dimension for item in query.filters)]
    ):
        raise ApiError(ErrorCategory.VALIDATION, "dashboard dimension is unavailable")
    if len(set(query.measures)) != len(query.measures):
        raise ApiError(ErrorCategory.VALIDATION, "dashboard measures must be distinct")
    if "projects" in query.measures and query.dataset != "ci":
        raise ApiError(ErrorCategory.VALIDATION, "project measure is unavailable")
    if query.sort_by not in {*selected, *query.measures}:
        raise ApiError(ErrorCategory.VALIDATION, "dashboard sort must be selected")
    if (
        "reason" in selected or any(item.dimension == "reason" for item in query.filters)
    ) and not diagnostics:
        raise ApiError(ErrorCategory.PERMISSION, "diagnostic access denied")
    if query.view == "line" and "day" not in selected:
        raise ApiError(ErrorCategory.VALIDATION, "line view requires day")
    if query.view == "heatmap" and len(selected) != 2:
        raise ApiError(ErrorCategory.VALIDATION, "heatmap requires two dimensions")
    if query.view == "pie" and len(selected) != 1:
        raise ApiError(ErrorCategory.VALIDATION, "pie view requires one dimension")
    return selected


async def _visible_accounts(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, superadmin: bool
) -> tuple[set[str], dict[str, list[str]]]:
    memberships = list(
        (
            await db.scalars(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.state == "active",
                )
            )
        ).all()
    )
    team_rows = cast(
        list[tuple[str, str]],
        (
            await db.execute(
                select(CorporateTeamMember.account_id, CorporateTeamMember.team_id)
                .join(
                    CorporateTeam,
                    (CorporateTeam.organization_id == CorporateTeamMember.organization_id)
                    & (CorporateTeam.id == CorporateTeamMember.team_id),
                )
                .where(
                    CorporateTeamMember.organization_id == organization_id,
                    CorporateTeam.state == "active",
                )
            )
        ).all(),
    )
    team_ids = sorted({team_id for _, team_id in team_rows})
    allowed_teams: set[str] = set(team_ids) if superadmin else set()
    if not superadmin:
        for team_id in team_ids:
            if await has_corporate_permission(
                db,
                organization_id=organization_id,
                principal_type="user",
                principal_id=ctx.account_id,
                permission="team.read",
                scope_kind="team",
                scope_id=team_id,
            ):
                allowed_teams.add(team_id)
    teams_by_account: dict[str, list[str]] = defaultdict(list)
    for account_id, team_id in team_rows:
        if team_id in allowed_teams:
            teams_by_account[account_id].append(team_id)
    allowed_accounts: set[str] = set()
    for membership in memberships:
        if superadmin or (
            membership.account_id in teams_by_account
            and await has_corporate_permission(
                db,
                organization_id=organization_id,
                principal_type="user",
                principal_id=ctx.account_id,
                permission="telemetry.read",
                scope_kind="member",
                scope_id=membership.account_id,
            )
        ):
            allowed_accounts.add(membership.account_id)
    return allowed_accounts, teams_by_account


async def _source_rows(
    db: AsyncSession,
    *,
    organization_id: str,
    query: DashboardQuery,
    now: datetime,
    account_ids: set[str],
) -> list[dict[str, str]]:
    if not account_ids:
        return []
    if query.dataset == "ci":
        rows = list(
            (
                await db.scalars(
                    select(CorporateCiCheck)
                    .where(
                        CorporateCiCheck.organization_id == organization_id,
                        CorporateCiCheck.account_id.in_(account_ids),
                    )
                    .limit(_MAX_SOURCE_ROWS + 1)
                )
            ).all()
        )
        if len(rows) > _MAX_SOURCE_ROWS:
            raise ApiError(ErrorCategory.VALIDATION, "dashboard query exceeds source row limit")
        return [
            {
                "state": row.status,
                "project": row.project_id,
                "account": row.account_id,
                "device": row.device_id,
                "harness": row.harness,
                "setup": row.setup_id or "",
                "day": _ts(row.checked_at)[:10],
                "checked_at": _ts(row.checked_at),
                "reason": row.reason,
            }
            for row in rows
        ]
    if query.dataset == "heartbeat":
        beats = list(
            (
                await db.scalars(
                    select(InstallationHeartbeat)
                    .where(
                        InstallationHeartbeat.organization_id == organization_id,
                        InstallationHeartbeat.account_id.in_(account_ids),
                    )
                    .limit(_MAX_SOURCE_ROWS + 1)
                )
            ).all()
        )
        if len(beats) > _MAX_SOURCE_ROWS:
            raise ApiError(ErrorCategory.VALIDATION, "dashboard query exceeds source row limit")
        return [
            {
                "state": evaluate_health(
                    row.reported_state, row.received_at, now=now, stale_after=DEFAULT_STALE_AFTER
                ),
                "account": row.account_id,
                "device": row.device_id,
                "day": _ts(row.checked_at)[:10],
                "checked_at": _ts(row.checked_at),
            }
            for row in beats
        ]
    events = list(
        (
            await db.scalars(
                select(TelemetryEvent)
                .where(
                    TelemetryEvent.organization_id == organization_id,
                    TelemetryEvent.kind == "heartbeat",
                    TelemetryEvent.provider_name.is_not(None),
                    TelemetryEvent.subject_state == "active",
                    TelemetryEvent.account_id.in_(account_ids),
                    TelemetryEvent.occurred_at >= now - timedelta(days=90),
                )
                .order_by(TelemetryEvent.occurred_at.desc())
                .limit(_MAX_SOURCE_ROWS + 1)
            )
        ).all()
    )
    if len(events) > _MAX_SOURCE_ROWS:
        raise ApiError(ErrorCategory.VALIDATION, "dashboard query exceeds source row limit")
    latest: dict[tuple[str | None, str | None, str, str], TelemetryEvent] = {}
    for row in events:
        key = (row.account_id, row.device_id, row.harness, row.provider_name or "")
        latest.setdefault(key, row)
    return [
        {
            "state": (
                "stale"
                if now
                - (
                    row.received_at
                    if row.received_at.tzinfo
                    else row.received_at.replace(tzinfo=UTC)
                )
                > DEFAULT_STALE_AFTER
                and row.health != "disabled"
                else row.health or "unknown"
            ),
            "account": row.account_id or "",
            "device": row.device_id or "",
            "harness": row.harness,
            "provider": row.provider_name or "",
            "day": _ts(row.occurred_at)[:10],
            "checked_at": _ts(row.occurred_at),
        }
        for row in latest.values()
    ]


@router.post(
    "/corporate/organizations/{organization_id}/dashboard/query",
    response_model=DashboardResult,
)
async def query_dashboard(
    organization_id: OrganizationId,
    payload: DashboardQueryRequest,
    request: Request,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardResult:
    _, membership = await service.organization_and_membership(
        db, ctx=ctx, organization_id=organization_id
    )
    if membership.role not in {"lead", "superadmin"}:
        raise ApiError(ErrorCategory.PERMISSION, "dashboard access denied")
    superadmin = membership.role == "superadmin"
    if superadmin:
        await service.authorize(
            db, ctx=ctx, organization_id=organization_id, permission="telemetry.read"
        )
    diagnostics = await has_corporate_permission(
        db,
        organization_id=organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        permission="audit.read",
    )
    selected = _validate_query(payload.query, diagnostics=diagnostics)
    account_ids, teams_by_account = await _visible_accounts(
        db, ctx=ctx, organization_id=organization_id, superadmin=superadmin
    )
    now = datetime.now(UTC)
    rows = await _source_rows(
        db,
        organization_id=organization_id,
        query=payload.query,
        now=now,
        account_ids=account_ids,
    )
    # Project visibility is checked after the bounded read and before filtering or aggregation.
    if payload.query.dataset == "ci" and not superadmin:
        visible_projects: dict[str, bool] = {}
        for project_id in {row["project"] for row in rows}:
            visible_projects[project_id] = await has_corporate_permission(
                db,
                organization_id=organization_id,
                principal_type="user",
                principal_id=ctx.account_id,
                permission="project.read",
                scope_kind="project",
                scope_id=project_id,
            )
        rows = [row for row in rows if visible_projects[row["project"]]]
    expanded: list[dict[str, str]] = []
    for row in rows:
        teams = sorted(teams_by_account.get(row["account"], []))
        if "team" in selected or any(item.dimension == "team" for item in payload.query.filters):
            expanded.extend({**row, "team": team_id} for team_id in teams)
        else:
            expanded.append(row)
    if len(expanded) * max(1, len(selected)) > 5000:
        raise ApiError(ErrorCategory.VALIDATION, "dashboard query exceeds cost limit")
    filtered = [
        row
        for row in expanded
        if all(row.get(item.dimension, "") in item.values for item in payload.query.filters)
    ]
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in filtered:
        grouped[tuple(row.get(dimension, "") for dimension in selected)].append(row)
    items = [
        DashboardCell(
            dimensions=dict(zip(selected, key, strict=True)),
            measures={
                measure: (
                    len(group)
                    if measure == "count"
                    else len({row["device"] for row in group})
                    if measure == "devices"
                    else len({row["project"] for row in group})
                )
                for measure in payload.query.measures
            },
        )
        for key, group in grouped.items()
    ]
    sort_by = payload.query.sort_by
    items.sort(
        key=lambda item: (
            item.measures.get(sort_by, 0)
            if sort_by in item.measures
            else item.dimensions.get(sort_by, ""),
            tuple(item.dimensions.values()),
        ),
        reverse=payload.query.sort_order == "desc",
    )
    result = DashboardResult(
        organization_id=organization_id,
        query=payload.query,
        evaluated_at=_ts(now),
        total_source_rows=len(filtered),
        total_groups=len(items),
        items=items[: payload.query.limit],
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="dashboard.query",
        target_table="corporate_dashboard_view",
        target_id=organization_id,
        request_id=getattr(request.state, "request_id", None),
        payload={"dataset": payload.query.dataset, "returned": len(result.items)},
    )
    await record_privileged_access(
        db,
        organization_id=organization_id,
        actor_account_id=ctx.account_id,
        action="telemetry.aggregate",
        target_table=(
            "telemetry_event"
            if payload.query.dataset == "provider"
            else "installation_heartbeat"
            if payload.query.dataset == "heartbeat"
            else "corporate_ci_check"
        ),
        target_id=organization_id,
        request_id=getattr(request.state, "request_id", None),
        detail={"dataset": payload.query.dataset, "returned": len(result.items)},
    )
    await db.commit()
    return result


def _saved_view(row: CorporateDashboardView) -> DashboardView:
    return DashboardView(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        scope=cast(DashboardScope, row.scope),
        scope_id=row.scope_id,
        owner_account_id=row.owner_account_id,
        query=DashboardQuery.model_validate(row.query),
        revision=row.revision,
    )


async def _view_scope_allowed(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    role: str,
    scope: str,
    scope_id: str,
    manage: bool,
) -> bool:
    if scope == "user":
        return scope_id == ctx.account_id
    if scope == "organization":
        return role == "superadmin" and scope_id == organization_id
    if scope != "team":
        return False
    team = await db.scalar(
        select(CorporateTeam).where(
            CorporateTeam.organization_id == organization_id,
            CorporateTeam.id == scope_id,
            CorporateTeam.state == "active",
        )
    )
    if team is None:
        return False
    if role == "superadmin":
        return True
    if not await has_corporate_permission(
        db,
        organization_id=organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        permission="team.read",
        scope_kind="team",
        scope_id=scope_id,
    ):
        return False
    member = await db.get(CorporateTeamMember, (organization_id, scope_id, ctx.account_id))
    return member is not None and (not manage or member.role == "lead")


async def _view_context(db: AsyncSession, *, ctx: AuthContext, organization_id: str) -> str:
    _, membership = await service.organization_and_membership(
        db, ctx=ctx, organization_id=organization_id
    )
    if membership.role not in {"lead", "superadmin"}:
        raise ApiError(ErrorCategory.PERMISSION, "dashboard access denied")
    return membership.role


@router.get(
    "/corporate/organizations/{organization_id}/dashboard/views",
    response_model=DashboardViewList,
)
async def list_views(
    organization_id: OrganizationId,
    request: Request,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardViewList:
    role = await _view_context(db, ctx=ctx, organization_id=organization_id)
    team_ids = (
        select(CorporateTeam.id).where(CorporateTeam.organization_id == organization_id)
        if role == "superadmin"
        else select(CorporateTeamMember.team_id).where(
            CorporateTeamMember.organization_id == organization_id,
            CorporateTeamMember.account_id == ctx.account_id,
        )
    )
    rows = list(
        (
            await db.scalars(
                select(CorporateDashboardView)
                .where(
                    CorporateDashboardView.organization_id == organization_id,
                    or_(
                        and_(
                            CorporateDashboardView.scope == "user",
                            CorporateDashboardView.scope_id == ctx.account_id,
                        ),
                        and_(
                            CorporateDashboardView.scope == "team",
                            CorporateDashboardView.scope_id.in_(team_ids),
                        ),
                        and_(
                            CorporateDashboardView.scope == "organization",
                            CorporateDashboardView.scope_id == organization_id,
                            literal(role == "superadmin"),
                        ),
                    ),
                )
                .order_by(CorporateDashboardView.created_at.desc())
                .limit(201)
            )
        ).all()
    )
    if len(rows) > 200:
        raise ApiError(ErrorCategory.VALIDATION, "dashboard view list exceeds limit")
    items = [
        _saved_view(row)
        for row in rows
        if await _view_scope_allowed(
            db,
            ctx=ctx,
            organization_id=organization_id,
            role=role,
            scope=row.scope,
            scope_id=row.scope_id,
            manage=False,
        )
    ]
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="dashboard.views.list",
        target_table="corporate_dashboard_view",
        target_id=organization_id,
        request_id=getattr(request.state, "request_id", None),
        payload={"returned": len(items)},
    )
    await db.commit()
    return DashboardViewList(organization_id=organization_id, items=items)


@router.post(
    "/corporate/organizations/{organization_id}/dashboard/views",
    response_model=DashboardView,
)
async def create_view(
    organization_id: OrganizationId,
    payload: DashboardViewRequest,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardView:
    role = await _view_context(db, ctx=ctx, organization_id=organization_id)
    fingerprint = service.mutation_fingerprint(
        payload.model_dump(mode="json", exclude={"idempotency_key"})
    )
    _, receipt = await service.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="telemetry.read",
        scope_kind="member" if role == "lead" else "organization",
        scope_id=ctx.account_id if role == "lead" else organization_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="dashboard.view.create",
        fingerprint=fingerprint,
    )
    if receipt is not None:
        await db.commit()
        return DashboardView.model_validate(receipt.response_body)
    if payload.expected_revision != 0 or not await _view_scope_allowed(
        db,
        ctx=ctx,
        organization_id=organization_id,
        role=role,
        scope=payload.scope,
        scope_id=payload.scope_id,
        manage=True,
    ):
        raise ApiError(ErrorCategory.PERMISSION, "dashboard view scope denied")
    diagnostics = await has_corporate_permission(
        db,
        organization_id=organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        permission="audit.read",
    )
    _validate_query(payload.query, diagnostics=diagnostics)
    row = CorporateDashboardView(
        id=new_id("dashboard_view"),
        organization_id=organization_id,
        scope=payload.scope,
        scope_id=payload.scope_id,
        owner_account_id=ctx.account_id,
        name=payload.name.strip(),
        query=payload.query.model_dump(mode="json"),
        revision=1,
    )
    if not row.name:
        raise ApiError(ErrorCategory.VALIDATION, "dashboard view name is empty")
    db.add(row)
    await db.flush()
    view = _saved_view(row)
    await service.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="dashboard.view.create",
        fingerprint=fingerprint,
        response=view,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="dashboard.view.create",
        target_table="corporate_dashboard_view",
        target_id=row.id,
        payload={"scope": row.scope},
    )
    await db.commit()
    return view


@router.put(
    "/corporate/organizations/{organization_id}/dashboard/views/{view_id}",
    response_model=DashboardView,
)
async def update_view(
    organization_id: OrganizationId,
    view_id: str,
    payload: DashboardViewRequest,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardView:
    role = await _view_context(db, ctx=ctx, organization_id=organization_id)
    fingerprint = service.mutation_fingerprint(
        {
            "view_id": view_id,
            **payload.model_dump(mode="json", exclude={"idempotency_key"}),
        }
    )
    _, receipt = await service.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="telemetry.read",
        scope_kind="member" if role == "lead" else "organization",
        scope_id=ctx.account_id if role == "lead" else organization_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="dashboard.view.update",
        fingerprint=fingerprint,
    )
    if receipt is not None:
        await db.commit()
        return DashboardView.model_validate(receipt.response_body)
    row = await db.scalar(
        select(CorporateDashboardView).where(
            CorporateDashboardView.organization_id == organization_id,
            CorporateDashboardView.id == view_id,
        )
    )
    if row is None or not await _view_scope_allowed(
        db,
        ctx=ctx,
        organization_id=organization_id,
        role=role,
        scope=row.scope,
        scope_id=row.scope_id,
        manage=True,
    ):
        raise ApiError(ErrorCategory.PERMISSION, "dashboard view access denied")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "dashboard view changed")
    if row.scope != payload.scope or row.scope_id != payload.scope_id:
        raise ApiError(ErrorCategory.VALIDATION, "dashboard view scope is immutable")
    diagnostics = await has_corporate_permission(
        db,
        organization_id=organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        permission="audit.read",
    )
    _validate_query(payload.query, diagnostics=diagnostics)
    name = payload.name.strip()
    if not name:
        raise ApiError(ErrorCategory.VALIDATION, "dashboard view name is empty")
    row.name = name
    row.query = payload.query.model_dump(mode="json")
    row.revision += 1
    await db.flush()
    view = _saved_view(row)
    await service.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="dashboard.view.update",
        fingerprint=fingerprint,
        response=view,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="dashboard.view.update",
        target_table="corporate_dashboard_view",
        target_id=row.id,
        payload={"revision": row.revision},
    )
    await db.commit()
    return view
