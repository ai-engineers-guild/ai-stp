"""Operational catalog assignments never mutate grants or harness state."""

from collections.abc import Sequence
from typing import Literal, cast

from sqlalchemy import and_, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_contracts.corporate import (
    AssignmentSelector,
    AssignmentState,
    AssignmentSubjectKind,
    CorporateAssignmentPlan,
    CorporateAssignmentPlanItem,
    CorporateAssignmentPlanRequest,
    CorporateCatalogAssignment,
    CorporateCatalogAssignmentList,
    CorporateCatalogAssignmentQuery,
    CorporateCatalogAssignmentRequest,
    CorporateCatalogUsage,
    CorporateCatalogUsageList,
    CorporateCatalogUsageQuery,
    CorporateDistributionCounts,
    CorporateDistributionExclusion,
    CorporateDistributionRequest,
    CorporateDistributionResult,
    CorporateDistributionState,
    CorporateDistributionStateList,
    CorporateDistributionStateQuery,
    CorporateDistributionTargetResult,
    CorporateEffectiveAssignment,
    CorporateEffectiveAssignmentCandidate,
    CorporateEffectiveAssignmentQuery,
    CorporatePlanMaterializedItem,
    DistributionLifecycle,
    DistributionTargetKind,
    DistributionTargetResult,
    PlanAction,
    PlanOutcome,
)
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.versioning import parse_version
from ai_stp_platform.catalog_read import get_visible_metadata, get_visible_object_versions
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateAssignmentDistribution as DistributionRow,
)
from ai_stp_platform.organization_models import (
    CorporateCatalogAssignment as AssignmentRow,
)
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateProjectMember,
    CorporateTeam,
    CorporateTeamMember,
    OrganizationMembership,
)
from ai_stp_platform.technology_models import (
    ProjectTeamRelation,
    ProjectTechnologyRelation,
    Technology,
    TechnologyTeamResponsibility,
)

UsageSubjectKind = Literal["employee", "team", "project", "technology"]

#: Deterministic effective-assignment precedence (ADR-0194): the lower the
#: rank, the stronger the scope. An explicit employee decision always outranks
#: every inherited assignment.
_SCOPE_RANK: dict[str, int] = {
    "employee": 0,
    "project": 1,
    "technology": 2,
    "team": 3,
    "organization": 4,
}

#: A latest assignment resolves to the same lifecycle an exact selector accepts.
_ELIGIBLE_LIFECYCLES: frozenset[str] = frozenset({"active", "deprecated"})


def _subject_column(kind: AssignmentSubjectKind) -> InstrumentedAttribute[str | None] | None:
    return {
        "employee": AssignmentRow.account_id,
        "team": AssignmentRow.team_id,
        "project": AssignmentRow.project_id,
        "technology": AssignmentRow.technology_id,
    }.get(kind)


def _row_scope(row: AssignmentRow) -> tuple[AssignmentSubjectKind, str]:
    for kind, identity in (
        ("employee", row.account_id),
        ("team", row.team_id),
        ("project", row.project_id),
        ("technology", row.technology_id),
    ):
        if identity is not None:
            return cast(AssignmentSubjectKind, kind), identity
    return "organization", row.organization_id


def _version_key(version: str) -> tuple[int, int]:
    major, minor = parse_version(version)
    return major, minor


async def _eligible_versions(
    db: AsyncSession,
    *,
    object_kind: Literal["setup", "component"],
    stable_id: str,
    account_id: str | None,
) -> list[tuple[str, str]]:
    rows = await get_visible_object_versions(
        db, object_kind=object_kind, stable_id=stable_id, account_id=account_id
    )
    eligible = [
        (row.version, row.passport_digest) for row in rows if row.lifecycle in _ELIGIBLE_LIFECYCLES
    ]
    eligible.sort(key=lambda item: _version_key(item[0]))
    return eligible


async def _check_selector(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    payload: CorporateCatalogAssignmentRequest,
) -> str | None:
    """Validate the selector and return the pinned digest for an exact write."""
    if payload.selector == "latest":
        eligible = await _eligible_versions(
            db,
            object_kind=payload.object_kind,
            stable_id=payload.stable_id,
            account_id=ctx.account_id,
        )
        if not eligible:
            raise ApiError(ErrorCategory.PERMISSION, "catalog line is unavailable")
        return None
    assert payload.version is not None
    catalog = await get_visible_metadata(
        db,
        object_kind=payload.object_kind,
        stable_id=payload.stable_id,
        version=payload.version,
        account_id=ctx.account_id,
    )
    if (
        catalog is None
        or catalog.published_at is None
        or catalog.lifecycle_state not in _ELIGIBLE_LIFECYCLES
    ):
        raise ApiError(ErrorCategory.PERMISSION, "catalog version is unavailable")
    if payload.passport_digest is not None and payload.passport_digest != catalog.passport_digest:
        raise ApiError(ErrorCategory.VALIDATION, "digest does not match the published coordinate")
    return catalog.passport_digest


