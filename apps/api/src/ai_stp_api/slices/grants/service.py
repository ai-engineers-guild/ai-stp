"""Grant invitation and access grant service (SPEC-026 / SPEC-002)."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_contracts.grants import (
    AccessGrantResponse,
    DirectGrantCreateRequest,
    GrantAcceptRequest,
    GrantInvitationCreateRequest,
    GrantInvitationResponse,
    GrantListResponse,
    GrantRevokeRequest,
    GrantRevokeResponse,
)
from ai_stp_foundation.ids import new_id, stable_id_pattern
from ai_stp_platform.grant_identity_models import (
    GrantRecipientReference,
    OAuthIdentityAlias,
)
from ai_stp_platform.models import (
    AccessGrant,
    Account,
    CatalogMetadata,
    GrantInvitation,
    OAuthIdentity,
)
from ai_stp_platform.queue.engine import enqueue
from ai_stp_platform.queue.states import JobType

# Module-level outbox for tokens that must reach the mail job without DB storage of raw token.
_PENDING_TOKENS: dict[str, str] = {}
_GITHUB_USERNAME = re.compile(r"^[a-z\d](?:[a-z\d]|-(?=[a-z\d])){0,38}$")
_ACCOUNT_ID = re.compile(stable_id_pattern("account"))


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ts(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def invitation_to_wire(row: GrantInvitation) -> GrantInvitationResponse:
    return GrantInvitationResponse(
        schema_version=1,
        invitation_id=row.id,
        object_kind=row.object_kind,  # type: ignore[arg-type]
        stable_id=row.stable_id,
        major=row.major,
        state=row.state,  # type: ignore[arg-type]
        expires_at=_ts(row.expires_at),
        created_at=_ts(row.created_at),
    )


def grant_to_wire(
    row: AccessGrant, reference: GrantRecipientReference | None = None
) -> AccessGrantResponse:
    return AccessGrantResponse(
        schema_version=1,
        grant_id=row.id,
        object_kind=row.object_kind,  # type: ignore[arg-type]
        stable_id=row.stable_id,
        major=row.major,
        grantee_account_id=row.grantee_account_id,
        owner_account_id=row.owner_account_id,
        state=row.state,  # type: ignore[arg-type]
        created_at=_ts(row.created_at),
        revoked_at=_ts(row.revoked_at) if row.revoked_at else None,
        recipient_kind=reference.identifier_kind if reference else None,  # type: ignore[arg-type]
        recipient=reference.identifier_value if reference else None,
    )


def normalize_github_username(value: str) -> str:
    """Return GitHub's canonical case-insensitive username form."""
    normalized = value.strip().lower().removeprefix("@")
    if _GITHUB_USERNAME.fullmatch(normalized) is None:
        raise ApiError(ErrorCategory.VALIDATION, "invalid GitHub username")
    return normalized


async def create_direct_grant(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    body: DirectGrantCreateRequest,
) -> AccessGrantResponse:
    """Create an active grant after resolving an explicit stable identity."""
    await _assert_owner(
        db, account_id=ctx.account_id, object_kind=body.object_kind, stable_id=body.stable_id
    )
    if body.recipient_kind == "github_username":
        recipient = normalize_github_username(body.recipient)
        grantee_account_id = await db.scalar(
            select(OAuthIdentity.account_id)
            .join(OAuthIdentityAlias, OAuthIdentityAlias.oauth_identity_id == OAuthIdentity.id)
            .where(
                OAuthIdentityAlias.provider == "github",
                OAuthIdentityAlias.normalized_value == recipient,
                OAuthIdentity.provider == "github",
                OAuthIdentity.state == "linked",
            )
        )
    else:
        recipient = body.recipient.strip()
        if _ACCOUNT_ID.fullmatch(recipient) is None:
            raise ApiError(ErrorCategory.VALIDATION, "invalid user ID")
        grantee_account_id = await db.scalar(select(Account.id).where(Account.id == recipient))
    if grantee_account_id is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "recipient not found")
    existing = await db.scalar(
        select(AccessGrant).where(
            AccessGrant.object_kind == body.object_kind,
            AccessGrant.stable_id == body.stable_id,
            AccessGrant.major == body.major,
            AccessGrant.grantee_account_id == grantee_account_id,
        )
    )
    if existing is not None:
        reference = await db.get(GrantRecipientReference, existing.id)
        return grant_to_wire(existing, reference)
    grant = AccessGrant(
        id=new_id("grant"),
        object_kind=body.object_kind,
        stable_id=body.stable_id,
        major=body.major,
        owner_account_id=ctx.account_id,
        grantee_account_id=grantee_account_id,
        state="active",
    )
    reference = GrantRecipientReference(
        grant_id=grant.id,
        identifier_kind=body.recipient_kind,
        identifier_value=recipient,
    )
    db.add(grant)
    await db.flush()
    db.add(reference)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="grant.created_direct",
        target_table="access_grant",
        target_id=grant.id,
        payload={"recipient_kind": body.recipient_kind},
    )
    await db.flush()
    return grant_to_wire(grant, reference)


