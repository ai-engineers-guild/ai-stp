"""Tenant employee profile edits are independent of access administration."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_contracts.corporate import CorporateMember, CorporateMemberProfileRequest
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import OrganizationMembership


async def update_member_profile(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    account_id: str,
    payload: CorporateMemberProfileRequest,
    request_id: str | None,
) -> CorporateMember:
    fingerprint = service.mutation_fingerprint(
        {"account_id": account_id, **payload.model_dump(mode="json", exclude={"idempotency_key"})}
    )
    _, receipt = await service.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.update",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="member.profile.update",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateMember.model_validate(receipt.response_body)
    row = await db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.account_id == account_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "member is unavailable")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "member revision is stale")
    account = await db.get(Account, account_id)
    if account is None:
        raise ApiError(ErrorCategory.PERMISSION, "member is unavailable")
    row.display_name = payload.display_name.strip()
    row.revision += 1
    await db.flush()
    response = service.member_view(row, account)
    await service.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="member.profile.update",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="member.profile.update",
        target_table="organization_membership",
        target_id=str(row.id),
        request_id=request_id,
    )
    return response
