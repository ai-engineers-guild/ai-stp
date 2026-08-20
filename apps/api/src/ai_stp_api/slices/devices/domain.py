"""Device domain rules and summary field contract (SPEC-002 REQ-204/214)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

# Closed summary field list from docs/contracts/device-passport.md plus the
# lifecycle fields required by GET /v1/devices (id, state, last activity).
# Assumption (flagged): wire names below are the Sprint-1 English identifiers
# for the Russian contract prose until #71 freezes the shared schema.
SUMMARY_FIELDS: frozenset[str] = frozenset(
    {
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
)

# Fields that must never appear on device list/register request or response.
FORBIDDEN_SUMMARY_FIELDS: frozenset[str] = frozenset(
    {
        "private_key",
        "public_key",
        "absolute_path",
        "absolute_paths",
        "home_dir",
        "local_path",
        "env",
        "environment",
        "env_values",
        "secrets",
        "token",
        "session",
        "nonce",
        "full_passport",
        "passport",
        "paths",
    }
)


class DeviceState(StrEnum):
    """Device lifecycle states from SPEC-002."""

    ACTIVE = "active"
    REVOKED = "revoked"


@dataclass(frozen=True)
class DeviceSummary:
    """Server-visible device summary (closed field set)."""

    id: str
    state: str
    last_seen_at: datetime | None
    display_name: str | None = None
    os: str | None = None
    architecture: str | None = None
    harnesses: tuple[dict[str, str], ...] = ()
    toolset_profile_version: str | None = None
    summary_updated_at: datetime | None = None

    def as_dict(self) -> dict[str, object]:
        """Serialize to the closed summary field set only."""
        data: dict[str, object] = {
            "id": self.id,
            "state": self.state,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "display_name": self.display_name,
            "os": self.os,
            "architecture": self.architecture,
            "harnesses": list(self.harnesses),
            "toolset_profile_version": self.toolset_profile_version,
            "summary_updated_at": (
                self.summary_updated_at.isoformat() if self.summary_updated_at else None
            ),
        }
        assert_summary_keys(data)
        reject_forbidden_fields(data)
        return data


def reject_forbidden_fields(payload: dict[str, object]) -> None:
    """Raise ValueError if payload contains full-passport / private fields."""
    bad = sorted(set(payload) & FORBIDDEN_SUMMARY_FIELDS)
    if bad:
        msg = f"forbidden device fields: {', '.join(bad)}"
        raise ValueError(msg)


def assert_summary_keys(data: dict[str, object]) -> None:
    """Ensure a summary dict uses only the closed field list."""
    extra = sorted(set(data) - SUMMARY_FIELDS)
    if extra:
        msg = f"summary contains non-contract fields: {', '.join(extra)}"
        raise ValueError(msg)
