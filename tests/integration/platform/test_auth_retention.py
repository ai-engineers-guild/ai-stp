"""Auth-state garbage collection against a real database.

Sessions and device authorizations are global tables with no owner process
after their expiry; the daily sweep's GC is the only thing that removes them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_foundation.ids import new_id
from ai_stp_platform.auth_retention import (
    gc_expired_device_authorizations,
    gc_expired_sessions,
)
from ai_stp_platform.models import Account, AccountSession, DeviceAuthorization

pytestmark = pytest.mark.platform


@pytest.mark.asyncio
async def test_expired_sessions_are_swept_while_live_ones_stay(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    account_id = new_id("account")
    async with db_sessionmaker() as session, session.begin():
        session.add(Account(id=account_id))
        session.add_all(
            [
                AccountSession(
                    id="s" * 64,
                    account_id=account_id,
                    expires_at=now - timedelta(days=31),
                    kind="access",
                ),
                AccountSession(
                    id="t" * 64,
                    account_id=account_id,
                    expires_at=now - timedelta(days=2),
                    kind="access",
                ),
                AccountSession(
                    id="u" * 64,
                    account_id=account_id,
                    expires_at=now + timedelta(days=1),
                    kind="access",
                ),
            ]
        )

    async with db_sessionmaker() as session, session.begin():
        assert await gc_expired_sessions(session, now=now) == 1

    async with db_sessionmaker() as session:
        remaining = set(
            (await session.scalars(select(AccountSession.id).order_by(AccountSession.id))).all()
        )
    # Only the 31-day-dead row was removed: a session dead two days is still
    # inside the forensic window, and a live session is never touched.
    assert remaining == {"t" * 64, "u" * 64}


@pytest.mark.asyncio
async def test_expired_device_authorizations_are_swept(
    db_sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    now = datetime.now(UTC)
    async with db_sessionmaker() as session, session.begin():
        session.add_all(
            [
                DeviceAuthorization(
                    device_code="dead-" + "d" * 40,
                    user_code="AAAA-AAAA",
                    provider="github",
                    status="consumed",
                    expires_at=now - timedelta(days=31),
                ),
                DeviceAuthorization(
                    device_code="live-" + "e" * 40,
                    user_code="BBBB-BBBB",
                    provider="github",
                    status="pending",
                    expires_at=now + timedelta(minutes=10),
                ),
            ]
        )

    async with db_sessionmaker() as session, session.begin():
        assert await gc_expired_device_authorizations(session, now=now) == 1

    async with db_sessionmaker() as session:
        remaining = set(
            (
                await session.scalars(
                    select(DeviceAuthorization.device_code).order_by(
                        DeviceAuthorization.device_code
                    )
                )
            ).all()
        )
    assert remaining == {"live-" + "e" * 40}
