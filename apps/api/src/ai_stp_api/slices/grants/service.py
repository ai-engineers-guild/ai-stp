"""Grant invitation and access grant service (SPEC-026 / SPEC-002)."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    CatalogIdentity,
    CatalogMetadata,
    GrantInvitation,
    OAuthIdentity,
)
from ai_stp_platform.organization_models import Organization, OrganizationMembership
from ai_stp_platform.queue.engine import enqueue
from ai_stp_platform.queue.states import JobType

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


async def _owner_scope_id(db: AsyncSession, *, owner_account_id: str) -> str:
    """Resolve the owner's personal organization id, creating it when absent.

    Bulk `pg_insert` writes bypass the `before_flush` hook that fills
    `organization_id` on ORM writes, so conflict-safe inserts must carry the
    scope explicitly. Org creation races on the partial unique index are
    arbitrated by `ON CONFLICT` the same way.
    """
    organization_id = await db.scalar(
        select(Organization.id).where(
            Organization.owner_account_id == owner_account_id,
            Organization.kind == "personal",
        )
    )
    if organization_id is not None:
        return organization_id
    candidate = new_id("organization")
    created = cast(
        CursorResult[Any],
        await db.execute(
            pg_insert(Organization)
            .values(
                id=candidate,
                kind="personal",
                owner_account_id=owner_account_id,
                display_name="Personal workspace",
                revision=1,
            )
            .on_conflict_do_nothing(
                index_elements=[Organization.owner_account_id],
                index_where=Organization.kind == "personal",
            )
        ),
    )
    if created.rowcount == 1:
        db.add(
            OrganizationMembership(
                organization_id=candidate,
                account_id=owner_account_id,
                role="owner",
                state="active",
                revision=1,
            )
        )
        await db.flush()
        return candidate
    organization_id = await db.scalar(
        select(Organization.id).where(
            Organization.owner_account_id == owner_account_id,
            Organization.kind == "personal",
        )
    )
    assert organization_id is not None
    return organization_id


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
    issuer_scope = await _issuer_scope(
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
        if existing.state == "revoked":
            existing.state = "active"
            existing.revoked_at = None
            await emit_audit(
                db,
                actor_account_id=ctx.account_id,
                action="grant.reactivated",
                target_table="access_grant",
                target_id=existing.id,
                payload={"recipient_kind": body.recipient_kind},
            )
            await db.flush()
        reference = await db.get(GrantRecipientReference, existing.id)
        return grant_to_wire(existing, reference)
    grant_id = new_id("grant")
    # `ON CONFLICT DO NOTHING` never raises on the race: a concurrent create
    # for the same target and grantee commits first, this insert skips, and
    # the re-select returns the committed winner. (A failed flush inside
    # `begin_nested` marks the whole session rollback-required in SQLAlchemy,
    # so the savepoint-replay idiom cannot survive here.)
    inserted = cast(
        CursorResult[Any],
        await db.execute(
            pg_insert(AccessGrant)
            .values(
                id=grant_id,
                organization_id=issuer_scope,
                object_kind=body.object_kind,
                stable_id=body.stable_id,
                major=body.major,
                owner_account_id=ctx.account_id,
                grantee_account_id=grantee_account_id,
                state="active",
            )
            .on_conflict_do_nothing(
                index_elements=[
                    AccessGrant.object_kind,
                    AccessGrant.stable_id,
                    AccessGrant.major,
                    AccessGrant.grantee_account_id,
                ]
            )
        ),
    )
    grant = (
        await db.execute(
            select(AccessGrant).where(
                AccessGrant.object_kind == body.object_kind,
                AccessGrant.stable_id == body.stable_id,
                AccessGrant.major == body.major,
                AccessGrant.grantee_account_id == grantee_account_id,
            )
        )
    ).scalar_one()
    if inserted.rowcount != 1:
        winner_reference = await db.get(GrantRecipientReference, grant.id)
        return grant_to_wire(grant, winner_reference)
    reference = GrantRecipientReference(
        grant_id=grant.id,
        identifier_kind=body.recipient_kind,
        identifier_value=recipient,
    )
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


async def _object_organization_id(
    db: AsyncSession, *, object_kind: str, stable_id: str
) -> str | None:
    """The object's owning organization, from identity or metadata."""
    organization_id = await db.scalar(
        select(CatalogIdentity.organization_id).where(CatalogIdentity.stable_id == stable_id)
    )
    if organization_id is not None:
        return organization_id
    return await db.scalar(
        select(CatalogMetadata.organization_id)
        .where(
            CatalogMetadata.object_kind == object_kind,
            CatalogMetadata.stable_id == stable_id,
            CatalogMetadata.organization_id.is_not(None),
        )
        .limit(1)
    )


