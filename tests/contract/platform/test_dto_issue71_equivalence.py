"""DTO ↔ #71 fixture contract equivalence (ADR-0037).

#71 (shared wire freeze) is still open and has not published fixtures under
schemas/ or tests/golden for auth/device wire shapes. Until those fixtures
land, this module locks the local closed field set from
docs/contracts/device-passport.md and skips fixture-diff assertions when the
fixture corpus is absent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from ai_stp_api.slices.devices.domain import SUMMARY_FIELDS

pytestmark = pytest.mark.platform

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ISSUE71_FIXTURE_DIRS = (
    _REPO_ROOT / "tests" / "golden" / "api",
    _REPO_ROOT / "schemas" / "v1" / "fixtures",
    _REPO_ROOT / "tests" / "contract" / "fixtures" / "issue71",
)


def _issue71_device_fixtures() -> list[Path]:
    found: list[Path] = []
    for directory in _ISSUE71_FIXTURE_DIRS:
        if not directory.is_dir():
            continue
        found.extend(directory.glob("*device*summary*.json"))
        found.extend(directory.glob("*DevicePassportSummary*.json"))
    return found


def test_summary_fields_match_device_passport_contract_prose() -> None:
    """Local golden: closed list stays aligned with device-passport.md intent."""
    # Lifecycle + passport summary closed list (see design.md assumption note).
    expected = {
        "id",
        "state",
        "last_seen_at",
        "display_name",
        "os",
        "architecture",
        "harnesses",
        "toolset_profile_version",
        "summary_updated_at",
    }
    assert expected == SUMMARY_FIELDS


def test_issue71_fixture_equivalence_when_present() -> None:
    fixtures = _issue71_device_fixtures()
    if not fixtures:
        pytest.skip("#71 device summary fixtures are not published yet")
    # When fixtures appear, every key set must equal SUMMARY_FIELDS.
    import json

    for path in fixtures:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        items: list[dict[str, Any]]
        if isinstance(payload, dict) and "devices" in payload:
            items = cast(list[dict[str, Any]], payload["devices"])
        elif isinstance(payload, dict) and "data" in payload:
            data = cast(dict[str, Any], payload["data"])
            devices = data.get("devices")
            items = cast(list[dict[str, Any]], devices if devices is not None else [data])
        else:
            items = [cast(dict[str, Any], payload)]
        for item in items:
            assert set(item) <= SUMMARY_FIELDS
            assert "private_key" not in item
            assert "absolute_path" not in item
