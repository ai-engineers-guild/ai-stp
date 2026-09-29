"""Organization membership invitations and the email-domain allowlist (#201).

One raw token exists only in the create response; at rest it is a SHA-256
hash, and the mutation receipt stores the view without the secret.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, NoReturn, cast

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.auth.domain import normalize_email
from ai_stp_api.slices.corporate.service import (
    assert_email_domain_allowed,
    authorize,
    authorize_idempotent,
    email_domain_allowed,
    ensure_active_projects,
    ensure_active_teams,
    ensure_current_job_title,
    ensure_role_exists,
    insert_membership_graph,
    member_view,
    mutation_fingerprint,
    store_mutation_receipt,
)
from ai_stp_contracts.corporate import (
    CorporateInvitation,
    CorporateInvitationAcceptRequest,
    CorporateInvitationCreateRequest,
    CorporateInvitationList,
    CorporateInvitationRevokeRequest,
    CorporateInvitationState,
    CorporateMailDeliveryState,
    CorporateMember,
    CorporateMembershipPolicy,
    CorporateMembershipPolicyRequest,
)
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.models import Account, OAuthIdentity
from ai_stp_platform.organization_models import (
    CorporateInvitation as CorporateInvitationRow,
)
from ai_stp_platform.organization_models import (
    CorporateMailDelivery,
    CorporateProvisionedIdentity,
    Organization,
    OrganizationMembership,
)
from ai_stp_platform.queue.engine import enqueue
from ai_stp_platform.queue.states import JobType

router = APIRouter(tags=["corporate"])

_DOMAIN = re.compile(
    r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _ts(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return format_timestamp(value)


def _expired(row: CorporateInvitationRow) -> bool:
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    return row.state in ("pending", "email_confirm_pending") and expires <= datetime.now(UTC)


def _view(
    row: CorporateInvitationRow,
    *,
    token: str | None = None,
    delivery: CorporateMailDelivery | None = None,
) -> CorporateInvitation:
    state = "expired" if _expired(row) else row.state
    return CorporateInvitation(
        schema_version=1,
        invitation_id=row.id,
        organization_id=row.organization_id,
        recipient_email=row.recipient_email_normalized,
        display_name=row.display_name,
        role=row.role,
        team_ids=list(row.team_ids or []),
        project_ids=list(row.project_ids or []),
        job_title_id=row.job_title_id,
        state=cast(CorporateInvitationState, state),
        expires_at=_ts(row.expires_at),
        created_at=_ts(row.created_at),
        accepted_account_id=row.accepted_account_id,
        claimant_account_id=row.claimant_account_id,
        token=token,
        delivery_state=cast(
            CorporateMailDeliveryState | None, delivery.state if delivery else None
        ),
        delivery_error=delivery.error if delivery else None,
    )


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_domains(values: list[str]) -> list[str]:
    domains = sorted(
        {item.strip().lower().lstrip("@.").rstrip(".") for item in values if item.strip()}
    )
    if any(_DOMAIN.fullmatch(item) is None for item in domains):
        raise ApiError(ErrorCategory.VALIDATION, "invalid email domain")
    return domains


async def _invitation(
    db: AsyncSession, *, organization_id: str, invitation_id: str
) -> CorporateInvitationRow:
    row = await db.get(CorporateInvitationRow, invitation_id)
    if row is None or row.organization_id != organization_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "invitation not found")
    return row


async def _reject(
    db: AsyncSession,
    *,
    row: CorporateInvitationRow | None,
    ctx: AuthContext,
    request_id: str | None,
    action: str,
    category: ErrorCategory,
    message: str,
) -> NoReturn:
    if row is not None:
        # The request session rolls back once ApiError propagates, so the
        # failure audit is committed before the raise — the row itself is
        # only locked, never mutated on this path.
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            organization_id=row.organization_id,
            action=action,
            target_table="corporate_invitation",
            target_id=row.id,
            outcome="failed",
            request_id=request_id,
        )
        await db.commit()
    raise ApiError(category, message)


async def _expire(
    db: AsyncSession,
    *,
    row: CorporateInvitationRow,
    ctx: AuthContext,
    request_id: str | None,
) -> NoReturn:
    row.state = "expired"
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=row.organization_id,
        action="member.invitation_expired",
        target_table="corporate_invitation",
        target_id=row.id,
        request_id=request_id,
    )
    await db.commit()
    raise ApiError(ErrorCategory.VALIDATION, "invitation expired")


async def _require_organization(
    db: AsyncSession,
    *,
    row: CorporateInvitationRow,
    ctx: AuthContext,
    request_id: str | None,
) -> Organization:
    organization = await db.get(Organization, row.organization_id)
    if organization is None or organization.state != "active":
        await _reject(
            db,
            row=row,
            ctx=ctx,
            request_id=request_id,
            action="member.invitation_org_inactive",
            category=ErrorCategory.CONFLICT,
            message="organization is unavailable",
        )
    if not email_domain_allowed(
        list(organization.allowed_email_domains or []), row.recipient_email_normalized
    ):
        await _reject(
            db,
            row=row,
            ctx=ctx,
            request_id=request_id,
            action="member.invitation_domain_rejected",
            category=ErrorCategory.VALIDATION,
            message="email domain is not allowed",
        )
    return organization


async def _accepted_member(
    db: AsyncSession, *, row: CorporateInvitationRow, ctx: AuthContext
) -> CorporateMember | None:
    if row.state != "accepted" or row.accepted_account_id != ctx.account_id:
        return None
    membership = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == row.organization_id,
            OrganizationMembership.account_id == ctx.account_id,
        )
    )
    account = await db.get(Account, ctx.account_id)
    if membership is None or account is None:
        return None
    return member_view(membership, account)


async def _send_confirmation(
    db: AsyncSession,
    *,
    row: CorporateInvitationRow,
    organization: Organization,
    ctx: AuthContext,
    request_id: str | None,
) -> NoReturn:
    """Bind the claimant and mail a confirmation token to the invited address.

    The invited inbox — not the sign-in provider — proves ownership, so any
    OAuth or SSO identity may claim the invitation. The confirmation token is
    hashed at rest and never leaves the mail pipeline in the ledger.
    """
    confirm_token = secrets.token_urlsafe(32)
    row.state = "email_confirm_pending"
    row.claimant_account_id = ctx.account_id
    row.confirmation_token_hash = _hash(confirm_token)
    # The ledger keeps one row per invitation: a resend resets it to queued so
    # admins always see the latest mail state; past jobs keep the history.
    delivery = await db.scalar(
        select(CorporateMailDelivery).where(CorporateMailDelivery.invitation_id == row.id)
    )
    if delivery is None:
        delivery = CorporateMailDelivery(
            id=new_id("mail"),
            organization_id=row.organization_id,
            invitation_id=row.id,
            to_email_normalized=row.recipient_email_normalized,
            display_name=row.display_name,
            template_key="",
            state="queued",
        )
        db.add(delivery)
    else:
        delivery.state = "queued"
        delivery.error = None
        delivery.provider_message_id = None
        delivery.sent_at = None
    await enqueue(
        db,
        job_type=JobType.DELIVER_CORPORATE_INVITATION,
        payload={
            "delivery_id": delivery.id,
            "invitation_id": row.id,
            "to_email": row.recipient_email_normalized,
            "display_name": row.display_name,
            "organization_name": organization.display_name,
            "role": row.role,
            "expires_at": _ts(row.expires_at),
            "mail_variant": "confirmation",
            # Same secrecy rule as accept_token: payload only until delivery.
            "confirm_token": confirm_token,
        },
        # Each send gets a unique key: the same delivery row may be resent.
        idempotency_key=f"deliver_corporate_invitation:{delivery.id}:{secrets.token_hex(8)}",
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=row.organization_id,
        action="member.invitation_email_confirm_sent",
        target_table="corporate_invitation",
        target_id=row.id,
        request_id=request_id,
    )
    await db.commit()
    raise ApiError(
        ErrorCategory.CONFLICT,
        "confirmation email sent to the invited address",
        details={"reason": "email_confirmation_sent"},
    )


async def _activate_membership(
    db: AsyncSession,
    *,
    row: CorporateInvitationRow,
    ctx: AuthContext,
    request_id: str | None,
) -> OrganizationMembership:
    existing = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == row.organization_id,
            OrganizationMembership.account_id == ctx.account_id,
        )
    )
    if existing is not None:
        await _reject(
            db,
            row=row,
            ctx=ctx,
            request_id=request_id,
            action="member.invitation_duplicate",
            category=ErrorCategory.CONFLICT,
            message="member already exists",
        )

    await ensure_active_teams(
        db, organization_id=row.organization_id, team_ids=list(row.team_ids or [])
    )
    await ensure_active_projects(
        db, organization_id=row.organization_id, project_ids=list(row.project_ids or [])
    )
    await ensure_current_job_title(
        db, organization_id=row.organization_id, job_title_id=row.job_title_id
    )
    membership = await insert_membership_graph(
        db,
        organization_id=row.organization_id,
        account_id=ctx.account_id,
        display_name=row.display_name,
        role=row.role,
        team_ids=list(row.team_ids or []),
        project_ids=list(row.project_ids or []),
        job_title_id=row.job_title_id,
    )
    try:
        async with db.begin_nested():
            db.add(
                CorporateProvisionedIdentity(
                    organization_id=row.organization_id,
                    normalized_email=row.recipient_email_normalized,
                    account_id=ctx.account_id,
                )
            )
            await db.flush()
    except IntegrityError:
        # The email is already provisioned elsewhere; membership still stands.
        pass
    row.state = "accepted"
    row.accepted_account_id = ctx.account_id
    row.confirmation_token_hash = None
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=row.organization_id,
        action="member.invitation_accepted",
        target_table="corporate_invitation",
        target_id=row.id,
        request_id=request_id,
    )
    await db.flush()
    return membership


@router.post(
    "/corporate/organizations/{organization_id}/invitations",
    response_model=CorporateInvitation,
)
async def create_invitation(
    organization_id: str,
    payload: CorporateInvitationCreateRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateInvitation:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.invite",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="member.invitation.create",
        fingerprint=fingerprint,
        request_id=_request_id(request),
    )
    if receipt is not None:
        return CorporateInvitation.model_validate(receipt.response_body)
    await ensure_active_teams(db, organization_id=organization_id, team_ids=payload.team_ids)
    await ensure_active_projects(
        db, organization_id=organization_id, project_ids=payload.project_ids
    )
    await ensure_role_exists(db, organization_id=organization_id, role=payload.role)
    await ensure_current_job_title(
        db, organization_id=organization_id, job_title_id=payload.job_title_id
    )
    assert_email_domain_allowed(organization, payload.recipient_email)
    normalized_email = normalize_email(payload.recipient_email)
    if await db.scalar(
        select(OrganizationMembership.id)
        .join(
            CorporateProvisionedIdentity,
            CorporateProvisionedIdentity.account_id == OrganizationMembership.account_id,
        )
        .where(
            OrganizationMembership.organization_id == organization_id,
            CorporateProvisionedIdentity.normalized_email == normalized_email,
        )
    ):
        raise ApiError(ErrorCategory.CONFLICT, "member already exists")
    joined_accounts = select(OAuthIdentity.account_id).where(
        OAuthIdentity.state == "linked",
        func.lower(OAuthIdentity.email) == normalized_email,
    )
    if await db.scalar(
        select(OrganizationMembership.id).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.account_id.in_(joined_accounts),
        )
    ):
        raise ApiError(ErrorCategory.CONFLICT, "member already exists")
    token = secrets.token_urlsafe(32)
    ttl_seconds = (
        payload.ttl_seconds
        if payload.ttl_seconds is not None
        else request.app.state.settings.corporate.invitation_ttl_seconds
    )
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    row = CorporateInvitationRow(
        id=new_id("invite"),
        organization_id=organization_id,
        issuer_account_id=ctx.account_id,
        recipient_email_normalized=normalized_email,
        display_name=payload.display_name.strip(),
        role=payload.role,
        team_ids=list(dict.fromkeys(payload.team_ids)),
        project_ids=list(dict.fromkeys(payload.project_ids)),
        job_title_id=payload.job_title_id,
        token_hash=_hash(token),
        state="pending",
        idempotency_key=payload.idempotency_key,
        expires_at=expires_at,
    )
    db.add(row)
    delivery = CorporateMailDelivery(
        id=new_id("mail"),
        organization_id=organization_id,
        invitation_id=row.id,
        to_email_normalized=normalized_email,
        display_name=row.display_name,
        template_key="",
        state="queued",
    )
    db.add(delivery)
    await enqueue(
        db,
        job_type=JobType.DELIVER_CORPORATE_INVITATION,
        payload={
            "delivery_id": delivery.id,
            "invitation_id": row.id,
            "to_email": normalized_email,
            "display_name": row.display_name,
            "organization_name": organization.display_name,
            "role": row.role,
            "expires_at": _ts(expires_at),
            # Token travels only in the job payload until delivered; the
            # ledger and the audit trail never see it.
            "accept_token": token,
        },
        idempotency_key=f"deliver_corporate_invitation:{row.id}",
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="member.invitation_created",
        target_table="corporate_invitation",
        target_id=row.id,
        request_id=_request_id(request),
        payload={"role": row.role},
    )
    await db.flush()
    # The receipt stores everything but the secret: a replayed create answers
    # the same view while the raw token stays non-recoverable.
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="member.invitation.create",
        fingerprint=fingerprint,
        response=_view(row, delivery=delivery),
    )
    return _view(row, token=token, delivery=delivery)


@router.get(
    "/corporate/organizations/{organization_id}/invitations",
    response_model=CorporateInvitationList,
)
async def list_invitations(
    organization_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateInvitationList:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="member.invite")
    rows = (
        (
            await db.execute(
                select(CorporateInvitationRow)
                .where(CorporateInvitationRow.organization_id == organization_id)
                .order_by(CorporateInvitationRow.created_at.desc())
                .limit(256)
            )
        )
        .scalars()
        .all()
    )
    deliveries = (
        (
            await db.execute(
                select(CorporateMailDelivery).where(
                    CorporateMailDelivery.invitation_id.in_([row.id for row in rows])
                )
            )
        )
        .scalars()
        .all()
    )
    by_invitation = {delivery.invitation_id: delivery for delivery in deliveries}
    return CorporateInvitationList(
        items=[_view(row, delivery=by_invitation.get(row.id)) for row in rows]
    )


@router.post(
    "/corporate/organizations/{organization_id}/invitations/{invitation_id}/revoke",
    response_model=CorporateInvitation,
)
async def revoke_invitation(
    organization_id: str,
    invitation_id: str,
    payload: CorporateInvitationRevokeRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateInvitation:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.invite",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="member.invitation.revoke",
        fingerprint=fingerprint,
        request_id=_request_id(request),
    )
    if receipt is not None:
        return CorporateInvitation.model_validate(receipt.response_body)
    row = await _invitation(db, organization_id=organization.id, invitation_id=invitation_id)
    if row.state == "pending":
        row.state = "revoked"
        row.revoked_at = datetime.now(UTC)
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            organization_id=organization.id,
            action="member.invitation_revoked",
            target_table="corporate_invitation",
            target_id=row.id,
            reason=payload.reason or None,
            request_id=_request_id(request),
        )
        await db.flush()
    response = _view(row)
    await store_mutation_receipt(
        db,
        organization_id=organization.id,
        key=payload.idempotency_key,
        operation="member.invitation.revoke",
        fingerprint=fingerprint,
        response=response,
    )
    return response


@router.post("/corporate/invitations/{invitation_id}/accept", response_model=CorporateMember)
async def accept_invitation(
    invitation_id: str,
    payload: CorporateInvitationAcceptRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateMember:
    request_id = _request_id(request)
    row = await db.get(CorporateInvitationRow, invitation_id, with_for_update=True)

    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "invitation not found")
    if accepted := await _accepted_member(db, row=row, ctx=ctx):
        return accepted
    if row.state == "email_confirm_pending":
        # A claim already bound the invitation to one account: re-accept by the
        # same claimant resends the confirmation mail; anyone else is denied.
        if row.claimant_account_id != ctx.account_id:
            await _reject(
                db,
                row=row,
                ctx=ctx,
                request_id=request_id,
                action="member.invitation_claimed",
                category=ErrorCategory.CONFLICT,
                message="invitation is claimed by another account",
            )
        if _expired(row):
            await _expire(db, row=row, ctx=ctx, request_id=request_id)
        if _hash(payload.token) != row.token_hash:
            await _reject(
                db,
                row=row,
                ctx=ctx,
                request_id=request_id,
                action="member.invitation_token_invalid",
                category=ErrorCategory.VALIDATION,
                message="invitation token invalid",
            )
        organization = await _require_organization(db, row=row, ctx=ctx, request_id=request_id)
        await _send_confirmation(
            db, row=row, organization=organization, ctx=ctx, request_id=request_id
        )
    if row.state != "pending":
        await _reject(
            db,
            row=row,
            ctx=ctx,
            request_id=request_id,
            action="member.invitation_replayed",
            category=ErrorCategory.CONFLICT,
            message=f"invitation is {row.state}",
        )
    if _expired(row):
        await _expire(db, row=row, ctx=ctx, request_id=request_id)
    if _hash(payload.token) != row.token_hash:
        await _reject(
            db,
            row=row,
            ctx=ctx,
            request_id=request_id,
            action="member.invitation_token_invalid",
            category=ErrorCategory.VALIDATION,
            message="invitation token invalid",
        )

    organization = await _require_organization(db, row=row, ctx=ctx, request_id=request_id)

    emails = {
        normalize_email(identity.email)
        for identity in (
            await db.execute(
                select(OAuthIdentity).where(
                    OAuthIdentity.account_id == ctx.account_id,
                    OAuthIdentity.state == "linked",
                    OAuthIdentity.email_verified.is_(True),
                )
            )
        )
        .scalars()
        .all()
    }
    if row.recipient_email_normalized not in emails:
        # Not a dead end: bind the claimant and prove the invited inbox by mail.
        await _send_confirmation(
            db, row=row, organization=organization, ctx=ctx, request_id=request_id
        )

    membership = await _activate_membership(db, row=row, ctx=ctx, request_id=request_id)
    account = cast(Account, await db.get(Account, ctx.account_id))
    return member_view(membership, account)


@router.post("/corporate/invitations/{invitation_id}/confirm", response_model=CorporateMember)
async def confirm_invitation(
    invitation_id: str,
    payload: CorporateInvitationAcceptRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateMember:
    """Activate a claimed invitation after the invited inbox proves ownership.

    The confirmation token lives in the emailed link's fragment; only the
    account that claimed the invitation may redeem it.
    """
    request_id = _request_id(request)
    row = await db.get(CorporateInvitationRow, invitation_id, with_for_update=True)

    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "invitation not found")
    if accepted := await _accepted_member(db, row=row, ctx=ctx):
        return accepted
    if row.state != "email_confirm_pending":
        await _reject(
            db,
            row=row,
            ctx=ctx,
            request_id=request_id,
            action="member.invitation_replayed",
            category=ErrorCategory.CONFLICT,
            message=f"invitation is {row.state}",
        )
    if _expired(row):
        await _expire(db, row=row, ctx=ctx, request_id=request_id)
    if row.claimant_account_id != ctx.account_id:
        await _reject(
            db,
            row=row,
            ctx=ctx,
            request_id=request_id,
            action="member.invitation_confirm_account_mismatch",
            category=ErrorCategory.CONFLICT,
            message="signed-in account did not claim the invitation",
        )
    if not row.confirmation_token_hash or _hash(payload.token) != row.confirmation_token_hash:
        await _reject(
            db,
            row=row,
            ctx=ctx,
            request_id=request_id,
            action="member.invitation_confirm_token_invalid",
            category=ErrorCategory.VALIDATION,
            message="confirmation token invalid",
        )
    await _require_organization(db, row=row, ctx=ctx, request_id=request_id)
    membership = await _activate_membership(db, row=row, ctx=ctx, request_id=request_id)
    account = cast(Account, await db.get(Account, ctx.account_id))
    return member_view(membership, account)


@router.get(
    "/corporate/organizations/{organization_id}/membership/policy",
    response_model=CorporateMembershipPolicy,
)
async def read_membership_policy(
    organization_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateMembershipPolicy:
    organization, _membership = await authorize(
        db, ctx=ctx, organization_id=organization_id, permission="organization.read"
    )
    return CorporateMembershipPolicy(
        organization_id=organization.id,
        allowed_email_domains=list(organization.allowed_email_domains or []),
        authorization_revision=organization.policy_revision,
    )


@router.put(
    "/corporate/organizations/{organization_id}/membership/policy",
    response_model=CorporateMembershipPolicy,
)
async def write_membership_policy(
    organization_id: str,
    payload: CorporateMembershipPolicyRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> CorporateMembershipPolicy:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="organization.manage",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="membership.policy.write",
        fingerprint=fingerprint,
        request_id=_request_id(request),
    )
    if receipt is not None:
        return CorporateMembershipPolicy.model_validate(receipt.response_body)
    organization.allowed_email_domains = _normalize_domains(payload.allowed_email_domains)
    organization.policy_revision += 1
    response = CorporateMembershipPolicy(
        organization_id=organization.id,
        allowed_email_domains=list(organization.allowed_email_domains),
        authorization_revision=organization.policy_revision,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization.id,
        action="membership.policy.write",
        target_table="organization",
        target_id=organization.id,
        request_id=_request_id(request),
        payload={"allowed_email_domains": response.allowed_email_domains},
    )
    await store_mutation_receipt(
        db,
        organization_id=organization.id,
        key=payload.idempotency_key,
        operation="membership.policy.write",
        fingerprint=fingerprint,
        response=response,
    )
    await db.flush()
    return response
