"""Operational catalog assignments never mutate grants or harness state."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_contracts.corporate import (
    CorporateCatalogAssignment,
    CorporateCatalogAssignmentList,
    CorporateCatalogAssignmentQuery,
    CorporateCatalogAssignmentRequest,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog_read import get_visible_metadata
from ai_stp_platform.organization_models import (
    CorporateCatalogAssignment as AssignmentRow,
)
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateTeam,
    CorporateTeamMember,
    OrganizationMembership,
)


async def write_assignment(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateCatalogAssignmentRequest,
    request_id: str | None,
) -> CorporateCatalogAssignment:
    kind = payload.subject_kind
    scope_kind = "organization" if kind == "employee" else kind
    scope_id = organization_id if kind == "employee" else payload.subject_id
    permission = "member.manage" if kind == "employee" else f"{kind}.update"
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
        or catalog.lifecycle_state not in {"active", "deprecated"}
    ):
        raise ApiError(ErrorCategory.PERMISSION, "catalog version is unavailable")
    if receipt is not None:
        return CorporateCatalogAssignment.model_validate(receipt.response_body)
    model = {
        "employee": OrganizationMembership,
        "team": CorporateTeam,
        "project": CorporateProject,
    }[kind]
    identity = OrganizationMembership.account_id if kind == "employee" else model.id
    subject = await db.scalar(
        select(model).where(
            model.organization_id == organization_id, identity == payload.subject_id
        )
    )
    if subject is None or (payload.state == "current" and subject.state != "active"):
        raise ApiError(ErrorCategory.PERMISSION, "assignment subject is unavailable")
    column = {
        "employee": AssignmentRow.account_id,
        "team": AssignmentRow.team_id,
        "project": AssignmentRow.project_id,
    }[kind]
    row = await db.scalar(
        select(AssignmentRow).where(
            AssignmentRow.organization_id == organization_id,
            column == payload.subject_id,
            AssignmentRow.object_kind == payload.object_kind,
            AssignmentRow.stable_id == payload.stable_id,
            AssignmentRow.version == payload.version,
        )
    )
    if (row.revision if row else 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "assignment revision is stale")
    if row is None:
        row = AssignmentRow(
            id=new_id("operation"),
            organization_id=organization_id,
            object_kind=payload.object_kind,
            stable_id=payload.stable_id,
            version=payload.version,
            state=payload.state,
            revision=1,
        )
        setattr(
            row,
            {"employee": "account_id", "team": "team_id", "project": "project_id"}[kind],
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
        version=payload.version,
        state=payload.state,
        revision=row.revision,
    )
    if kind != "employee":
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
    if kind == "employee":
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
    else:
        await service.read_project(
            db,
            ctx=ctx,
            organization_id=organization_id,
            project_id=query.subject_id,
            request_id=request_id,
        )
    column = {
        "employee": AssignmentRow.account_id,
        "team": AssignmentRow.team_id,
        "project": AssignmentRow.project_id,
    }[kind]
    predicate = column == query.subject_id
    state_filter = AssignmentRow.state == "current"
    if query.include_retired:
        # Historical direct revisions support reassignment; retired team effects never propagate.
        state_filter = or_(state_filter, column == query.subject_id)
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
        catalog = await get_visible_metadata(
            db,
            object_kind=object_kind,
            stable_id=row.stable_id,
            version=row.version,
            account_id=ctx.account_id,
        )
        if (
            catalog is None
            or catalog.published_at is None
            or catalog.lifecycle_state not in {"active", "deprecated"}
        ):
            continue
        items.append(
            CorporateCatalogAssignment.model_validate(
                {
                    "assignment_id": row.id,
                    "organization_id": organization_id,
                    "subject_kind": kind,
                    "subject_id": query.subject_id,
                    "object_kind": row.object_kind,
                    "stable_id": row.stable_id,
                    "version": row.version,
                    "state": row.state,
                    "revision": row.revision,
                    "source_team_id": row.team_id if kind == "employee" else None,
                    "display_name": catalog.name,
                }
            )
        )
    return CorporateCatalogAssignmentList(
        items=items[query.offset : query.offset + query.limit], total=len(items)
    )
