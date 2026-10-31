"""A legacy-source finding cannot hide a changed graph or inherit an extension."""

from __future__ import annotations

import copy
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from scripts.safety.check_advisory_scope import (
    MINIMATCH_ADVISORY,
    MINIMATCH_REVIEW_BEFORE,
    validate_minimatch_scope,
)

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps/web"
TODAY = date(2026, 10, 31)


def config() -> dict[str, Any]:
    return tomllib.loads((WEB / "osv-scanner.toml").read_text())


def test_original_sources_and_reviewed_graph_are_accepted() -> None:
    assert validate_minimatch_scope(
        (WEB / "bun.lock").read_bytes(), (WEB / "package.json").read_bytes(), config(), TODAY
    )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b"minimatch@3.1.5", b"minimatch@3.1.6"),
        (b"minimatch@11.0.3", b"minimatch@10.2.6"),
        (b"sha512-VgjWUsnnT6n+NUk6", b"sha512-XgjWUsnnT6n+NUk6"),
    ],
)
def test_other_versions_or_source_integrity_cannot_inherit_review(old: bytes, new: bytes) -> None:
    lock = (WEB / "bun.lock").read_bytes()
    assert old in lock
    with pytest.raises(ValueError, match="graph differs"):
        validate_minimatch_scope(
            lock.replace(old, new), (WEB / "package.json").read_bytes(), config(), TODAY
        )


def test_a_new_package_patch_or_manifest_cannot_inherit_review() -> None:
    manifest = (WEB / "package.json").read_bytes()
    with pytest.raises(ValueError, match="graph differs"):
        validate_minimatch_scope((WEB / "bun.lock").read_bytes(), manifest + b"\n", config(), TODAY)


def test_expiry_extension_duplicate_and_blank_dispositions_refuse() -> None:
    original = config()
    invalid = [copy.deepcopy(original) for _ in range(3)]
    invalid[0]["IgnoredVulns"][0]["ignoreUntil"] = date(2027, 1, 1)
    invalid[1]["IgnoredVulns"].append(copy.deepcopy(original["IgnoredVulns"][0]))
    invalid[2]["IgnoredVulns"][0]["reason"] = ""
    for value, today in [(original, MINIMATCH_REVIEW_BEFORE), *[(x, TODAY) for x in invalid]]:
        with pytest.raises(ValueError, match="explicit review"):
            validate_minimatch_scope(
                (WEB / "bun.lock").read_bytes(), (WEB / "package.json").read_bytes(), value, today
            )


def test_without_this_disposition_the_full_scanner_remains_responsible() -> None:
    assert not validate_minimatch_scope(b"unreviewed", b"unreviewed", {}, TODAY)
    assert config()["IgnoredVulns"][0]["id"] == MINIMATCH_ADVISORY