async def write_assignment(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateCatalogAssignmentRequest,
    request_id: str | None,
) -> CorporateCatalogAssignment:
    kind = payload.subject_kind
    scope_kind = kind if kind in {"team", "project", "technology"} else "organization"
    scope_id = payload.subject_id if kind in {"team", "project", "technology"} else organization_id
    permission = {
        "employee": "member.manage",
        "organization": "organization.manage",
    }.get(kind, f"{kind}.update")
    fingerprint = service.mutation_fingerprint(
        payload.model_dump(mode="json", exclude={"idempotency_key"})
    )
    _, receipt = await service.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=permission,
        scope_kind=scope_kind,
        scope_id=scope_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="catalog_assignment.write",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    # Revalidate catalog access even on replay; a receipt is not an access grant.
    pinned_digest = await _check_selector(db, ctx=ctx, payload=payload)
    if receipt is not None:
        return CorporateCatalogAssignment.model_validate(receipt.response_body)
    if kind == "organization":
        subject_active = payload.subject_id == organization_id
        subject = object() if subject_active else None
    else:
        model = {
            "employee": OrganizationMembership,
            "team": CorporateTeam,
            "project": CorporateProject,
            "technology": Technology,
        }[kind]
        identity = OrganizationMembership.account_id if kind == "employee" else model.id
        subject = await db.scalar(
            select(model).where(
                model.organization_id == organization_id, identity == payload.subject_id
            )
        )
        subject_active = subject is not None and (
            getattr(subject, "state", None) == "active"
            or getattr(subject, "lifecycle", None) in {"active", "deprecated"}
        )
    if subject is None or (payload.state == "current" and not subject_active):
        raise ApiError(ErrorCategory.PERMISSION, "assignment subject is unavailable")
    column = _subject_column(kind)
    predicates = [
        AssignmentRow.organization_id == organization_id,
        AssignmentRow.object_kind == payload.object_kind,
        AssignmentRow.stable_id == payload.stable_id,
    ]
    if column is None:
        predicates.extend(
            (
                AssignmentRow.account_id.is_(None),
                AssignmentRow.team_id.is_(None),
                AssignmentRow.project_id.is_(None),
                AssignmentRow.technology_id.is_(None),
            )
        )
    else:
        predicates.append(column == payload.subject_id)
    if payload.version is None:
        predicates.append(AssignmentRow.version.is_(None))
    else:
        predicates.append(AssignmentRow.version == payload.version)
    if payload.harness is None:
        predicates.append(AssignmentRow.harness.is_(None))
    else:
        predicates.append(AssignmentRow.harness == payload.harness)
    row = await db.scalar(select(AssignmentRow).where(*predicates))
    if (row.revision if row else 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "assignment revision is stale")
    if row is None:
        row = AssignmentRow(
            id=new_id("operation"),
            organization_id=organization_id,
            object_kind=payload.object_kind,
            stable_id=payload.stable_id,
            selector=payload.selector,
            version=payload.version,
            passport_digest=pinned_digest,
            harness=payload.harness,
            state=payload.state,
            revision=1,
        )
        if kind != "organization":
            setattr(
                row,
                {
                    "employee": "account_id",
                    "team": "team_id",
                    "project": "project_id",
                    "technology": "technology_id",
                }[kind],
                payload.subject_id,
            )
        db.add(row)
    else:
        row.state = payload.state
        row.revision += 1
    await db.flush()
    response = CorporateCatalogAssignment(
        assignment_id=row.id,
        organization_id=organization_id,
        subject_kind=kind,
        subject_id=payload.subject_id,
        object_kind=payload.object_kind,
        stable_id=payload.stable_id,
        selector=cast(AssignmentSelector, row.selector),
        version=row.version,
        passport_digest=row.passport_digest,
        harness=cast(HarnessId | None, row.harness),
        state=payload.state,
        revision=row.revision,
    )
    if kind not in {"employee", "organization"}:
        response = CorporateCatalogAssignment.model_validate(
            {**response.model_dump(), f"{kind}_id": payload.subject_id}
        )
    await service.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="catalog_assignment.write",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="catalog_assignment.write",
        target_table="corporate_catalog_assignment",
        target_id=row.id,
        request_id=request_id,
    )
    return response


async def list_assignments(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    query: CorporateCatalogAssignmentQuery,
    request_id: str | None,
) -> CorporateCatalogAssignmentList:
    kind = query.subject_kind
    if kind == "organization":
        if query.subject_id != organization_id:
            raise ApiError(ErrorCategory.PERMISSION, "organization access denied")
        await service.authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission="organization.read",
        )
    elif kind == "employee":
        await service.read_member(
            db,
            ctx=ctx,
            organization_id=organization_id,
            account_id=query.subject_id,
            request_id=request_id,
        )
    elif kind == "team":
        await service.read_team(
            db,
            ctx=ctx,
            organization_id=organization_id,
            team_id=query.subject_id,
            request_id=request_id,
        )
    elif kind == "technology":
        await service.authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission="technology.read",
            scope_kind="technology",
            scope_id=query.subject_id,
        )
        technology = await db.scalar(
            select(Technology).where(
                Technology.organization_id == organization_id,
                Technology.id == query.subject_id,
            )
        )
        if technology is None:
            raise ApiError(ErrorCategory.PERMISSION, "technology access denied")
    else:
        await service.read_project(
            db,
            ctx=ctx,
            organization_id=organization_id,
            project_id=query.subject_id,
            request_id=request_id,
        )
    column = _subject_column(kind)
    predicate: ColumnElement[bool]
    if column is None:
        predicate = (
            AssignmentRow.account_id.is_(None)
            & AssignmentRow.team_id.is_(None)
            & AssignmentRow.project_id.is_(None)
            & AssignmentRow.technology_id.is_(None)
        )
    else:
        predicate = column == query.subject_id
    state_filter: ColumnElement[bool] = AssignmentRow.state == "current"
    if query.include_retired:
        # Historical direct revisions support reassignment; retired team effects never propagate.
        state_filter = or_(state_filter, predicate)
    if kind == "employee":
        team_ids = (
            select(CorporateTeamMember.team_id)
            .join(
                CorporateTeam,
                (CorporateTeam.id == CorporateTeamMember.team_id)
                & (CorporateTeam.organization_id == CorporateTeamMember.organization_id),
            )
            .where(
                CorporateTeamMember.organization_id == organization_id,
                CorporateTeamMember.account_id == query.subject_id,
                CorporateTeam.state == "active",
            )
        )
        predicate = or_(predicate, AssignmentRow.team_id.in_(team_ids))
    rows = (
        await db.scalars(
            select(AssignmentRow)
            .where(
                AssignmentRow.organization_id == organization_id,
                state_filter,
                predicate,
            )
            .order_by(AssignmentRow.id)
        )
    ).all()
    items: list[CorporateCatalogAssignment] = []
    for row in rows:
        if row.object_kind not in {"setup", "component"}:
            raise ApiError(ErrorCategory.VALIDATION, "invalid persisted assignment kind")
        object_kind = "setup" if row.object_kind == "setup" else "component"
        catalog = None
        if row.version is not None:
            catalog = await get_visible_metadata(
                db,
                object_kind=object_kind,
                stable_id=row.stable_id,
                version=row.version,
                account_id=ctx.account_id,
            )
        # Assignment metadata is tenant-scoped operational data. It remains
        # visible to an authorized corporate reader even when the catalog
        # object's content is outside that reader's catalog access.
        display_name = (
            catalog.name
            if catalog is not None
            and catalog.published_at is not None
            and catalog.lifecycle_state in _ELIGIBLE_LIFECYCLES
            else None
        )
        items.append(
            CorporateCatalogAssignment.model_validate(
                {
                    "assignment_id": row.id,
                    "organization_id": organization_id,
                    "subject_kind": kind,
                    "subject_id": query.subject_id,
                    "object_kind": row.object_kind,
                    "stable_id": row.stable_id,
                    "selector": row.selector,
                    "version": row.version,
                    "passport_digest": row.passport_digest,
                    "harness": row.harness,
                    "state": row.state,
                    "revision": row.revision,
                    "source_team_id": row.team_id if kind == "employee" else None,
                    "display_name": display_name or row.stable_id,
                }
            )
        )
    return CorporateCatalogAssignmentList(
        items=items[query.offset : query.offset + query.limit], total=len(items)
    )