async def _corporate_owner_scope(
    db: AsyncSession, *, account_id: str, object_kind: str, stable_id: str
) -> str | None:
    """The object's corporate organization when the caller is its current
    resolved operational owner; `None` otherwise. Bare corporate membership
    never qualifies (ADR-0221)."""
    from ai_stp_api.slices.corporate.subject_access import resolves_catalog_ownership

    organization_id = await _object_organization_id(
        db, object_kind=object_kind, stable_id=stable_id
    )
    if organization_id is None:
        return None
    organization = await db.get(Organization, organization_id)
    if organization is None or organization.kind != "corporate":
        return None
    if not await resolves_catalog_ownership(
        db,
        organization_id=organization_id,
        object_kind=object_kind,
        stable_id=stable_id,
        account_id=account_id,
    ):
        return None
    return organization_id


async def _is_personal_owner(
    db: AsyncSession, *, account_id: str, object_kind: str, stable_id: str
) -> bool:
    return (
        await db.scalar(
            select(CatalogMetadata.id).where(
                CatalogMetadata.owner_account_id == account_id,
                CatalogMetadata.object_kind == object_kind,
                CatalogMetadata.stable_id == stable_id,
            )
        )
    ) is not None


async def _issuer_scope(
    db: AsyncSession, *, account_id: str, object_kind: str, stable_id: str
) -> str:
    """The organization scope an issuance runs under: the author's personal
    workspace for personal objects, or the object's corporate organization
    when the caller is its current resolved owner."""
    if await _is_personal_owner(
        db, account_id=account_id, object_kind=object_kind, stable_id=stable_id
    ):
        return await _owner_scope_id(db, owner_account_id=account_id)
    corporate_scope = await _corporate_owner_scope(
        db, account_id=account_id, object_kind=object_kind, stable_id=stable_id
    )
    if corporate_scope is not None:
        return corporate_scope
    # Ownership may also be future private draft; for MVP require catalog row.
    raise ApiError(ErrorCategory.PERMISSION, "not the owner of the object")


async def create_invitation(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    body: GrantInvitationCreateRequest,
) -> GrantInvitationResponse:
    issuer_scope = await _issuer_scope(
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
        organization_id=issuer_scope,
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
    # FOR UPDATE: two accepts of the same invitation must serialize — the loser
    # re-reads `accepted` and replays the winner's grant instead of racing the
    # access_grant unique key into a 500.
    invitation = await db.get(GrantInvitation, invitation_id, with_for_update=True)
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

    # `ON CONFLICT DO NOTHING` keeps the transaction alive through the race:
    # a concurrent accept of a *different* invitation for the same target and
    # grantee commits first, this insert skips, and the unique winner is the
    # grant this acceptance binds to. (A failed flush inside `begin_nested`
    # marks the whole session rollback-required in SQLAlchemy.)
    inserted = cast(
        CursorResult[Any],
        await db.execute(
            pg_insert(AccessGrant)
            .values(
                id=new_id("grant"),
                organization_id=invitation.organization_id
                or await _owner_scope_id(db, owner_account_id=invitation.owner_account_id),
                object_kind=invitation.object_kind,
                stable_id=invitation.stable_id,
                major=invitation.major,
                owner_account_id=invitation.owner_account_id,
                grantee_account_id=ctx.account_id,
                state="active",
            )
            .on_conflict_do_nothing(
                index_elements=[
                    AccessGrant.object_kind,
                    AccessGrant.stable_id,
                    AccessGrant.major,
                    AccessGrant.grantee_account_id,
                ]
            )
        ),
    )
    grant = (
        await db.execute(
            select(AccessGrant).where(
                AccessGrant.object_kind == invitation.object_kind,
                AccessGrant.stable_id == invitation.stable_id,
                AccessGrant.major == invitation.major,
                AccessGrant.grantee_account_id == ctx.account_id,
            )
        )
    ).scalar_one()
    invitation.state = "accepted"
    invitation.accepted_grant_id = grant.id
    if inserted.rowcount != 1:
        await db.flush()
        return grant_to_wire(grant)
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


async def _may_withdraw(
    db: AsyncSession,
    *,
    account_id: str,
    issuer_account_id: str,
    object_kind: str,
    stable_id: str,
) -> bool:
    """The issuer or the object's current resolved corporate owner may
    withdraw — the same authority context issuance was checked against."""
    if issuer_account_id == account_id:
        return True
    return (
        await _corporate_owner_scope(
            db, account_id=account_id, object_kind=object_kind, stable_id=stable_id
        )
        is not None
    )


async def revoke_invitation(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    invitation_id: str,
    body: GrantRevokeRequest,
) -> GrantRevokeResponse:
    invitation = await db.get(GrantInvitation, invitation_id)
    if invitation is None or not await _may_withdraw(
        db,
        account_id=ctx.account_id,
        issuer_account_id=invitation.owner_account_id,
        object_kind=invitation.object_kind,
        stable_id=invitation.stable_id,
    ):
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
    if grant is None or not await _may_withdraw(
        db,
        account_id=ctx.account_id,
        issuer_account_id=grant.owner_account_id,
        object_kind=grant.object_kind,
        stable_id=grant.stable_id,
    ):
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
