"""OSV offline database freshness probes for doctor and optional readiness."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

# Default: treat DB as stale after 36 hours without a successful refresh stamp.
DEFAULT_MAX_AGE_HOURS = 36.0
_STAMP_NAMES = (".ai_stp_osv_refreshed_at", "STATUS.txt")
# Files that do not count as vulnerability data (image placeholders).
_IGNORE_NAMES = frozenset({"README", "README.md", ".gitkeep", ".keep"})


def osv_offline_dir() -> Path | None:
    """Resolve configured offline dir path (may not exist yet)."""
    raw = os.environ.get("AI_STP_OSV_OFFLINE_DIR", "").strip()
    if not raw:
        default = Path("/var/lib/ai_stp/osv")
        return default if default.exists() else None
    return Path(raw)


def max_age_hours() -> float:
    raw = os.environ.get("AI_STP_OSV_MAX_AGE_HOURS", "").strip()
    if not raw:
        return DEFAULT_MAX_AGE_HOURS
    try:
        return max(1.0, float(raw))
    except ValueError:
        return DEFAULT_MAX_AGE_HOURS


def _stamp_mtime(directory: Path) -> float | None:
    """Only explicit refresh stamps prove a successful offline DB load."""
    for name in _STAMP_NAMES:
        marker = directory / name
        if marker.is_file():
            try:
                return marker.stat().st_mtime
            except OSError:
                continue
    return None


def _data_file_count(directory: Path) -> int:
    """Count real offline packs (ecosystem zip), not README/status placeholders."""
    count = 0
    try:
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            name = path.name
            if name in _IGNORE_NAMES:
                continue
            if name in _STAMP_NAMES or name.startswith(".ai_stp"):
                continue
            # osv-scanner layout: …/{ecosystem}/all.zip or other .zip packs
            if name == "all.zip" or name.endswith(".zip"):
                count += 1
    except OSError:
        return 0
    return count


def osv_db_status() -> dict[str, Any]:
    """Return offline OSV DB health fields (never raises).

    reason is one of: not_configured | directory_missing | no_files | stale | ok
    """
    configured_raw = os.environ.get("AI_STP_OSV_OFFLINE_DIR", "").strip()
    directory = osv_offline_dir()
    max_age = max_age_hours()
    path_str = configured_raw or (str(directory) if directory else "")

    if directory is None:
        return {
            "configured": bool(configured_raw),
            "path": path_str,
            "present": False,
            "fresh": False,
            "age_hours": None,
            "max_age_hours": max_age,
            "file_count": 0,
            "reason": "not_configured" if not configured_raw else "directory_missing",
        }
    if not directory.is_dir():
        return {
            "configured": True,
            "path": str(directory),
            "present": False,
            "fresh": False,
            "age_hours": None,
            "max_age_hours": max_age,
            "file_count": 0,
            "reason": "directory_missing",
        }

    file_count = _data_file_count(directory)
    stamp = _stamp_mtime(directory)
    if stamp is None:
        # Placeholder README only, or data without refresh stamp → not fresh.
        return {
            "configured": True,
            "path": str(directory),
            "present": file_count > 0,
            "fresh": False,
            "age_hours": None,
            "max_age_hours": max_age,
            "file_count": file_count,
            "reason": "no_files" if file_count == 0 else "no_stamp",
        }

    age_hours = max(0.0, (time.time() - stamp) / 3600.0)
    fresh = age_hours <= max_age and file_count > 0
    if file_count == 0:
        reason = "no_files"
        fresh = False
    elif age_hours > max_age:
        reason = "stale"
    else:
        reason = "ok"
    return {
        "configured": True,
        "path": str(directory),
        "present": True,
        "fresh": fresh,
        "age_hours": round(age_hours, 3),
        "max_age_hours": max_age,
        "file_count": file_count,
        "reason": reason,
    }


def osv_db_ready(*, require_fresh: bool = False) -> bool:
    """Boolean probe for optional readiness gates.

    Default: offline DB is optional (API readiness must not die without cron).
    When ``AI_STP_OSV_REQUIRE_FRESH=1`` or require_fresh=True, require stamp +
    non-empty data within max age — empty placeholder dirs fail closed.
    """
    env_require = os.environ.get("AI_STP_OSV_REQUIRE_FRESH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    require = require_fresh or env_require
    status = osv_db_status()
    if not require:
        return True
    return bool(status.get("present") and status.get("fresh") and status.get("reason") == "ok")