async def list_usage(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    query: CorporateCatalogUsageQuery,
    request_id: str | None,
) -> CorporateCatalogUsageList:
    """Return one authorized, deduplicated usage projection for an exact object."""
    await service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="catalog_object.read",
    )
    version_predicate: ColumnElement[bool] = cast(ColumnElement[bool], true())
    if query.version is not None:
        # A `latest` row governs the whole line: it applies to whichever
        # version resolves at evaluation time, including the requested one.
        version_predicate = or_(
            AssignmentRow.version == query.version,
            and_(AssignmentRow.version.is_(None), AssignmentRow.selector == "latest"),
        )
    rows = (
        await db.scalars(
            select(AssignmentRow)
            .where(
                AssignmentRow.organization_id == organization_id,
                AssignmentRow.object_kind == query.object_kind,
                AssignmentRow.stable_id == query.stable_id,
                version_predicate,
                AssignmentRow.state == "current",
            )
            .order_by(AssignmentRow.id)
        )
    ).all()
    latest_version: str | None = None
    if any(row.version is None for row in rows):
        eligible = await _eligible_versions(
            db,
            object_kind=query.object_kind,
            stable_id=query.stable_id,
            account_id=ctx.account_id,
        )
        latest_version = eligible[-1][0] if eligible else None
    team_ids = {row.team_id for row in rows if row.team_id is not None}
    account_ids = {row.account_id for row in rows if row.account_id is not None}
    if team_ids:
        account_ids.update(
            (
                await db.scalars(
                    select(CorporateTeamMember.account_id).where(
                        CorporateTeamMember.organization_id == organization_id,
                        CorporateTeamMember.team_id.in_(team_ids),
                    )
                )
            ).all()
        )
    team_members_by_team: dict[str, list[CorporateTeamMember]] = {}
    if team_ids:
        for member in (
            await db.scalars(
                select(CorporateTeamMember).where(
                    CorporateTeamMember.organization_id == organization_id,
                    CorporateTeamMember.team_id.in_(team_ids),
                )
            )
        ).all():
            team_members_by_team.setdefault(member.team_id, []).append(member)
    teams = {
        row.id: row.name
        for row in (
            await db.scalars(
                select(CorporateTeam).where(
                    CorporateTeam.organization_id == organization_id,
                    CorporateTeam.id.in_(team_ids or {""}),
                )
            )
        ).all()
    }
    projects = {
        row.id: row.name
        for row in (
            await db.scalars(
                select(CorporateProject).where(
                    CorporateProject.organization_id == organization_id,
                    CorporateProject.id.in_({row.project_id for row in rows if row.project_id}),
                )
            )
        ).all()
    }
    technologies = {
        row.id: row.name
        for row in (
            await db.scalars(
                select(Technology).where(
                    Technology.organization_id == organization_id,
                    Technology.id.in_({row.technology_id for row in rows if row.technology_id}),
                )
            )
        ).all()
    }
    members = {
        membership.account_id: membership.display_name or account.display_name
        for membership, account in (
            await db.execute(
                select(OrganizationMembership, Account)
                .join(Account, Account.id == OrganizationMembership.account_id)
                .where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.account_id.in_(account_ids or {""}),
                )
            )
        ).all()
    }
    permission_cache: dict[tuple[str, str], bool] = {}

    async def readable(kind: str, identity: str) -> bool:
        key = (kind, identity)
        if key not in permission_cache:
            permission_cache[key] = await has_corporate_permission(
                db,
                organization_id=organization_id,
                principal_type="user",
                principal_id=ctx.account_id,
                permission="member.read" if kind == "employee" else f"{kind}.read",
                scope_kind="organization" if kind == "employee" else kind,
                scope_id=organization_id if kind == "employee" else identity,
            )
        return permission_cache[key]

    def subject(row: AssignmentRow) -> tuple[UsageSubjectKind, str, str] | None:
        for kind, identity, name in (
            ("employee", row.account_id, members.get(row.account_id or "", "")),
            ("team", row.team_id, teams.get(row.team_id or "", "")),
            ("project", row.project_id, projects.get(row.project_id or "", "")),
            ("technology", row.technology_id, technologies.get(row.technology_id or "", "")),
        ):
            if identity is not None:
                return cast(UsageSubjectKind, kind), identity, name or identity
        return None

    items: list[CorporateCatalogUsage] = []
    for row in rows:
        # `latest` rows carry no stored coordinate; the resolved version is
        # display-only context, the selector stays the assignment's own.
        row_version = row.version if row.version is not None else latest_version
        selector = cast(AssignmentSelector, row.selector)
        identity = subject(row)
        if identity is not None and await readable(identity[0], identity[1]):
            items.append(
                CorporateCatalogUsage(
                    organization_id=organization_id,
                    assignment_id=row.id,
                    object_kind=query.object_kind,
                    stable_id=row.stable_id,
                    selector=selector,
                    version=row_version,
                    subject_kind=identity[0],
                    subject_id=identity[1],
                    subject_name=identity[2],
                    source="direct",
                )
            )
        if row.team_id is None:
            continue
        for member in team_members_by_team.get(row.team_id, []):
            member_name = members.get(member.account_id)
            if member_name is None or not await readable("employee", member.account_id):
                continue
            items.append(
                CorporateCatalogUsage(
                    organization_id=organization_id,
                    assignment_id=row.id,
                    object_kind=query.object_kind,
                    stable_id=row.stable_id,
                    selector=selector,
                    version=row_version,
                    subject_kind="employee",
                    subject_id=member.account_id,
                    subject_name=member_name,
                    source="effective",
                    source_team_id=row.team_id,
                )
            )
    items.sort(key=lambda item: (item.subject_name.casefold(), item.subject_id, item.source))
    return CorporateCatalogUsageList(
        items=items[query.offset : query.offset + query.limit], total=len(items)
    )


async def _member_team_ids(db: AsyncSession, *, organization_id: str, account_id: str) -> set[str]:
    """Active team identities one employee belongs to inside the tenant."""
    return set(
        (
            await db.scalars(
                select(CorporateTeamMember.team_id)
                .join(
                    CorporateTeam,
                    (CorporateTeam.id == CorporateTeamMember.team_id)
                    & (CorporateTeam.organization_id == CorporateTeamMember.organization_id),
                )
                .where(
                    CorporateTeamMember.organization_id == organization_id,
                    CorporateTeamMember.account_id == account_id,
                    CorporateTeam.state == "active",
                )
            )
        ).all()
    )


async def _require_project_scope(
    db: AsyncSession, *, organization_id: str, project_id: str, account_id: str
) -> None:
    """A project scope applies to an employee only while the link is current.

    Distribution resolves project assignments onto project members, so
    evaluation must apply the same boundary: naming a project the account is
    not a member of is an invalid context, not a silent extra scope (REQ-8107).
    Refusing keeps a mistyped or foreign project from quietly producing a plan
    that omits requirements the named context was meant to carry.
    """
    member = await db.scalar(
        select(CorporateProjectMember.account_id)
        .join(
            CorporateProject,
            (CorporateProject.id == CorporateProjectMember.project_id)
            & (CorporateProject.organization_id == CorporateProjectMember.organization_id),
        )
        .where(
            CorporateProjectMember.organization_id == organization_id,
            CorporateProjectMember.project_id == project_id,
            CorporateProjectMember.account_id == account_id,
            CorporateProject.state == "active",
        )
    )
    if member is None:
        raise ApiError(ErrorCategory.VALIDATION, "the account is not a member of the named project")