async def _assert_owner(
    db: AsyncSession, *, account_id: str, object_kind: str, stable_id: str
) -> None:
    owned = await db.scalar(
        select(CatalogMetadata.id).where(
            CatalogMetadata.owner_account_id == account_id,
            CatalogMetadata.object_kind == object_kind,
            CatalogMetadata.stable_id == stable_id,
        )
    )
    if owned is None:
        # Ownership may also be future private draft; for MVP require catalog row.
        raise ApiError(ErrorCategory.PERMISSION, "not the owner of the object")


async def create_invitation(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    body: GrantInvitationCreateRequest,
) -> GrantInvitationResponse:
    await _assert_owner(
        db, account_id=ctx.account_id, object_kind=body.object_kind, stable_id=body.stable_id
    )
    existing = await db.scalar(
        select(GrantInvitation).where(
            GrantInvitation.owner_account_id == ctx.account_id,
            GrantInvitation.idempotency_key == body.idempotency_key,
        )
    )
    if existing is not None:
        return invitation_to_wire(existing)

    email = normalize_email(body.recipient_email)
    token = secrets.token_urlsafe(32)
    invitation = GrantInvitation(
        id=new_id("invite"),
        owner_account_id=ctx.account_id,
        object_kind=body.object_kind,
        stable_id=body.stable_id,
        major=body.major,
        recipient_email_normalized=email,
        token_hash=hash_token(token),
        state="pending",
        idempotency_key=body.idempotency_key,
        expires_at=datetime.now(UTC) + timedelta(seconds=body.ttl_seconds),
    )
    db.add(invitation)
    _PENDING_TOKENS[invitation.id] = token
    await enqueue(
        db,
        job_type=JobType.DELIVER_INVITATION,
        payload={
            "invitation_id": invitation.id,
            "to_email": email,
            "object_stable_id": body.stable_id,
            "major": body.major,
            # Token travels only in job payload until delivered; audit never gets it.
            "accept_token": token,
        },
        idempotency_key=f"deliver_invitation:{invitation.id}",
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="grant.invitation_created",
        target_table="grant_invitation",
        target_id=invitation.id,
        payload={"stable_id": body.stable_id, "major": body.major},
    )
    await db.flush()
    return invitation_to_wire(invitation)


