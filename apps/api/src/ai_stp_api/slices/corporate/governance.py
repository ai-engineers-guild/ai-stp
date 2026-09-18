"""Tenant catalog governance relations; global publication facts stay untouched."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import catalog_ownership, service
from ai_stp_contracts.corporate import CorporateAuditEntry, OrganizationId
from ai_stp_contracts.corporate_catalog_ownership import CorporateCatalogOwnershipQuery
from ai_stp_contracts.corporate_governance import (
    CorporateCatalogGovernanceQuery,
    CorporateCatalogGovernanceView,
    CorporateCatalogLifecycle,
    CorporateCatalogLifecycleRequest,
    CorporateCatalogMaintainer,
    CorporateCatalogMaintainerRequest,
    CorporateCatalogVerification,
    CorporateCatalogVerificationRequest,
    CorporateGovernanceTarget,
)
from ai_stp_platform.catalog_read import get_visible_metadata
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.models import AuditEvent
from ai_stp_platform.organization_models import (
    CorporateCatalogAssignment as AssignmentRow,
)
from ai_stp_platform.organization_models import (
    CorporateCatalogLifecycle as LifecycleRow,
)
from ai_stp_platform.organization_models import (
    CorporateCatalogMaintainer as MaintainerRow,
)
from ai_stp_platform.organization_models import (
    CorporateCatalogVerification as VerificationRow,
)
from ai_stp_platform.organization_models import (
    CorporateTeam,
    OrganizationMembership,
)

router = APIRouter(tags=["corporate"])

_LIFECYCLE_TRANSITIONS: dict[str | None, frozenset[str]] = {
    None: frozenset({"visible"}),
    "visible": frozenset({"visible", "hidden", "deprecated", "retired"}),
    "hidden": frozenset({"hidden", "visible", "retired"}),
    "deprecated": frozenset({"deprecated", "visible", "retired"}),
    "retired": frozenset({"retired", "visible"}),
}


def validate_lifecycle_transition(previous: str | None, next_state: str) -> None:
    if next_state not in _LIFECYCLE_TRANSITIONS[previous]:
        raise ApiError(ErrorCategory.CONFLICT, "catalog lifecycle transition is not allowed")


async def _catalog(db: AsyncSession, *, target: CorporateGovernanceTarget, account_id: str) -> None:
    row = await get_visible_metadata(
        db,
        object_kind=target.object_kind,
        stable_id=target.stable_id,
        version=target.version,
        account_id=account_id,
    )
    if (
        row is None
        or row.published_at is None
        or row.lifecycle_state
        not in {
            "active",
            "deprecated",
        }
    ):
        raise ApiError(ErrorCategory.PERMISSION, "catalog version is unavailable")


async def _authorize(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    target: CorporateGovernanceTarget,
    permission: str,
    authorization_revision: int,
    idempotency_key: str,
    fingerprint: str,
    operation: str,
    request_id: str | None,
):
    return await service.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=permission,
        scope_kind="catalog_object",
        scope_id=target.stable_id,
        authorization_revision=authorization_revision,
        idempotency_key=idempotency_key,
        operation=operation,
        fingerprint=fingerprint,
        request_id=request_id,
    )


async def write_maintainer(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateCatalogMaintainerRequest,
    request_id: str | None,
) -> CorporateCatalogMaintainer:
    fingerprint = service.mutation_fingerprint(
        payload.model_dump(mode="json", exclude={"idempotency_key"})
    )
    _, receipt = await _authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        target=payload,
        permission="catalog_object.maintainer",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        fingerprint=fingerprint,
        operation="catalog_maintainer.write",
        request_id=request_id,
    )
    await _catalog(db, target=payload, account_id=ctx.account_id)
    if receipt is not None:
        return CorporateCatalogMaintainer.model_validate(receipt.response_body)
    subject_model = OrganizationMembership if payload.subject_kind == "employee" else CorporateTeam
    subject_column = (
        OrganizationMembership.account_id
        if payload.subject_kind == "employee"
        else CorporateTeam.id
    )
    subject = await db.scalar(
        select(subject_model).where(
            subject_model.organization_id == organization_id,
            subject_column == payload.subject_id,
        )
    )
    if subject is None or (
        payload.state == "current" and getattr(subject, "state", None) != "active"
    ):
        raise ApiError(ErrorCategory.PERMISSION, "maintainer subject is unavailable")
    row = await db.get(
        MaintainerRow,
        (
            organization_id,
            payload.object_kind,
            payload.stable_id,
            payload.version,
            payload.subject_kind,
            payload.subject_id,
        ),
    )
    if (row.revision if row else 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "maintainer revision is stale")
    if row is None:
        row = MaintainerRow(
            organization_id=organization_id,
            object_kind=payload.object_kind,
            stable_id=payload.stable_id,
            version=payload.version,
            subject_kind=payload.subject_kind,
            subject_id=payload.subject_id,
            state=payload.state,
            revision=1,
            actor_account_id=ctx.account_id,
            reason=payload.reason,
        )
        db.add(row)
    else:
        row.state = payload.state
        row.revision += 1
        row.actor_account_id = ctx.account_id
        row.reason = payload.reason
    await db.flush()
    response = CorporateCatalogMaintainer(
        organization_id=organization_id,
        object_kind=payload.object_kind,
        stable_id=payload.stable_id,
        version=payload.version,
        subject_kind=payload.subject_kind,
        subject_id=payload.subject_id,
        state=payload.state,
        revision=row.revision,
        reason=payload.reason,
    )
    await service.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="catalog_maintainer.write",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="catalog_maintainer.write",
        target_table="corporate_catalog_maintainer",
        target_id=payload.stable_id,
        request_id=request_id,
        payload={
            "subject_kind": payload.subject_kind,
            "subject_id": payload.subject_id,
            "state": payload.state,
        },
    )
    return response


async def write_verification(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateCatalogVerificationRequest,
    request_id: str | None,
) -> CorporateCatalogVerification:
    fingerprint = service.mutation_fingerprint(
        payload.model_dump(mode="json", exclude={"idempotency_key"})
    )
    _, receipt = await _authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        target=payload,
        permission="catalog_object.verify",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        fingerprint=fingerprint,
        operation="catalog_verification.write",
        request_id=request_id,
    )
    await _catalog(db, target=payload, account_id=ctx.account_id)
    if receipt is not None:
        return CorporateCatalogVerification.model_validate(receipt.response_body)
    row = await db.get(
        VerificationRow,
        (organization_id, payload.object_kind, payload.stable_id, payload.version),
    )
    if (row.revision if row else 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "verification revision is stale")
    if row is None:
        row = VerificationRow(
            organization_id=organization_id,
            object_kind=payload.object_kind,
            stable_id=payload.stable_id,
            version=payload.version,
            state=payload.state,
            revision=1,
            verified_by_account_id=ctx.account_id if payload.state == "verified" else None,
            reason=payload.reason,
        )
        db.add(row)
    else:
        row.state = payload.state
        row.revision += 1
        row.verified_by_account_id = ctx.account_id if payload.state == "verified" else None
        row.reason = payload.reason
    await db.flush()
    response = CorporateCatalogVerification(
        organization_id=organization_id,
        object_kind=payload.object_kind,
        stable_id=payload.stable_id,
        version=payload.version,
        state=payload.state,
        revision=row.revision,
        verified_by_account_id=row.verified_by_account_id,
        reason=row.reason,
    )
    await service.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="catalog_verification.write",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="catalog_verification.write",
        target_table="corporate_catalog_verification",
        target_id=payload.stable_id,
        request_id=request_id,
        payload={"version": payload.version, "state": payload.state, "reason": payload.reason},
    )
    return response


async def write_lifecycle(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateCatalogLifecycleRequest,
    request_id: str | None,
) -> CorporateCatalogLifecycle:
    fingerprint = service.mutation_fingerprint(
        payload.model_dump(mode="json", exclude={"idempotency_key"})
    )
    _, receipt = await _authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        target=payload,
        permission="catalog_object.lifecycle",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        fingerprint=fingerprint,
        operation="catalog_lifecycle.write",
        request_id=request_id,
    )
    await _catalog(db, target=payload, account_id=ctx.account_id)
    if receipt is not None:
        return CorporateCatalogLifecycle.model_validate(receipt.response_body)
    row = await db.get(
        LifecycleRow,
        (organization_id, payload.object_kind, payload.stable_id, payload.version),
    )
    if (row.revision if row else 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "lifecycle revision is stale")
    validate_lifecycle_transition(row.state if row else None, payload.state)
    if row is None:
        row = LifecycleRow(
            organization_id=organization_id,
            object_kind=payload.object_kind,
            stable_id=payload.stable_id,
            version=payload.version,
            state=payload.state,
            revision=1,
            actor_account_id=ctx.account_id,
            reason=payload.reason,
        )
        db.add(row)
    else:
        row.state = payload.state
        row.revision += 1
        row.actor_account_id = ctx.account_id
        row.reason = payload.reason
    await db.flush()
    response = CorporateCatalogLifecycle(
        organization_id=organization_id,
        object_kind=payload.object_kind,
        stable_id=payload.stable_id,
        version=payload.version,
        state=payload.state,
        revision=row.revision,
        reason=row.reason,
    )
    await service.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="catalog_lifecycle.write",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="catalog_lifecycle.write",
        target_table="corporate_catalog_lifecycle",
        target_id=payload.stable_id,
        request_id=request_id,
        payload={"version": payload.version, "state": payload.state, "reason": payload.reason},
    )
    return response


async def read_governance(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    object_kind: Literal["setup", "component"],
    stable_id: str,
    version: str,
    query: CorporateCatalogGovernanceQuery,
    request_id: str | None,
) -> CorporateCatalogGovernanceView:
    try:
        target = CorporateGovernanceTarget(
            object_kind=object_kind, stable_id=stable_id, version=version
        )
    except ValidationError as exc:
        raise ApiError(ErrorCategory.VALIDATION, "catalog identity is invalid") from exc
    await service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="catalog_object.read",
        scope_kind="catalog_object",
        scope_id=stable_id,
    )
    await _catalog(db, target=target, account_id=ctx.account_id)
    ownership = await catalog_ownership.read_ownership(
        db,
        ctx=ctx,
        organization_id=organization_id,
        subject=CorporateCatalogOwnershipQuery.model_validate(target.model_dump()),
        request_id=request_id,
    )
    maintainer_query = select(MaintainerRow).where(
        MaintainerRow.organization_id == organization_id,
        MaintainerRow.object_kind == object_kind,
        MaintainerRow.stable_id == stable_id,
        MaintainerRow.version == version,
    )
    if not query.include_retired:
        maintainer_query = maintainer_query.where(MaintainerRow.state == "current")
    maintainer_rows = list(
        (
            await db.scalars(
                maintainer_query.order_by(MaintainerRow.subject_kind, MaintainerRow.subject_id)
            )
        ).all()
    )
    maintainers = [
        CorporateCatalogMaintainer(
            organization_id=row.organization_id,
            object_kind=object_kind,
            stable_id=stable_id,
            version=version,
            subject_kind=cast(Literal["employee", "team"], row.subject_kind),
            subject_id=row.subject_id,
            state=cast(Literal["current", "retired"], row.state),
            revision=row.revision,
            reason=row.reason,
        )
        for row in maintainer_rows
    ]
    verification_row = await db.get(
        VerificationRow, (organization_id, object_kind, stable_id, version)
    )
    verification = (
        CorporateCatalogVerification(
            organization_id=verification_row.organization_id,
            object_kind=object_kind,
            stable_id=stable_id,
            version=version,
            state=cast(Literal["verified", "revoked"], verification_row.state),
            revision=verification_row.revision,
            verified_by_account_id=verification_row.verified_by_account_id,
            reason=verification_row.reason,
        )
        if verification_row is not None
        and (query.include_retired or verification_row.state == "verified")
        else None
    )
    lifecycle_row = await db.get(LifecycleRow, (organization_id, object_kind, stable_id, version))
    lifecycle = (
        CorporateCatalogLifecycle(
            organization_id=lifecycle_row.organization_id,
            object_kind=object_kind,
            stable_id=stable_id,
            version=version,
            state=cast(Literal["visible", "hidden", "deprecated", "retired"], lifecycle_row.state),
            revision=lifecycle_row.revision,
            reason=lifecycle_row.reason,
        )
        if lifecycle_row is not None and (query.include_retired or lifecycle_row.state != "retired")
        else None
    )
    history: list[CorporateAuditEntry] = []
    if query.include_history:
        await service.authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission="catalog_object.audit",
            scope_kind="catalog_object",
            scope_id=stable_id,
        )
        assignment_ids = select(AssignmentRow.id).where(
            AssignmentRow.organization_id == organization_id,
            AssignmentRow.object_kind == object_kind,
            AssignmentRow.stable_id == stable_id,
            AssignmentRow.version == version,
        )
        history_rows = list(
            (
                await db.scalars(
                    select(AuditEvent)
                    .where(
                        AuditEvent.organization_id == organization_id,
                        AuditEvent.target_table.in_(
                            (
                                "corporate_catalog_ownership",
                                "corporate_catalog_assignment",
                                "corporate_catalog_maintainer",
                                "corporate_catalog_verification",
                                "corporate_catalog_lifecycle",
                            )
                        ),
                        (AuditEvent.target_id == stable_id)
                        | AuditEvent.target_id.in_(assignment_ids),
                    )
                    .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                    .limit(256)
                )
            ).all()
        )
        history = [service.audit_entry(row) for row in history_rows]
    available_actions = [
        action
        for action, permission in (
            ("ownership.transfer", "catalog_object.ownership_transfer"),
            ("maintainer.manage", "catalog_object.maintainer"),
            ("verification.manage", "catalog_object.verify"),
            ("lifecycle.manage", "catalog_object.lifecycle"),
            ("assignment.manage", "catalog_object.assign"),
            ("audit.explain", "catalog_object.explain"),
        )
        if await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=ctx.account_id,
            permission=permission,
            scope_kind="catalog_object",
            scope_id=stable_id,
        )
    ]
    return CorporateCatalogGovernanceView(
        organization_id=organization_id,
        object_kind=object_kind,
        stable_id=stable_id,
        version=version,
        ownership=ownership,
        maintainers=maintainers,
        verification=verification,
        lifecycle=lifecycle,
        history=history,
        available_actions=available_actions,
    )


@router.put(
    "/corporate/organizations/{organization_id}/catalog-governance/maintainers",
    response_model=CorporateCatalogMaintainer,
)
async def put_maintainer(
    organization_id: OrganizationId,
    payload: CorporateCatalogMaintainerRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateCatalogMaintainer:
    return await write_maintainer(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.put(
    "/corporate/organizations/{organization_id}/catalog-governance/verification",
    response_model=CorporateCatalogVerification,
)
async def put_verification(
    organization_id: OrganizationId,
    payload: CorporateCatalogVerificationRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateCatalogVerification:
    return await write_verification(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.put(
    "/corporate/organizations/{organization_id}/catalog-governance/lifecycle",
    response_model=CorporateCatalogLifecycle,
)
async def put_lifecycle(
    organization_id: OrganizationId,
    payload: CorporateCatalogLifecycleRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateCatalogLifecycle:
    return await write_lifecycle(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get(
    "/corporate/organizations/{organization_id}/catalog-governance/{object_kind}/{stable_id}/versions/{version}",
    response_model=CorporateCatalogGovernanceView,
)
async def get_governance(
    organization_id: OrganizationId,
    object_kind: Literal["setup", "component"],
    stable_id: str,
    version: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    include_retired: Annotated[bool, Query()] = False,
    include_history: Annotated[bool, Query()] = False,
) -> CorporateCatalogGovernanceView:
    return await read_governance(
        db,
        ctx=ctx,
        organization_id=organization_id,
        object_kind=object_kind,
        stable_id=stable_id,
        version=version,
        query=CorporateCatalogGovernanceQuery(
            include_retired=include_retired, include_history=include_history
        ),
        request_id=getattr(request.state, "request_id", None),
    )
