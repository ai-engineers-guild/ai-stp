"""Account and OAuth identity linking (SPEC-002 REQ-201/202/203)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.slices.auth.domain import (
    LinkDecision,
    LinkState,
    ProviderProfile,
    normalize_email,
    normalize_subject,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.grant_identity_models import OAuthIdentityAlias
from ai_stp_platform.identity import allocate_account_identity
from ai_stp_platform.models import Account, Device, OAuthIdentity


async def _identity_by_provider_subject(
    db: AsyncSession,
    provider: str,
    subject: str,
) -> OAuthIdentity | None:
    result = await db.execute(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == provider,
            OAuthIdentity.provider_subject == subject,
        )
    )
    return result.scalar_one_or_none()


async def _accounts_for_verified_email(db: AsyncSession, email: str) -> list[str]:
    result = await db.execute(
        select(OAuthIdentity.account_id)
        .where(
            OAuthIdentity.email == email,
            OAuthIdentity.email_verified.is_(True),
            OAuthIdentity.state == LinkState.LINKED.value,
        )
        .distinct()
    )
    return list(result.scalars().all())


async def is_account_populated(db: AsyncSession, account_id: str) -> bool:
    """An account is populated if it has linked identities, devices or catalog.

    Two populated accounts must never be silently merged (REQ-202).
    """
    identity_count = await db.scalar(
        select(func.count())
        .select_from(OAuthIdentity)
        .where(
            OAuthIdentity.account_id == account_id,
            OAuthIdentity.state == LinkState.LINKED.value,
        )
    )
    if identity_count and identity_count > 0:
        # A single linked identity still counts as populated once the account
        # also owns devices; pure first-login accounts are handled by callers
        # before a second identity is attached. Device ownership is the hard
        # signal of local data; catalog ownership is out of this slice's write
        # path but still checked for conservatism.
        device_count = await db.scalar(
            select(func.count()).select_from(Device).where(Device.account_id == account_id)
        )
        if device_count and device_count > 0:
            return True
        return identity_count > 1
    device_count = await db.scalar(
        select(func.count()).select_from(Device).where(Device.account_id == account_id)
    )
    return bool(device_count and device_count > 0)


async def _create_account(db: AsyncSession) -> Account:
    account = Account(
        id=new_id("account"),
        status="onboarding_pending",
        show_profile_publicly=False,
        allow_publisher_listing=False,
    )
    db.add(account)
    await db.flush()
    await allocate_account_identity(db, account)
    return account


def _apply_profile_fields(identity: OAuthIdentity, profile: ProviderProfile) -> None:
    """Refresh stored presentation fields from the latest provider claims."""
    identity.email = profile.email
    identity.email_verified = profile.email_verified
    if profile.avatar_url is not None:
        identity.avatar_url = profile.avatar_url
    if profile.display_name is not None:
        identity.display_name = profile.display_name


async def _apply_identity_alias(
    db: AsyncSession, identity: OAuthIdentity, profile: ProviderProfile
) -> None:
    if profile.provider != "github" or profile.username is None:
        return
    normalized = profile.username.strip().lower()
    alias = await db.scalar(
        select(OAuthIdentityAlias).where(OAuthIdentityAlias.oauth_identity_id == identity.id)
    )
    if alias is None:
        db.add(
            OAuthIdentityAlias(
                oauth_identity_id=identity.id,
                provider="github",
                normalized_value=normalized,
            )
        )
    else:
        alias.normalized_value = normalized


async def _attach_identity(
    db: AsyncSession,
    *,
    account_id: str,
    profile: ProviderProfile,
    state: LinkState = LinkState.LINKED,
) -> OAuthIdentity:
    identity = OAuthIdentity(
        account_id=account_id,
        provider=profile.provider,
        provider_subject=profile.subject,
        email=profile.email,
        email_verified=profile.email_verified,
        avatar_url=profile.avatar_url,
        display_name=profile.display_name,
        state=state.value,
    )
    db.add(identity)
    await db.flush()
    await _apply_identity_alias(db, identity, profile)
    await db.flush()
    return identity


async def resolve_login_identity(
    db: AsyncSession,
    profile: ProviderProfile,
) -> LinkDecision:
    """Resolve Account for a provider login (create / same-email link / conflict).

    Uniform client-facing errors are raised for unauthenticated probes so that
    enumeration of emails is not facilitated by distinct codes (REQ-209 pattern).
    """
    if not profile.email_verified:
        # Same generic auth failure as other login problems (no email leak).
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication failed")

    subject = normalize_subject(profile.subject)
    email = normalize_email(profile.email)
    normalized = ProviderProfile(
        provider=profile.provider,
        subject=subject,
        email=email,
        email_verified=True,
        avatar_url=profile.avatar_url,
        display_name=profile.display_name,
        username=profile.username,
    )

    existing = await _identity_by_provider_subject(db, normalized.provider, subject)
    if existing is not None:
        if existing.state == LinkState.CONFLICT.value:
            raise ApiError(ErrorCategory.CONFLICT, "identity link conflict")
        if existing.state == LinkState.REVOKED.value:
            # Re-link after explicit unlink (same subject keeps the row).
            existing.state = LinkState.LINKED.value
            _apply_profile_fields(existing, normalized)
            await _apply_identity_alias(db, existing, normalized)
            await db.flush()
            await emit_audit(
                db,
                actor_account_id=existing.account_id,
                action="auth.identity_relinked",
                target_table="oauth_identity",
                target_id=str(existing.id),
                payload={"provider": normalized.provider},
            )
            return LinkDecision(
                account_id=existing.account_id,
                identity_id=existing.id,
                created_account=False,
                linked_identity=True,
                state=LinkState.LINKED,
            )
        # linked or pending → same account; refresh avatar/display claims.
        _apply_profile_fields(existing, normalized)
        await _apply_identity_alias(db, existing, normalized)
        await db.flush()
        return LinkDecision(
            account_id=existing.account_id,
            identity_id=existing.id,
            created_account=False,
            linked_identity=False,
            state=LinkState(existing.state),
        )

    email_accounts = await _accounts_for_verified_email(db, email)
    if not email_accounts:
        account = await _create_account(db)
        identity = await _attach_identity(db, account_id=account.id, profile=normalized)
        await emit_audit(
            db,
            actor_account_id=account.id,
            action="auth.account_created",
            target_table="account",
            target_id=account.id,
            payload={"provider": normalized.provider},
        )
        await emit_audit(
            db,
            actor_account_id=account.id,
            action="auth.identity_linked",
            target_table="oauth_identity",
            target_id=str(identity.id),
            payload={"provider": normalized.provider},
        )
        return LinkDecision(
            account_id=account.id,
            identity_id=identity.id,
            created_account=True,
            linked_identity=True,
            state=LinkState.LINKED,
        )

    if len(email_accounts) > 1:
        # Ambiguous same-email ownership across accounts → typed conflict.
        raise ApiError(ErrorCategory.CONFLICT, "identity link conflict")

    target_account_id = email_accounts[0]
    # Same confirmed email → link (REQ-202). No second account is created, so
    # silent merge of two populated accounts cannot occur on this path.
    identity = await _attach_identity(db, account_id=target_account_id, profile=normalized)
    await emit_audit(
        db,
        actor_account_id=target_account_id,
        action="auth.identity_linked",
        target_table="oauth_identity",
        target_id=str(identity.id),
        payload={"provider": normalized.provider, "via": "same_email"},
    )
    return LinkDecision(
        account_id=target_account_id,
        identity_id=identity.id,
        created_account=False,
        linked_identity=True,
        state=LinkState.LINKED,
    )


async def resolve_step_up_link(
    db: AsyncSession,
    *,
    session_account_id: str,
    profile: ProviderProfile,
) -> LinkDecision:
    """Link a second identity from an authenticated session (REQ-203).

    Different-email identities are allowed only on this path. An identity that
    already belongs to another account yields a typed conflict and never moves.
    """
    if not profile.email_verified:
        raise ApiError(ErrorCategory.VALIDATION, "email not verified by provider")

    subject = normalize_subject(profile.subject)
    email = normalize_email(profile.email)
    normalized = ProviderProfile(
        provider=profile.provider,
        subject=subject,
        email=email,
        email_verified=True,
        avatar_url=profile.avatar_url,
        display_name=profile.display_name,
        username=profile.username,
    )

    existing = await _identity_by_provider_subject(db, normalized.provider, subject)
    if existing is not None:
        if existing.account_id == session_account_id:
            was_revoked = existing.state == LinkState.REVOKED.value
            if was_revoked:
                existing.state = LinkState.LINKED.value
            _apply_profile_fields(existing, normalized)
            await _apply_identity_alias(db, existing, normalized)
            await db.flush()
            return LinkDecision(
                account_id=session_account_id,
                identity_id=existing.id,
                created_account=False,
                linked_identity=was_revoked,
                state=LinkState(existing.state),
            )
        # Identity already bound to another account → never silent-merge.
        other_populated = await is_account_populated(db, existing.account_id)
        self_populated = await is_account_populated(db, session_account_id)
        if other_populated or self_populated or existing.account_id != session_account_id:
            existing.state = LinkState.CONFLICT.value
            await db.flush()
            await emit_audit(
                db,
                actor_account_id=session_account_id,
                action="auth.identity_conflict",
                target_table="oauth_identity",
                target_id=str(existing.id),
                payload={"provider": normalized.provider},
            )
            raise ApiError(ErrorCategory.CONFLICT, "identity link conflict")

    identity = await _attach_identity(db, account_id=session_account_id, profile=normalized)
    await emit_audit(
        db,
        actor_account_id=session_account_id,
        action="auth.identity_linked",
        target_table="oauth_identity",
        target_id=str(identity.id),
        payload={"provider": normalized.provider, "via": "step_up"},
    )
    return LinkDecision(
        account_id=session_account_id,
        identity_id=identity.id,
        created_account=False,
        linked_identity=True,
        state=LinkState.LINKED,
    )


async def count_linked_identities(db: AsyncSession, account_id: str) -> int:
    """Return the number of active (linked/pending) identities for an account."""
    count = await db.scalar(
        select(func.count())
        .select_from(OAuthIdentity)
        .where(
            OAuthIdentity.account_id == account_id,
            OAuthIdentity.state.in_((LinkState.LINKED.value, LinkState.PENDING.value)),
        )
    )
    return int(count or 0)


async def unlink_identity(
    db: AsyncSession,
    *,
    account_id: str,
    provider: str,
) -> None:
    """Revoke one linked identity. The last active identity cannot be removed.

    Revocation keeps the row so a later sign-in with the same provider subject
    can re-link without colliding on the unique (provider, subject) key.
    """
    name = provider.strip().lower()
    result = await db.execute(
        select(OAuthIdentity).where(
            OAuthIdentity.account_id == account_id,
            OAuthIdentity.provider == name,
            OAuthIdentity.state.in_((LinkState.LINKED.value, LinkState.PENDING.value)),
        )
    )
    identity = result.scalar_one_or_none()
    if identity is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "identity not linked")

    active = await count_linked_identities(db, account_id)
    if active <= 1:
        raise ApiError(
            ErrorCategory.VALIDATION,
            "cannot unlink the last identity",
        )

    identity.state = LinkState.REVOKED.value
    await db.flush()
    await emit_audit(
        db,
        actor_account_id=account_id,
        action="auth.identity_unlinked",
        target_table="oauth_identity",
        target_id=str(identity.id),
        payload={"provider": name},
    )