async def list_grants(db: AsyncSession, *, ctx: AuthContext) -> GrantListResponse:
    invitations = list(
        (
            await db.execute(
                select(GrantInvitation).where(GrantInvitation.owner_account_id == ctx.account_id)
            )
        )
        .scalars()
        .all()
    )
    grants = list(
        (
            await db.execute(
                select(AccessGrant).where(
                    or_(
                        AccessGrant.owner_account_id == ctx.account_id,
                        AccessGrant.grantee_account_id == ctx.account_id,
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    reference_rows: list[GrantRecipientReference] = (
        list(
            (
                await db.execute(
                    select(GrantRecipientReference).where(
                        GrantRecipientReference.grant_id.in_([grant.id for grant in grants])
                    )
                )
            )
            .scalars()
            .all()
        )
        if grants
        else []
    )
    references: dict[str, GrantRecipientReference] = {row.grant_id: row for row in reference_rows}
    return GrantListResponse(
        schema_version=1,
        invitations=[invitation_to_wire(i) for i in invitations],
        grants=[grant_to_wire(g, references.get(g.id)) for g in grants],
    )


async def accept_invitation(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    invitation_id: str,
    body: GrantAcceptRequest,
) -> AccessGrantResponse:
    invitation = await db.get(GrantInvitation, invitation_id)
    if invitation is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "invitation not found")
    if invitation.state == "accepted" and invitation.accepted_grant_id:
        grant = await db.get(AccessGrant, invitation.accepted_grant_id)
        if grant is not None:
            return grant_to_wire(grant)
    if invitation.state != "pending":
        raise ApiError(ErrorCategory.CONFLICT, f"invitation is {invitation.state}")
    expires = (
        invitation.expires_at
        if invitation.expires_at.tzinfo
        else invitation.expires_at.replace(tzinfo=UTC)
    )
    if expires <= datetime.now(UTC):
        invitation.state = "expired"
        await db.flush()
        raise ApiError(ErrorCategory.VALIDATION, "invitation expired")
    if hash_token(body.token) != invitation.token_hash:
        raise ApiError(ErrorCategory.VALIDATION, "invitation token invalid")

    identities = list(
        (
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
    )
    emails = {normalize_email(i.email) for i in identities}
    if invitation.recipient_email_normalized not in emails:
        raise ApiError(ErrorCategory.VALIDATION, "verified email does not match invitation")

    existing_grant = await db.scalar(
        select(AccessGrant).where(
            AccessGrant.object_kind == invitation.object_kind,
            AccessGrant.stable_id == invitation.stable_id,
            AccessGrant.major == invitation.major,
            AccessGrant.grantee_account_id == ctx.account_id,
            AccessGrant.state == "active",
        )
    )
    if existing_grant is not None:
        invitation.state = "accepted"
        invitation.accepted_grant_id = existing_grant.id
        await db.flush()
        return grant_to_wire(existing_grant)

    grant = AccessGrant(
        id=new_id("grant"),
        object_kind=invitation.object_kind,
        stable_id=invitation.stable_id,
        major=invitation.major,
        owner_account_id=invitation.owner_account_id,
        grantee_account_id=ctx.account_id,
        state="active",
    )
    db.add(grant)
    invitation.state = "accepted"
    invitation.accepted_grant_id = grant.id
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="grant.accepted",
        target_table="access_grant",
        target_id=grant.id,
        payload={"invitation_id": invitation.id},
    )
    await db.flush()
    return grant_to_wire(grant)


async def revoke_invitation(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    invitation_id: str,
    body: GrantRevokeRequest,
) -> GrantRevokeResponse:
    invitation = await db.get(GrantInvitation, invitation_id)
    if invitation is None or invitation.owner_account_id != ctx.account_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "invitation not found")
    if invitation.state == "pending":
        invitation.state = "revoked"
        invitation.revoked_at = datetime.now(UTC)
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            action="grant.invitation_revoked",
            target_table="grant_invitation",
            target_id=invitation.id,
            reason=body.reason or None,
        )
        await db.flush()
    return GrantRevokeResponse(schema_version=1, revoked=True, local_bytes_retained=True)


async def revoke_grant(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    grant_id: str,
    body: GrantRevokeRequest,
) -> GrantRevokeResponse:
    grant = await db.get(AccessGrant, grant_id)
    if grant is None or grant.owner_account_id != ctx.account_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "grant not found")
    if grant.state == "active":
        grant.state = "revoked"
        grant.revoked_at = datetime.now(UTC)
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            action="grant.revoked",
            target_table="access_grant",
            target_id=grant.id,
            reason=body.reason or None,
            payload={"local_bytes_retained": True},
        )
        await db.flush()
    return GrantRevokeResponse(schema_version=1, revoked=True, local_bytes_retained=True)
