"""Operational catalog assignments never mutate grants or harness state."""

from typing import Literal, cast

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_contracts.corporate import (
    AssignmentSelector,
    AssignmentSubjectKind,
    CorporateCatalogAssignment,
    CorporateCatalogAssignmentList,
    CorporateCatalogAssignmentQuery,
    CorporateCatalogAssignmentRequest,
    CorporateCatalogUsage,
    CorporateCatalogUsageList,
    CorporateCatalogUsageQuery,
    CorporateEffectiveAssignment,
    CorporateEffectiveAssignmentCandidate,
    CorporateEffectiveAssignmentQuery,
)
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.versioning import parse_version
from ai_stp_platform.catalog_read import get_visible_metadata, get_visible_object_versions
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateCatalogAssignment as AssignmentRow,
)
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateTeam,
    CorporateTeamMember,
    OrganizationMembership,
)
from ai_stp_platform.technology_models import Technology

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
    rows = (
        await db.scalars(
            select(AssignmentRow)
            .where(
                AssignmentRow.organization_id == organization_id,
                AssignmentRow.object_kind == query.object_kind,
                AssignmentRow.stable_id == query.stable_id,
                AssignmentRow.version == query.version,
                AssignmentRow.state == "current",
            )
            .order_by(AssignmentRow.id)
        )
    ).all()
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
                permission=f"{kind}.read",
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
        # The usage view answers for one exact version; `latest` rows resolve
        # only at evaluation time and have no stored coordinate to list.
        if row.version is None:
            continue
        identity = subject(row)
        if identity is not None and await readable(identity[0], identity[1]):
            items.append(
                CorporateCatalogUsage(
                    organization_id=organization_id,
                    assignment_id=row.id,
                    object_kind=query.object_kind,
                    stable_id=row.stable_id,
                    version=row.version,
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
                    version=row.version,
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


async def resolve_effective(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    query: CorporateEffectiveAssignmentQuery,
    request_id: str | None,
) -> CorporateEffectiveAssignment:
    """Evaluate the winning assignment for one employee and one catalog line.

    Deterministic order (ADR-0194): employee, project, technology, team,
    organization; inside one scope a harness-specific assignment outranks an
    unrestricted one; an explicit employee decision - current or retired -
    outranks every inherited assignment. `latest` resolves at evaluation time
    against the employee's eligible catalog versions and never rewrites stored
    assignments or materialized installations.
    """
    await service.read_member(
        db,
        ctx=ctx,
        organization_id=organization_id,
        account_id=query.account_id,
        request_id=request_id,
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
    team_ids = set(
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
                    CorporateTeamMember.account_id == query.account_id,
                    CorporateTeam.state == "active",
                )
            )
        ).all()
    )

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
                    account_id=ctx.account_id,
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