async def _evaluate_assignment_line(
    db: AsyncSession,
    *,
    organization_id: str,
    query: CorporateEffectiveAssignmentQuery,
    rows: Sequence[AssignmentRow],
    team_ids: set[str],
    viewer_account_id: str,
) -> CorporateEffectiveAssignment:
    """Evaluate the winning assignment for one employee and one catalog line.

    Deterministic order (ADR-0194): employee, project, technology, team,
    organization; inside one scope a harness-specific assignment outranks an
    unrestricted one; an explicit employee decision - current or retired -
    outranks every inherited assignment. `latest` resolves at evaluation time
    against the employee's eligible catalog versions and never rewrites stored
    assignments or materialized installations.
    """

    def applicable(row: AssignmentRow) -> tuple[AssignmentSubjectKind, str] | None:
        kind, identity = _row_scope(row)
        if kind == "employee":
            return (kind, identity) if identity == query.account_id else None
        if kind == "team":
            return (kind, identity) if identity in team_ids else None
        if kind == "project":
            return (kind, identity) if identity == query.project_id else None
        if kind == "technology":
            return (kind, identity) if identity == query.technology_id else None
        return kind, identity

    def harness_ok(row: AssignmentRow) -> bool:
        return row.harness is None or row.harness == query.harness

    def sort_key(
        entry: tuple[AssignmentRow, tuple[AssignmentSubjectKind, str]],
    ) -> tuple[int, int, int, str]:
        row, (kind, _identity) = entry
        return (
            _SCOPE_RANK[kind],
            0 if row.harness is not None else 1,
            -row.revision,
            row.id,
        )

    considered = [
        (row, scope) for row in rows if (scope := applicable(row)) is not None and harness_ok(row)
    ]
    considered.sort(key=sort_key)
    employee_entries = [entry for entry in considered if entry[1][0] == "employee"]

    winner: AssignmentRow | None = None
    winner_scope: tuple[AssignmentSubjectKind, str] | None = None
    revoked = False
    if employee_entries:
        top, top_scope = min(employee_entries, key=sort_key)
        if top.state == "retired":
            revoked = True
        else:
            winner, winner_scope = top, top_scope
    else:
        current = [entry for entry in considered if entry[0].state == "current"]
        if current:
            winner, winner_scope = current[0]

    resolved_version: str | None = None
    resolved_digest: str | None = None
    if winner is not None:
        if winner.selector == "latest":
            eligible = await _eligible_versions(
                db,
                object_kind=query.object_kind,
                stable_id=query.stable_id,
                account_id=query.account_id,
            )
            if eligible:
                resolved_version, resolved_digest = eligible[-1]
        else:
            resolved_version = winner.version
            resolved_digest = winner.passport_digest
            if resolved_digest is None and winner.version is not None:
                catalog = await get_visible_metadata(
                    db,
                    object_kind=query.object_kind,
                    stable_id=query.stable_id,
                    version=winner.version,
                    account_id=viewer_account_id,
                )
                resolved_digest = None if catalog is None else catalog.passport_digest

    candidates: list[CorporateEffectiveAssignmentCandidate] = []
    for row, (kind, identity) in considered:
        if row is winner:
            outcome: Literal["winner", "overridden", "revoked", "inapplicable"] = "winner"
        elif row.state == "retired":
            outcome = "revoked"
        else:
            outcome = "overridden"
        candidates.append(
            CorporateEffectiveAssignmentCandidate(
                assignment_id=row.id,
                scope=kind,
                subject_id=identity,
                selector=cast(AssignmentSelector, row.selector),
                version=row.version,
                harness=cast(HarnessId | None, row.harness),
                state=cast(Literal["current", "retired"], row.state),
                revision=row.revision,
                outcome=outcome,
                resolved_version=resolved_version if row is winner else None,
                resolved_digest=resolved_digest if row is winner else None,
            )
        )
    if winner is not None and winner_scope is not None:
        state: Literal["assigned", "revoked", "unassigned"] = "assigned"
    elif revoked:
        state = "revoked"
    else:
        state = "unassigned"
    return CorporateEffectiveAssignment(
        organization_id=organization_id,
        account_id=query.account_id,
        object_kind=query.object_kind,
        stable_id=query.stable_id,
        state=state,
        assignment_id=winner.id if winner is not None else None,
        source_scope=winner_scope[0] if winner_scope is not None else None,
        source_subject_id=winner_scope[1] if winner_scope is not None else None,
        selector=cast(AssignmentSelector, winner.selector) if winner is not None else None,
        version=resolved_version,
        passport_digest=resolved_digest,
        harness=cast(HarnessId | None, winner.harness) if winner is not None else None,
        candidates=candidates,
    )


async def resolve_effective(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    query: CorporateEffectiveAssignmentQuery,
    request_id: str | None,
) -> CorporateEffectiveAssignment:
    """Authorize the member read and evaluate one catalog line (ADR-0194)."""
    await service.read_member(
        db,
        ctx=ctx,
        organization_id=organization_id,
        account_id=query.account_id,
        request_id=request_id,
    )
    if query.project_id is not None:
        await _require_project_scope(
            db,
            organization_id=organization_id,
            project_id=query.project_id,
            account_id=query.account_id,
        )
    rows = (
        await db.scalars(
            select(AssignmentRow)
            .where(
                AssignmentRow.organization_id == organization_id,
                AssignmentRow.object_kind == query.object_kind,
                AssignmentRow.stable_id == query.stable_id,
            )
            .order_by(AssignmentRow.id)
        )
    ).all()
    team_ids = await _member_team_ids(
        db, organization_id=organization_id, account_id=query.account_id
    )
    return await _evaluate_assignment_line(
        db,
        organization_id=organization_id,
        query=query,
        rows=rows,
        team_ids=team_ids,
        viewer_account_id=ctx.account_id,
    )


