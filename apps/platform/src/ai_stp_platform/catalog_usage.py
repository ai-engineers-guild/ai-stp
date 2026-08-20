"""Privacy-preserving public catalog usage counters (SPEC-051, ADR-0097).

Recording and projection are both off until the feature flag is enabled.
Dedup stores only a keyed digest and an expiry. Raw IP, user-agent, account
and device identity are never persisted. Download is not install success.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Final

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.catalog import (
    USAGE_METRICS_DEFAULT_RETENTION_SECONDS,
    USAGE_METRICS_DEFAULT_SECRET_ROTATION_SECONDS,
    USAGE_METRICS_DEFAULT_WINDOW_SECONDS,
    USAGE_METRICS_ENABLED_BY_DEFAULT,
    USAGE_METRICS_RETENTION_MAX_SECONDS,
    USAGE_METRICS_WINDOW_MAX_SECONDS,
    USAGE_METRICS_WINDOW_MIN_SECONDS,
    CatalogUsageMetrics,
)
from ai_stp_platform.models import CatalogUsageAggregate, CatalogUsageDedup

DETAIL_VIEW: Final = "detail_view"
ARTIFACT_DOWNLOAD: Final = "artifact_download"
USAGE_ACTIONS: Final[frozenset[str]] = frozenset({DETAIL_VIEW, ARTIFACT_DOWNLOAD})
_MATERIAL_PREFIX: Final = b"ai-stp:catalog-usage:v1"
_CLEANUP_BATCH: Final = 64


@dataclass(frozen=True)
class CatalogUsagePolicy:
    enabled: bool = USAGE_METRICS_ENABLED_BY_DEFAULT
    window_seconds: int = USAGE_METRICS_DEFAULT_WINDOW_SECONDS
    retention_seconds: int = USAGE_METRICS_DEFAULT_RETENTION_SECONDS
    secret_rotation_seconds: int = USAGE_METRICS_DEFAULT_SECRET_ROTATION_SECONDS
    secret: str = ""

    def validate(self) -> None:
        if self.window_seconds < USAGE_METRICS_WINDOW_MIN_SECONDS:
            raise ValueError("usage window is shorter than the documented minimum")
        if self.window_seconds > USAGE_METRICS_WINDOW_MAX_SECONDS:
            raise ValueError("usage window is longer than the documented maximum")
        if self.retention_seconds < self.window_seconds:
            raise ValueError("usage retention must cover at least one window")
        if self.retention_seconds > USAGE_METRICS_RETENTION_MAX_SECONDS:
            raise ValueError("usage retention exceeds the documented maximum")
        if self.secret_rotation_seconds < self.window_seconds:
            raise ValueError("usage secret rotation must overlap the current window")
        if self.secret_rotation_seconds > self.retention_seconds:
            raise ValueError("usage secret must rotate at least as often as retention")
        if self.enabled and len(self.secret) < 32:
            raise ValueError("enabled usage counters require a dedicated secret")


def window_id(now: datetime, *, window_seconds: int) -> int:
    return int(now.timestamp()) // window_seconds


def secret_epoch(now: datetime, *, rotation_seconds: int) -> int:
    return int(now.timestamp()) // rotation_seconds


def peer_network_signal(host: str | None) -> str:
    """In-memory minimum network signal. Empty when the peer is unknown."""
    return host or ""


def usage_dedup_digest(
    *,
    secret: str,
    epoch: int,
    action: str,
    stable_id: str,
    window: int,
    network_signal: str,
) -> str:
    """Keyed digest. Inputs are not recoverable from the stored hex."""
    if action not in USAGE_ACTIONS:
        raise ValueError("unknown usage action")
    epoch_key = hmac.new(secret.encode("utf-8"), f"epoch:{epoch}".encode(), sha256).digest()
    material = b"\0".join(
        (
            _MATERIAL_PREFIX,
            action.encode("ascii"),
            stable_id.encode("utf-8"),
            str(window).encode("ascii"),
            network_signal.encode("utf-8"),
        )
    )
    return hmac.new(epoch_key, material, sha256).hexdigest()


def usage_metrics_from_row(row: CatalogUsageAggregate | None) -> CatalogUsageMetrics:
    if row is None:
        return CatalogUsageMetrics(detail_views_count=0, artifact_downloads_count=0)
    return CatalogUsageMetrics(
        detail_views_count=row.detail_views_count,
        artifact_downloads_count=row.artifact_downloads_count,
    )


async def load_usage_metrics(
    session: AsyncSession,
    stable_ids: list[str],
    *,
    policy: CatalogUsagePolicy,
) -> dict[str, CatalogUsageMetrics]:
    if not policy.enabled or not stable_ids:
        return {}
    rows = (
        await session.execute(
            select(CatalogUsageAggregate).where(CatalogUsageAggregate.stable_id.in_(stable_ids))
        )
    ).scalars()
    found = {row.stable_id: usage_metrics_from_row(row) for row in rows}
    empty = usage_metrics_from_row(None)
    return {stable_id: found.get(stable_id, empty) for stable_id in stable_ids}


async def record_usage(
    session: AsyncSession,
    *,
    policy: CatalogUsagePolicy,
    action: str,
    stable_id: str,
    network_signal: str,
    now: datetime | None = None,
    method: str = "GET",
) -> bool:
    """Atomically increment once per keyed window. False when skipped."""
    if not policy.enabled or method != "GET" or action not in USAGE_ACTIONS:
        return False
    policy.validate()
    moment = now or datetime.now(UTC)
    window = window_id(moment, window_seconds=policy.window_seconds)
    epoch = secret_epoch(moment, rotation_seconds=policy.secret_rotation_seconds)
    current_key = usage_dedup_digest(
        secret=policy.secret,
        epoch=epoch,
        action=action,
        stable_id=stable_id,
        window=window,
        network_signal=network_signal,
    )
    previous_key = usage_dedup_digest(
        secret=policy.secret,
        epoch=epoch - 1,
        action=action,
        stable_id=stable_id,
        window=window,
        network_signal=network_signal,
    )
    if await session.get(CatalogUsageDedup, previous_key) is not None:
        await session.execute(
            insert(CatalogUsageDedup)
            .values(
                dedup_key=current_key,
                expires_at=moment + timedelta(seconds=policy.retention_seconds),
            )
            .on_conflict_do_nothing(index_elements=["dedup_key"])
        )
        return False
    inserted = await session.execute(
        insert(CatalogUsageDedup)
        .values(
            dedup_key=current_key,
            expires_at=moment + timedelta(seconds=policy.retention_seconds),
        )
        .on_conflict_do_nothing(index_elements=["dedup_key"])
        .returning(CatalogUsageDedup.dedup_key)
    )
    if inserted.scalar_one_or_none() is None:
        return False
    views = 1 if action == DETAIL_VIEW else 0
    downloads = 1 if action == ARTIFACT_DOWNLOAD else 0
    increment = insert(CatalogUsageAggregate).values(
        stable_id=stable_id,
        detail_views_count=views,
        artifact_downloads_count=downloads,
        updated_at=moment,
    )
    increment = increment.on_conflict_do_update(
        index_elements=["stable_id"],
        set_={
            "detail_views_count": CatalogUsageAggregate.detail_views_count
            + increment.excluded.detail_views_count,
            "artifact_downloads_count": CatalogUsageAggregate.artifact_downloads_count
            + increment.excluded.artifact_downloads_count,
            "updated_at": moment,
        },
    )
    await session.execute(increment)
    await purge_expired_usage_dedup(session, now=moment)
    return True


async def purge_expired_usage_dedup(
    session: AsyncSession, *, now: datetime, limit: int = _CLEANUP_BATCH
) -> int:
    keys = (
        select(CatalogUsageDedup.dedup_key).where(CatalogUsageDedup.expires_at < now).limit(limit)
    )
    result = await session.execute(
        delete(CatalogUsageDedup).where(CatalogUsageDedup.dedup_key.in_(keys))
    )
    rowcount = getattr(result, "rowcount", 0)
    return rowcount if isinstance(rowcount, int) else 0
