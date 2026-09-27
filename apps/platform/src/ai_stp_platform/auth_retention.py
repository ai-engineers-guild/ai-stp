"""Auth-state garbage collection.

``account_session`` rows outlive their usefulness on every sign-in, refresh
rotation, and logout, and ``device_authorization`` rows outlive it on every
device-code grant — neither table had a reaper, so they grew forever. Both
sweeps are bounded per pass and keyed on ``expires_at``: a session row is dead
once expiry plus the forensic window has passed (a presented token whose row
is gone fails the same PK lookup a revoked row does), and a device grant is
dead once its expiry has passed regardless of status, since ``exchange``
refuses every status after expiry.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_platform.models import AccountSession, DeviceAuthorization
from ai_stp_platform.tenant_scope import set_tenant_scope

AUTH_RETENTION_DAYS = 30
AUTH_GC_BATCH_LIMIT = 5000


async def gc_expired_sessions(
    session: AsyncSession,
    *,
    retention_days: int = AUTH_RETENTION_DAYS,
    limit: int = AUTH_GC_BATCH_LIMIT,
    now: datetime | None = None,
) -> int:
    """Delete session rows dead past the retention window; bounded per pass."""
    await set_tenant_scope(session, "*")
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    ids = (
        await session.scalars(
            select(AccountSession.id)
            .where(AccountSession.expires_at < cutoff)
            .order_by(AccountSession.expires_at)
            .limit(limit)
        )
    ).all()
    if not ids:
        return 0
    result = cast(
        "CursorResult[Any]",
        await session.execute(sql_delete(AccountSession).where(AccountSession.id.in_(ids))),
    )
    return result.rowcount or 0


async def gc_expired_device_authorizations(
    session: AsyncSession,
    *,
    retention_days: int = AUTH_RETENTION_DAYS,
    limit: int = AUTH_GC_BATCH_LIMIT,
    now: datetime | None = None,
) -> int:
    """Delete device-grant rows dead past the retention window; bounded per pass."""
    await set_tenant_scope(session, "*")
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    ids = (
        await session.scalars(
            select(DeviceAuthorization.device_code)
            .where(DeviceAuthorization.expires_at < cutoff)
            .order_by(DeviceAuthorization.expires_at)
            .limit(limit)
        )
    ).all()
    if not ids:
        return 0
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            sql_delete(DeviceAuthorization).where(DeviceAuthorization.device_code.in_(ids))
        ),
    )
    return result.rowcount or 0


__all__ = [
    "AUTH_GC_BATCH_LIMIT",
    "AUTH_RETENTION_DAYS",
    "gc_expired_device_authorizations",
    "gc_expired_sessions",
]