def _plan_item(
    evaluation: CorporateEffectiveAssignment,
    *,
    materialized: CorporatePlanMaterializedItem | None,
    resolved_version: str | None,
    resolved_digest: str | None,
    supported: bool,
) -> CorporateAssignmentPlanItem:
    """Classify one evaluated line against the reported materialized state."""
    outcome: PlanOutcome
    action: PlanAction
    diagnostic: str | None = None
    if evaluation.state == "assigned" and not supported:
        outcome, action = "unsupported", "none"
        resolved_version, resolved_digest = None, None
        diagnostic = "assigned coordinate has no eligible published version"
    elif evaluation.state == "assigned":
        if materialized is None:
            outcome, action = "missing", "install"
        elif materialized.version != resolved_version:
            outcome, action = "outdated", "update"
        elif (
            materialized.passport_digest is not None
            and resolved_digest is not None
            and materialized.passport_digest != resolved_digest
        ):
            outcome, action = "conflicting", "update"
            diagnostic = "materialized digest differs from the assigned coordinate"
        else:
            outcome, action = "installed", "none"
    else:
        outcome = cast(PlanOutcome, evaluation.state)
        action = "remove" if materialized is not None else "none"
    return CorporateAssignmentPlanItem(
        object_kind=evaluation.object_kind,
        stable_id=evaluation.stable_id,
        state=evaluation.state,
        outcome=outcome,
        action=action,
        assignment_id=evaluation.assignment_id,
        source_scope=evaluation.source_scope,
        source_subject_id=evaluation.source_subject_id,
        selector=evaluation.selector,
        version=resolved_version,
        passport_digest=resolved_digest,
        harness=evaluation.harness,
        installed_version=None if materialized is None else materialized.version,
        installed_passport_digest=None if materialized is None else materialized.passport_digest,
        diagnostic=diagnostic,
        candidates=evaluation.candidates,
    )


#: A setup's member graph is walked transitively through `requires_components`;
#: the bound keeps a malformed or cyclic document from turning a read into a
#: scan, the same way every other catalog walk in this slice is bounded.
_MEMBER_GRAPH_BOUND = 512


def _reference_triples(
    document: dict[str, object], field: str
) -> list[tuple[str, str, str | None]]:
    raw = document.get(field)
    if not isinstance(raw, list):
        return []
    triples: list[tuple[str, str, str | None]] = []
    for entry in cast(list[object], raw):
        if not isinstance(entry, dict):
            continue
        held = cast(dict[str, object], entry)
        stable_id = held.get("stable_id")
        version = held.get("version")
        if not isinstance(stable_id, str) or not stable_id:
            continue
        if not isinstance(version, str) or not version:
            continue
        digest = held.get("passport_digest")
        triples.append((stable_id, version, digest if isinstance(digest, str) else None))
    return triples


async def _passport_document(
    db: AsyncSession,
    *,
    object_kind: Literal["setup", "component"],
    stable_id: str,
    version: str,
    account_id: str,
) -> dict[str, object] | None:
    metadata = await get_visible_metadata(
        db,
        object_kind=object_kind,
        stable_id=stable_id,
        version=version,
        account_id=account_id,
    )
    document = None if metadata is None else metadata.passport_document
    return document if isinstance(document, dict) else None


async def _assigned_setup_members(
    db: AsyncSession,
    *,
    items: list[CorporateAssignmentPlanItem],
    materialized: dict[tuple[str, str], CorporatePlanMaterializedItem],
    account_id: str,
) -> dict[tuple[str, str, str | None], str]:
    """Exact member coordinates an assigned setup's materialized version pins.

    Assigning a setup approves the exact component graph that version carries,
    so a member materialized at its pinned coordinate is allowed through the
    setup rather than standing as an unauthorized install. Only setups the
    context both assigns and has materialized contribute their graph, and only
    lines with no effective assignment at all are covered - an explicit revoke
    still dominates.
    """
    covered: dict[tuple[str, str, str | None], str] = {}
    for item in items:
        if item.object_kind != "setup" or item.state != "assigned":
            continue
        held = materialized.get(("setup", item.stable_id))
        if held is None:
            continue
        document = await _passport_document(
            db,
            object_kind="setup",
            stable_id=held.stable_id,
            version=held.version,
            account_id=account_id,
        )
        if document is None:
            continue
        pending = _reference_triples(document, "components")
        steps = 0
        while pending and steps < _MEMBER_GRAPH_BOUND:
            steps += 1
            member_id, member_version, member_digest = pending.pop()
            key = (member_id, member_version, member_digest)
            if key in covered:
                continue
            covered[key] = held.stable_id
            member = await _passport_document(
                db,
                object_kind="component",
                stable_id=member_id,
                version=member_version,
                account_id=account_id,
            )
            if member is not None:
                pending.extend(_reference_triples(member, "requires_components"))
    return covered


def _cover_setup_member(
    item: CorporateAssignmentPlanItem,
    materialized: dict[tuple[str, str], CorporatePlanMaterializedItem],
    covered: dict[tuple[str, str, str | None], str],
) -> CorporateAssignmentPlanItem:
    if item.object_kind != "component" or item.state != "unassigned":
        return item
    held = materialized.get(("component", item.stable_id))
    if held is None:
        return item
    for (member_id, version, digest), setup_id in covered.items():
        if member_id != item.stable_id or version != held.version:
            continue
        if (
            digest is not None
            and held.passport_digest is not None
            and digest != held.passport_digest
        ):
            continue
        return item.model_copy(
            update={
                "outcome": "installed",
                "action": "none",
                "diagnostic": (f"materialized as an exact member of the assigned setup {setup_id}"),
            }
        )
    return item


