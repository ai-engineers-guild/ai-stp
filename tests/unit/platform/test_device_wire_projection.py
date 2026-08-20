"""Pure device wire projection invariants."""

from datetime import UTC, datetime, timedelta, timezone, tzinfo
from typing import Self

import pytest

from ai_stp_api.slices.devices import router
from ai_stp_platform.models import Device

pytestmark = pytest.mark.platform


def _device() -> Device:
    created = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    return Device(
        id="device_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        account_id="account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        public_key="fixture-public-key",
        device_type="cli",
        approximate_location=None,
        user_agent=None,
        state="active",
        last_seen_at=created,
        created_at=created,
        updated_at=created,
    )


def test_device_record_projects_display_summary_and_normalizes_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = _device()
    record = router._device_record(  # pyright: ignore[reportPrivateUsage]
        device, display_name="workstation"
    )

    assert record["summary"] == {
        "schema_version": 1,
        "display_name": "workstation",
        "operating_system": "linux",
        "architecture": "x86_64",
        "detected_harnesses": [],
        "toolchain_profile_version": "unknown",
        "summary_updated_at": "2026-08-10T12:00:00.000Z",
    }
    east = timezone(timedelta(hours=3))
    assert (
        router._wire_ts(  # pyright: ignore[reportPrivateUsage]
            datetime(2026, 8, 10, 15, 0, tzinfo=east)
        )
        == "2026-08-10T12:00:00.000Z"
    )

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls(2026, 8, 10, 12, 0, tzinfo=tz)

    monkeypatch.setattr(router, "datetime", FrozenDateTime)
    assert router._wire_ts(None) == "2026-08-10T12:00:00.000Z"  # pyright: ignore[reportPrivateUsage]


def test_device_etag_ignores_activity_but_changes_with_revocation() -> None:
    device = _device()
    original = router._device_etag(device)  # pyright: ignore[reportPrivateUsage]

    refreshed = datetime(2026, 8, 10, 13, 0, tzinfo=UTC)
    device.last_seen_at = refreshed
    device.updated_at = refreshed
    assert router._device_etag(device) == original  # pyright: ignore[reportPrivateUsage]

    device.state = "revoked"
    assert router._device_etag(device) != original  # pyright: ignore[reportPrivateUsage]
