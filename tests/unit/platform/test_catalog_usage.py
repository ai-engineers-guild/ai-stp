"""Public usage counters stay private, gated, and independent of trust."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_stp_contracts.catalog import (
    USAGE_METRICS_DEFAULT_RETENTION_SECONDS,
    USAGE_METRICS_DEFAULT_WINDOW_SECONDS,
    USAGE_METRICS_ENABLED_BY_DEFAULT,
    USAGE_METRICS_WINDOW_MIN_SECONDS,
)
from ai_stp_platform.catalog_usage import (
    ARTIFACT_DOWNLOAD,
    DETAIL_VIEW,
    CatalogUsagePolicy,
    peer_network_signal,
    record_usage,
    secret_epoch,
    usage_dedup_digest,
    window_id,
)
from ai_stp_platform.models import CatalogUsageAggregate, CatalogUsageDedup

pytestmark = pytest.mark.platform

NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=UTC)
STABLE_ID = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
SECRET = "unit-catalog-usage-secret-32-bytes!"


def _enabled() -> CatalogUsagePolicy:
    return CatalogUsagePolicy(enabled=True, secret=SECRET)


def test_usage_metrics_are_disabled_by_default() -> None:
    assert USAGE_METRICS_ENABLED_BY_DEFAULT is False
    assert CatalogUsagePolicy().enabled is False


def test_usage_metrics_policy_requires_secret_and_documented_bounds() -> None:
    with pytest.raises(ValueError, match="dedicated secret"):
        CatalogUsagePolicy(enabled=True, secret="short").validate()
    with pytest.raises(ValueError, match="minimum"):
        CatalogUsagePolicy(
            window_seconds=USAGE_METRICS_WINDOW_MIN_SECONDS - 1, secret=SECRET
        ).validate()
    with pytest.raises(ValueError, match="at least one window"):
        CatalogUsagePolicy(
            window_seconds=USAGE_METRICS_DEFAULT_WINDOW_SECONDS,
            retention_seconds=USAGE_METRICS_DEFAULT_WINDOW_SECONDS - 1,
            secret=SECRET,
        ).validate()


def test_detail_view_dedup_digest_excludes_raw_identity_and_changes_across_windows() -> None:
    policy = _enabled()
    window = window_id(NOW, window_seconds=policy.window_seconds)
    epoch = secret_epoch(NOW, rotation_seconds=policy.secret_rotation_seconds)
    signal = peer_network_signal("203.0.113.9")
    digest = usage_dedup_digest(
        secret=policy.secret,
        epoch=epoch,
        action=DETAIL_VIEW,
        stable_id=STABLE_ID,
        window=window,
        network_signal=signal,
    )
    assert len(digest) == 64
    assert digest.isalnum()
    assert "203.0.113.9" not in digest
    assert STABLE_ID not in digest
    later = NOW + timedelta(seconds=policy.window_seconds)
    other_window = usage_dedup_digest(
        secret=policy.secret,
        epoch=secret_epoch(later, rotation_seconds=policy.secret_rotation_seconds),
        action=DETAIL_VIEW,
        stable_id=STABLE_ID,
        window=window_id(later, window_seconds=policy.window_seconds),
        network_signal=signal,
    )
    download = usage_dedup_digest(
        secret=policy.secret,
        epoch=epoch,
        action=ARTIFACT_DOWNLOAD,
        stable_id=STABLE_ID,
        window=window,
        network_signal=signal,
    )
    assert digest != other_window
    assert digest != download
    same = usage_dedup_digest(
        secret=policy.secret,
        epoch=epoch,
        action=DETAIL_VIEW,
        stable_id=STABLE_ID,
        window=window,
        network_signal=signal,
    )
    assert same == digest


def test_usage_metrics_tables_have_only_privacy_safe_columns() -> None:
    dedup_fields = set(CatalogUsageDedup.__table__.columns.keys())
    aggregate_fields = set(CatalogUsageAggregate.__table__.columns.keys())
    assert dedup_fields == {"dedup_key", "expires_at"}
    assert aggregate_fields == {
        "stable_id",
        "detail_views_count",
        "artifact_downloads_count",
        "updated_at",
    }
    forbidden = {
        "ip",
        "address",
        "user_agent",
        "account_id",
        "device_id",
        "visitor",
        "cookie",
        "consent",
    }
    stored = dedup_fields | aggregate_fields
    assert forbidden.isdisjoint(stored)


def test_artifact_download_is_not_install_success() -> None:
    policy = _enabled()
    assert policy.enabled is True
    assert DETAIL_VIEW != "install_success"
    assert ARTIFACT_DOWNLOAD != "install_success"
    assert USAGE_METRICS_DEFAULT_RETENTION_SECONDS >= USAGE_METRICS_DEFAULT_WINDOW_SECONDS


def test_usage_metrics_peer_signal_never_invents_an_identifier() -> None:
    assert peer_network_signal(None) == ""
    assert peer_network_signal("2001:db8::1") == "2001:db8::1"


@pytest.mark.asyncio
async def test_disabled_usage_metrics_and_head_never_touch_storage() -> None:
    class _Boom:
        async def get(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("disabled usage must not read storage")

        async def execute(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("disabled usage must not write storage")

    session = _Boom()
    assert (
        await record_usage(
            session,  # type: ignore[arg-type]
            policy=CatalogUsagePolicy(),
            action=DETAIL_VIEW,
            stable_id=STABLE_ID,
            network_signal="203.0.113.9",
        )
        is False
    )
    assert (
        await record_usage(
            session,  # type: ignore[arg-type]
            policy=_enabled(),
            action=ARTIFACT_DOWNLOAD,
            stable_id=STABLE_ID,
            network_signal="203.0.113.9",
            method="HEAD",
        )
        is False
    )