async def plan_assignments(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateAssignmentPlanRequest,
    request_id: str | None,
) -> CorporateAssignmentPlan:
    """Evaluate the deterministic install/update plan for one context (ADR-0196).

    Every catalog line carrying an assignment applicable to the context - plus
    every materialized coordinate the caller reports - is evaluated through the
    same precedence as the single-line effective read. Resolved coordinates are
    always exact and eligible; the plan is a pure read and writes nothing.
    """
    await service.read_member(
        db,
        ctx=ctx,
        organization_id=organization_id,
        account_id=payload.account_id,
        request_id=request_id,
    )
    if payload.project_id is not None:
        await _require_project_scope(
            db,
            organization_id=organization_id,
            project_id=payload.project_id,
            account_id=payload.account_id,
        )
    team_ids = await _member_team_ids(
        db, organization_id=organization_id, account_id=payload.account_id
    )
    scope_clauses: list[ColumnElement[bool]] = [
        and_(
            AssignmentRow.account_id.is_(None),
            AssignmentRow.team_id.is_(None),
            AssignmentRow.project_id.is_(None),
            AssignmentRow.technology_id.is_(None),
        ),
        AssignmentRow.account_id == payload.account_id,
    ]
    if team_ids:
        scope_clauses.append(AssignmentRow.team_id.in_(team_ids))
    if payload.project_id is not None:
        scope_clauses.append(AssignmentRow.project_id == payload.project_id)
    if payload.technology_id is not None:
        scope_clauses.append(AssignmentRow.technology_id == payload.technology_id)
    rows = (
        await db.scalars(
            select(AssignmentRow)
            .where(AssignmentRow.organization_id == organization_id, or_(*scope_clauses))
            .order_by(AssignmentRow.id)
        )
    ).all()
    by_line: dict[tuple[str, str], list[AssignmentRow]] = {}
    for row in rows:
        by_line.setdefault((row.object_kind, row.stable_id), []).append(row)
    materialized = {(item.object_kind, item.stable_id): item for item in payload.materialized}
    items: list[CorporateAssignmentPlanItem] = []
    for object_kind, stable_id in sorted(set(by_line) | set(materialized)):
        line_query = CorporateEffectiveAssignmentQuery(
            account_id=payload.account_id,
            object_kind=cast(Literal["setup", "component"], object_kind),
            stable_id=stable_id,
            project_id=payload.project_id,
            technology_id=payload.technology_id,
            harness=payload.harness,
        )
        evaluation = await _evaluate_assignment_line(
            db,
            organization_id=organization_id,
            query=line_query,
            rows=by_line.get((object_kind, stable_id), []),
            team_ids=team_ids,
            viewer_account_id=ctx.account_id,
        )
        resolved_version, resolved_digest = evaluation.version, evaluation.passport_digest
        supported = True
        if evaluation.state == "assigned":
            eligible = await _eligible_versions(
                db,
                object_kind=line_query.object_kind,
                stable_id=stable_id,
                account_id=payload.account_id,
            )
            if evaluation.selector == "latest":
                supported = bool(eligible)
            else:
                match = next((pair for pair in eligible if pair[0] == resolved_version), None)
                supported = match is not None
                if match is not None:
                    resolved_version, resolved_digest = match
        items.append(
            _plan_item(
                evaluation,
                materialized=materialized.get((object_kind, stable_id)),
                resolved_version=resolved_version,
                resolved_digest=resolved_digest,
                supported=supported,
            )
        )
    covered = await _assigned_setup_members(
        db,
        items=items,
        materialized=materialized,
        account_id=payload.account_id,
    )
    if covered:
        items = [_cover_setup_member(item, materialized, covered) for item in items]
    return CorporateAssignmentPlan(
        organization_id=organization_id,
        account_id=payload.account_id,
        harness=payload.harness,
        project_id=payload.project_id,
        technology_id=payload.technology_id,
        items=items,
        total=len(items),
    )


# ADR-0195: per-source-scope write authorization for distribution.
_DISTRIBUTE_PERMISSIONS = {
    "employee": ("member.manage", "organization"),
    "team": ("team.update", "team"),
    "project": ("project.update", "project"),
    "technology": ("technology.update", "technology"),
    "organization": ("organization.manage", "organization"),
}
# Read authorization for the distribution-state endpoint.
_DISTRIBUTION_READ_PERMISSIONS = {
    "team": ("team.read", "team"),
    "project": ("project.read", "project"),
    "technology": ("technology.read", "technology"),
    "organization": ("organization.read", "organization"),
}


async def _expand_targets(
    db: AsyncSession,
    *,
    organization_id: str,
    kind: AssignmentSubjectKind,
    identity: str | None,
) -> tuple[list[str], list[str], list[CorporateDistributionExclusion]]:
    """Resolve the source scope into employee/project targets plus exclusions.

    Employees are always resolved through an active membership; projects are
    limited to active corporate projects. Inactive or foreign scope members are
    returned as exclusions instead of targets (REQ-8511).
    """
    active_member_ids = select(OrganizationMembership.account_id).where(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.state == "active",
    )
    members: set[str] = set()
    projects: set[str] = set()
    exclusions: list[CorporateDistributionExclusion] = []
    if kind == "employee":
        membership = await db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.account_id == identity,
            )
        )
        if membership is None or membership.state != "active":
            exclusions.append(
                CorporateDistributionExclusion(
                    target_kind="employee",
                    target_id=identity or "",
                    reason="membership_inactive",
                )
            )
        else:
            members.add(membership.account_id)
    elif kind == "team":
        members.update(
            (
                await db.scalars(
                    select(CorporateTeamMember.account_id).where(
                        CorporateTeamMember.organization_id == organization_id,
                        CorporateTeamMember.team_id == identity,
                        CorporateTeamMember.account_id.in_(active_member_ids),
                    )
                )
            ).all()
        )
        projects.update(
            (
                await db.scalars(
                    select(ProjectTeamRelation.project_id)
                    .join(
                        CorporateProject,
                        (CorporateProject.organization_id == ProjectTeamRelation.organization_id)
                        & (CorporateProject.id == ProjectTeamRelation.project_id),
                    )
                    .where(
                        ProjectTeamRelation.organization_id == organization_id,
                        ProjectTeamRelation.team_id == identity,
                        ProjectTeamRelation.state == "current",
                        CorporateProject.state == "active",
                    )
                )
            ).all()
        )
    elif kind == "project":
        members.update(
            (
                await db.scalars(
                    select(CorporateProjectMember.account_id).where(
                        CorporateProjectMember.organization_id == organization_id,
                        CorporateProjectMember.project_id == identity,
                        CorporateProjectMember.account_id.in_(active_member_ids),
                    )
                )
            ).all()
        )
        project = await db.scalar(
            select(CorporateProject).where(
                CorporateProject.organization_id == organization_id,
                CorporateProject.id == identity,
            )
        )
        if project is None or project.state != "active":
            exclusions.append(
                CorporateDistributionExclusion(
                    target_kind="project",
                    target_id=identity or "",
                    reason="project_inactive",
                )
            )
        else:
            projects.add(project.id)
    elif kind == "technology":
        team_ids = (
            await db.scalars(
                select(TechnologyTeamResponsibility.team_id).where(
                    TechnologyTeamResponsibility.organization_id == organization_id,
                    TechnologyTeamResponsibility.technology_id == identity,
                    TechnologyTeamResponsibility.state == "current",
                )
            )
        ).all()
        if team_ids:
            members.update(
                (
                    await db.scalars(
                        select(CorporateTeamMember.account_id).where(
                            CorporateTeamMember.organization_id == organization_id,
                            CorporateTeamMember.team_id.in_(team_ids),
                            CorporateTeamMember.account_id.in_(active_member_ids),
                        )
                    )
                ).all()
            )
        projects.update(
            (
                await db.scalars(
                    select(ProjectTechnologyRelation.project_id)
                    .join(
                        CorporateProject,
                        (
                            CorporateProject.organization_id
                            == ProjectTechnologyRelation.organization_id
                        )
                        & (CorporateProject.id == ProjectTechnologyRelation.project_id),
                    )
                    .where(
                        ProjectTechnologyRelation.organization_id == organization_id,
                        ProjectTechnologyRelation.technology_id == identity,
                        ProjectTechnologyRelation.state == "current",
                        CorporateProject.state == "active",
                    )
                )
            ).all()
        )
        if projects:
            members.update(
                (
                    await db.scalars(
                        select(CorporateProjectMember.account_id).where(
                            CorporateProjectMember.organization_id == organization_id,
                            CorporateProjectMember.project_id.in_(projects),
                            CorporateProjectMember.account_id.in_(active_member_ids),
                        )
                    )
                ).all()
            )
    else:
        members.update((await db.scalars(active_member_ids)).all())
        projects.update(
            (
                await db.scalars(
                    select(CorporateProject.id).where(
                        CorporateProject.organization_id == organization_id,
                        CorporateProject.state == "active",
                    )
                )
            ).all()
        )
    return sorted(members), sorted(projects), exclusions


