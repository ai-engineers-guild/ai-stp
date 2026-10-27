"""Fence the exact legacy-source assessment before its advisory ID is filtered."""

from __future__ import annotations

import json
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ADVISORY = "GHSA-qwgh-2vcv-g2f7"
LEGACY_VERSION = "0.10.4"
LEGACY_CHECKSUM = "3078c7629b62d3f0439517fa394996acacc5cbc91c5a20d8c658e77abd503a71"
REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"
REVIEW_BEFORE = date(2026, 11, 3)
ROOT = Path(__file__).resolve().parents[2]
SCOPES = ("apps/cli", "apps/desktop/src-tauri")
NAMES = {"block-buffer", "block_buffer"}
AUDITED_SOURCES = {
    LEGACY_VERSION: LEGACY_CHECKSUM,
    "0.12.1": "d2f6c7dbe95a6ed67ad9f18e57daf93a2f034c524b99fd2b76d18fdfeb6660aa",
}


def _legacy_edge(dependency: str, only_legacy: bool) -> bool:
    fields = dependency.split()
    return bool(
        fields
        and fields[0] in NAMES
        and (
            (len(fields) == 1 and only_legacy) or (len(fields) >= 2 and fields[1] == LEGACY_VERSION)
        )
    )


def validate_scope(lock: dict[str, Any], config: dict[str, Any], today: date) -> bool:
    """Refuse an expired, stale or broader disposition; OSV still scans the lock."""
    entries: list[dict[str, Any]] = config.get("IgnoredVulns", [])
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        raise ValueError("invalid advisory configuration")
    selected = [item for item in entries if item.get("id") == ADVISORY]
    if not selected:
        return False
    if (
        len(selected) != 1
        or selected[0].get("ignoreUntil") != REVIEW_BEFORE
        or today >= REVIEW_BEFORE
        or not isinstance(selected[0].get("reason"), str)
        or not selected[0]["reason"].strip()
    ):
        raise ValueError("legacy buffer assessment needs current explicit review")
    packages: list[dict[str, Any]] = lock.get("package", [])
    if not isinstance(packages, list) or any(not isinstance(item, dict) for item in packages):
        raise ValueError("invalid Cargo package inventory")
    buffers = [item for item in packages if item.get("name") in NAMES]
    legacy = [item for item in buffers if item.get("version") == LEGACY_VERSION]
    if len(legacy) != 1:
        raise ValueError("remove the stale or ambiguous legacy buffer assessment")
    for item in buffers:
        version = item.get("version")
        if not isinstance(version, str) or version not in AUDITED_SOURCES:
            raise ValueError("an unaudited buffer version cannot inherit this assessment")
        if item.get("source") != REGISTRY or item.get("checksum") != AUDITED_SOURCES[version]:
            raise ValueError("buffer source differs from the audited crate")
    # The version-specific regression dependency must not keep an otherwise
    # obsolete exception alive after upstream transitive consumers disappear.
    consumed = False
    for item in packages:
        if item.get("name") == "ai-stp-cli":
            continue
        dependencies: list[str] = item.get("dependencies", [])
        if not isinstance(dependencies, list) or any(
            not isinstance(value, str) for value in dependencies
        ):
            raise ValueError("invalid Cargo dependency inventory")
        if any(_legacy_edge(value, len(buffers) == 1) for value in dependencies):
            consumed = True
    if not consumed:
        raise ValueError("remove the legacy regression pin and assessment with their last consumer")
    return True


def main() -> None:
    checked = 0
    for scope in SCOPES:
        directory = ROOT / scope
        config_path = directory / "osv-scanner.toml"
        config = tomllib.loads(config_path.read_text()) if config_path.exists() else {}
        lock = tomllib.loads((directory / "Cargo.lock").read_text())
        try:
            checked += int(validate_scope(lock, config, datetime.now(UTC).date()))
        except ValueError as error:
            raise SystemExit(f"advisory scope refused for {scope}: {error}") from error
    print(
        json.dumps(
            {
                "advisory": ADVISORY,
                "audited_legacy_version": LEGACY_VERSION,
                "validated_scopes": checked,
                "review_before": REVIEW_BEFORE.isoformat(),
            }
        )
    )


if __name__ == "__main__":
    main()
