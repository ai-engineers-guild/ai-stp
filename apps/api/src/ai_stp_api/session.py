"""Opaque server session issue and verify (ADR-0041, SPEC-002 REQ-207).

Token scheme: issue ``secrets.token_urlsafe(32)``, store only
``sha256_hex(token)`` as ``account_session.id``. The raw token is never
persisted. Verify hashes the presented credential and does one PK lookup.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_platform.models import AccountSession, Device


def hash_session_token(raw_token: str) -> str:
    """Return the durable primary-key form of a raw session token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def mint_session_token() -> str:
    """Create a high-entropy opaque session token for the client."""
    return secrets.token_urlsafe(32)


@dataclass(frozen=True)
class AuthContext:
    """Resolved authentication context for one request."""

    account_id: str
    session_id: str
    device_id: str | None
    is_admin: bool
    via_cookie: bool


@dataclass(frozen=True)
class IssuedSession:
    """Raw token plus the durable row that stores only its hash."""

    raw_token: str
    session: AccountSession


async def issue_session(
    db: AsyncSession,
    *,
    account_id: str,
    device_id: str | None,
    ttl_seconds: int,
) -> IssuedSession:
    """Persist a new session row keyed by the hash of a fresh raw token."""
    raw = mint_session_token()
    session_id = hash_session_token(raw)
    now = datetime.now(UTC)
    row = AccountSession(
        id=session_id,
        account_id=account_id,
        device_id=device_id,
        expires_at=now + timedelta(seconds=ttl_seconds),
        revoked_at=None,
    )
    db.add(row)
    await db.flush()
    return IssuedSession(raw_token=raw, session=row)


async def revoke_session(db: AsyncSession, session_id: str) -> bool:
    """Mark a session revoked. Returns True if a live session was revoked."""
    row = await db.get(AccountSession, session_id)
    if row is None:
        return False
    if row.revoked_at is not None:
        return False
    row.revoked_at = datetime.now(UTC)
    await db.flush()
    return True


async def revoke_sessions_for_device(db: AsyncSession, device_id: str) -> int:
    """Revoke every non-revoked session bound to a device. Returns count."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(AccountSession).where(
            AccountSession.device_id == device_id,
            AccountSession.revoked_at.is_(None),
        )
    )
    rows = list(result.scalars().all())
    for row in rows:
        row.revoked_at = now
    if rows:
        await db.flush()
    return len(rows)


async def load_session_row(db: AsyncSession, session_id: str) -> AccountSession | None:
    """Load a session with its optional device for active-state checks."""
    result = await db.execute(
        select(AccountSession)
        .where(AccountSession.id == session_id)
        .options(selectinload(AccountSession.device))
    )
    return result.scalar_one_or_none()


def session_is_active(row: AccountSession, *, now: datetime | None = None) -> bool:
    """Report whether a loaded session row may authorize a request."""
    clock = now or datetime.now(UTC)
    if row.revoked_at is not None:
        return False
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires <= clock:
        return False
    return device_active_or_none(row.device)


def session_device_revoked(row: AccountSession) -> bool:
    """True when the session is bound to a non-active device."""
    device = row.device
    return device is not None and device.state != "active"


async def verify_raw_token(
    db: AsyncSession,
    raw_token: str,
    *,
    admin_account_ids: frozenset[str],
    via_cookie: bool,
) -> AuthContext:
    """Hash ``raw_token``, look up the session and return an AuthContext.

    Raises ``ApiError`` with ``AUTH_REQUIRED`` when the credential is missing,
    unknown, expired or session-revoked. Raises ``DEVICE_REVOKED`` when the
    bound device is revoked (SPEC-025 REQ-2508). Does not log the token value.
    """
    if not raw_token:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication required")
    session_id = hash_session_token(raw_token)
    row = await load_session_row(db, session_id)
    if row is None:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication required")
    if session_device_revoked(row):
        raise ApiError(ErrorCategory.DEVICE_REVOKED, "device is revoked")
    if not session_is_active(row):
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication required")
    if row.device is not None:
        row.device.last_seen_at = datetime.now(UTC)
        await db.flush()
    return AuthContext(
        account_id=row.account_id,
        session_id=row.id,
        device_id=row.device_id,
        is_admin=row.account_id in admin_account_ids,
        via_cookie=via_cookie,
    )


def device_active_or_none(device: Device | None) -> bool:
    """Helper used by callers that already hold a device row."""
    return device is None or device.state == "active"