def _derive_state(row: DistributionRow, *, source: AssignmentRow) -> DistributionLifecycle | None:
    """Derived lifecycle for a stored distribution row (REQ-8515).

    Non-applied results never carry a lifecycle. A stored ``pending`` row whose
    source revision advanced becomes ``outdated``; anything applied under a
    retired source reports ``revoked``. ``installed`` is only ever observed from
    the stored row — distribution never mutates provider-owned harness state.
    """
    if row.result == "failed":
        return "failed"
    if row.result != "applied":
        return None
    if source.state == "retired":
        return "revoked"
    if row.state == "pending" and row.operation_revision < source.revision:
        return "outdated"
    return cast(DistributionLifecycle, row.state)


async def _target_authorized(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    target_kind: DistributionTargetKind,
    target_id: str,
) -> bool:
    if target_kind == "employee":
        return await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=ctx.account_id,
            permission="member.manage",
            scope_kind="organization",
            scope_id=organization_id,
        )
    return await has_corporate_permission(
        db,
        organization_id=organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        permission="project.update",
        scope_kind="project",
        scope_id=target_id,
    )


async def distribute_assignment(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateDistributionRequest,
    request_id: str | None,
) -> CorporateDistributionResult:
    """Preview or apply one bulk assignment distribution (ADR-0195).

    Expansion, exclusion, override, per-target authorization, and result
    classification are identical for dry-run and apply; apply additionally
    mutates the source (revoke retires it), persists every per-target outcome,
    and stores the idempotent receipt. A later skipped/conflicted/denied row
    must never mask an earlier applied row when deciding revoke eligibility or
    collide with it on the composite key.
    Distribution rows never copy the source selector/version/harness
    policy and never touch provider state.
    """
    source = await db.scalar(
        select(AssignmentRow).where(
            AssignmentRow.id == payload.source_assignment_id,
            AssignmentRow.organization_id == organization_id,
        )
    )
    if source is None:
        raise ApiError(
            ErrorCategory.PERMISSION,
            "source assignment is unavailable",
        )
    kind, identity = _row_scope(source)
    permission, scope_kind = _DISTRIBUTE_PERMISSIONS[kind]
    scope_id = identity if scope_kind != "organization" else organization_id
    if payload.dry_run:
        organization, _ = await service.authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission=permission,
            scope_kind=scope_kind,
            scope_id=scope_id,
        )
        if payload.authorization_revision != organization.policy_revision:
            raise ApiError(
                ErrorCategory.PRECONDITION,
                "capability revision is stale",
            )
    else:
        _, receipt = await service.authorize_idempotent(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission=permission,
            scope_kind=scope_kind,
            scope_id=scope_id,
            authorization_revision=payload.authorization_revision,
            idempotency_key=payload.idempotency_key,
            operation="catalog_assignment.distribute",
            fingerprint=service.mutation_fingerprint(
                payload.model_dump(mode="json", exclude={"idempotency_key"})
            ),
            request_id=request_id,
        )
        if receipt is not None:
            return CorporateDistributionResult.model_validate(receipt.response_body)
    # Revision and state preconditions run after the receipt check so an
    # idempotent revoke retry replays instead of tripping over the revision
    # its first application bumped.
    if source.state != "current":
        raise ApiError(ErrorCategory.CONFLICT, "source assignment is retired")
    if source.revision != payload.expected_revision:
        raise ApiError(
            ErrorCategory.PRECONDITION,
            "assignment revision is stale",
        )
    members, projects, exclusions = await _expand_targets(
        db, organization_id=organization_id, kind=kind, identity=identity
    )
    target_pairs: list[tuple[DistributionTargetKind, str]] = cast(
        list[tuple[DistributionTargetKind, str]],
        [("employee", member) for member in members]
        + [("project", project) for project in projects],
    )
    # Individual overrides: rows at the target's own scope for the same line.
    # A NULL-harness override applies unconditionally; a conditional one only
    # conflicts when it matches the source condition (ADR-0194/ADR-0195).
    scope_clauses: list[ColumnElement[bool]] = []
    if members:
        scope_clauses.append(AssignmentRow.account_id.in_(members))
    if projects:
        scope_clauses.append(AssignmentRow.project_id.in_(projects))
    overrides: dict[tuple[DistributionTargetKind, str], AssignmentRow] = {}
    if scope_clauses:
        harness_filter = (
            AssignmentRow.harness.is_(None)
            if source.harness is None
            else or_(
                AssignmentRow.harness.is_(None),
                AssignmentRow.harness == source.harness,
            )
        )
        override_rows = (
            await db.scalars(
                select(AssignmentRow).where(
                    AssignmentRow.organization_id == organization_id,
                    AssignmentRow.object_kind == source.object_kind,
                    AssignmentRow.stable_id == source.stable_id,
                    AssignmentRow.id != source.id,
                    or_(*scope_clauses),
                    harness_filter,
                )
            )
        ).all()
        for row in override_rows:
            key: tuple[DistributionTargetKind, str]
            if row.account_id is not None:
                key = ("employee", row.account_id)
            else:
                key = ("project", row.project_id or "")
            overrides[key] = row
    existing = (
        await db.scalars(
            select(DistributionRow).where(
                DistributionRow.organization_id == organization_id,
                DistributionRow.source_assignment_id == source.id,
            )
        )
    ).all()
    # Revoke eligibility and assign-suppression look at the latest *applied*
    # row per target: a later conflicted/denied/failed result must not mask a
    # still-outstanding earlier distribution.
    live_by_target: dict[tuple[DistributionTargetKind, str], DistributionRow] = {}
    for row in existing:
        if row.result != "applied":
            continue
        key = (cast(DistributionTargetKind, row.target_kind), row.target_id)
        current = live_by_target.get(key)
        if current is None or current.operation_revision < row.operation_revision:
            live_by_target[key] = row
    existing_by_key = {
        (row.target_kind, row.target_id, row.operation_revision): row for row in existing
    }
    source_revision = source.revision
    operation_revision = source_revision + 1 if payload.action == "revoke" else source_revision
    plans: list[CorporateDistributionTargetResult] = []
    for target_kind, target_id in target_pairs:
        authorized = await _target_authorized(
            db,
            ctx=ctx,
            organization_id=organization_id,
            target_kind=target_kind,
            target_id=target_id,
        )
        override = overrides.get((target_kind, target_id))
        live = live_by_target.get((target_kind, target_id))
        live_pending = (
            live is not None
            and live.result == "applied"
            and live.state in ("pending", "installed", "outdated")
        )
        if not authorized:
            plans.append(
                CorporateDistributionTargetResult(
                    target_kind=target_kind,
                    target_id=target_id,
                    result="denied",
                    diagnostic="target scope is not authorized",
                )
            )
        elif override is not None and payload.action == "assign":
            plans.append(
                CorporateDistributionTargetResult(
                    target_kind=target_kind,
                    target_id=target_id,
                    result="conflicted",
                    diagnostic="individual exception is authoritative",
                    overriding_assignment_id=override.id,
                )
            )
        elif payload.action == "assign":
            if live is not None and live.operation_revision == source_revision:
                plans.append(
                    CorporateDistributionTargetResult(
                        target_kind=target_kind,
                        target_id=target_id,
                        result="skipped",
                        state=_derive_state(live, source=source),
                        diagnostic="already distributed at this revision",
                    )
                )
            else:
                plans.append(
                    CorporateDistributionTargetResult(
                        target_kind=target_kind,
                        target_id=target_id,
                        result="applied",
                        state="pending",
                    )
                )
        elif live_pending:
            plans.append(
                CorporateDistributionTargetResult(
                    target_kind=target_kind,
                    target_id=target_id,
                    result="applied",
                    state="revoked",
                )
            )
        else:
            plans.append(
                CorporateDistributionTargetResult(
                    target_kind=target_kind,
                    target_id=target_id,
                    result="skipped",
                    diagnostic="no live distribution",
                )
            )
    if not payload.dry_run:
        if payload.action == "revoke":
            source.state = "retired"
            source.revision += 1
            await db.flush()
        for index, plan in enumerate(plans):
            # Reuse a row at this operation revision so a repeat operation can
            # update the durable outcome without colliding on the composite key.
            prior = existing_by_key.get((plan.target_kind, plan.target_id, operation_revision))
            try:
                async with db.begin_nested():
                    if prior is not None:
                        prior.action = payload.action
                        prior.result = plan.result
                        prior.state = plan.state
                        prior.diagnostic = plan.diagnostic
                        prior.overriding_assignment_id = plan.overriding_assignment_id
                    else:
                        db.add(
                            DistributionRow(
                                organization_id=organization_id,
                                source_assignment_id=source.id,
                                target_kind=plan.target_kind,
                                target_id=plan.target_id,
                                operation_revision=operation_revision,
                                action=payload.action,
                                result=plan.result,
                                state=plan.state,
                                diagnostic=plan.diagnostic,
                                overriding_assignment_id=plan.overriding_assignment_id,
                            )
                        )
            except Exception:
                plans[index] = plan.model_copy(
                    update={
                        "result": "failed",
                        "state": "failed",
                        "diagnostic": "distribution record failed",
                    }
                )
                try:
                    async with db.begin_nested():
                        if prior is not None:
                            prior.action = payload.action
                            prior.result = "failed"
                            prior.state = "failed"
                            prior.diagnostic = "distribution record failed"
                        else:
                            db.add(
                                DistributionRow(
                                    organization_id=organization_id,
                                    source_assignment_id=source.id,
                                    target_kind=plan.target_kind,
                                    target_id=plan.target_id,
                                    operation_revision=operation_revision,
                                    action=payload.action,
                                    result="failed",
                                    state="failed",
                                    diagnostic="distribution record failed",
                                )
                            )
                except Exception:
                    pass
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            organization_id=organization_id,
            action=f"catalog_assignment.{payload.action}.distribute",
            target_table="corporate_assignment_distribution",
            target_id=source.id,
            request_id=request_id,
            payload={
                "action": payload.action,
                "targets": len(plans),
                "applied": sum(1 for plan in plans if plan.result == "applied"),
            },
        )
    counts = CorporateDistributionCounts(
        applied=sum(1 for plan in plans if plan.result == "applied"),
        skipped=sum(1 for plan in plans if plan.result == "skipped"),
        conflicted=sum(1 for plan in plans if plan.result == "conflicted"),
        denied=sum(1 for plan in plans if plan.result == "denied"),
        failed=sum(1 for plan in plans if plan.result == "failed"),
    )
    result = CorporateDistributionResult(
        distribution_id=None if payload.dry_run else payload.idempotency_key,
        organization_id=organization_id,
        source_assignment_id=source.id,
        action=payload.action,
        dry_run=payload.dry_run,
        source_revision=source_revision,
        targets=plans,
        exclusions=exclusions,
        counts=counts,
    )
    if not payload.dry_run:
        await service.store_mutation_receipt(
            db,
            organization_id=organization_id,
            key=payload.idempotency_key,
            operation="catalog_assignment.distribute",
            fingerprint=service.mutation_fingerprint(
                payload.model_dump(mode="json", exclude={"idempotency_key"})
            ),
            response=result,
        )
    return result


async def list_distribution(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    query: CorporateDistributionStateQuery,
    request_id: str | None,
) -> CorporateDistributionStateList:
    """Latest per-target distribution state for one source assignment."""
    source = await db.scalar(
        select(AssignmentRow).where(
            AssignmentRow.id == query.source_assignment_id,
            AssignmentRow.organization_id == organization_id,
        )
    )
    if source is None:
        raise ApiError(
            ErrorCategory.PERMISSION,
            "source assignment is unavailable",
        )
    kind, identity = _row_scope(source)
    if kind == "employee":
        await service.read_member(
            db,
            ctx=ctx,
            organization_id=organization_id,
            account_id=identity or "",
            request_id=request_id,
        )
    else:
        permission, scope_kind = _DISTRIBUTION_READ_PERMISSIONS[kind]
        await service.authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission=permission,
            scope_kind=scope_kind,
            scope_id=identity if scope_kind != "organization" else organization_id,
        )
    rows = (
        await db.scalars(
            select(DistributionRow).where(
                DistributionRow.organization_id == organization_id,
                DistributionRow.source_assignment_id == source.id,
            )
        )
    ).all()
    latest: dict[tuple[str, str], DistributionRow] = {}
    for row in rows:
        key = (row.target_kind, row.target_id)
        current = latest.get(key)
        if current is None or current.operation_revision < row.operation_revision:
            latest[key] = row
    items = [
        CorporateDistributionState(
            target_kind=cast(DistributionTargetKind, row.target_kind),
            target_id=row.target_id,
            result=cast(DistributionTargetResult, row.result),
            state=_derive_state(row, source=source),
            operation_revision=row.operation_revision,
            diagnostic=row.diagnostic,
        )
        for _, row in sorted(latest.items())
    ]
    return CorporateDistributionStateList(
        organization_id=organization_id,
        source_assignment_id=source.id,
        source_revision=source.revision,
        source_state=cast(AssignmentState, source.state),
        items=items[query.offset : query.offset + query.limit],
        total=len(items),
    )
