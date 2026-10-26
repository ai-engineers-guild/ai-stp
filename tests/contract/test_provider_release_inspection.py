"""Release observations must not silently become installation evidence."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".github/scripts/inspect-provider-release.py"
SPEC = importlib.util.spec_from_file_location("provider_release_inspection", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
INSPECTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSPECTION)

COMMIT = "a" * 40


def report() -> dict[str, Any]:
    return {
        "artifact": {
            "harness_id": "codex",
            "version": "0.0.95",
            "project": "codex-setup-system",
            "platform": "linux/x86_64",
            "trust_level": "verified_publisher",
            "source_commit": COMMIT,
        },
        "provider_info": {
            "harness_id": "codex",
            "provider_version": "0.0.95",
            "provider_id": "codex-setup-system",
            "scoped_projection_profiles": [
                {
                    "target_scope": "project",
                    "component_kinds": ["skill"],
                    "native_namespaces": [".agents/skills"],
                }
            ],
        },
        "network": {
            "enforcement": "enforced",
            "isolated": "denied",
            "positive_control": ["ipv4_tcp", "ipv6_tcp", "ipv4_udp"],
        },
        "harness_written": False,
        "installed": False,
    }


def test_exact_observation_is_accepted_without_granting_installation() -> None:
    value = report()
    before = copy.deepcopy(value)
    INSPECTION.validate_report(value, "codex", "0.0.95", COMMIT)
    assert value == before
    assert value["installed"] is False


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("artifact", "harness_id", "pi"),
        ("artifact", "version", "0.0.94"),
        ("artifact", "project", "pi-setup-system"),
        ("artifact", "platform", "macos/arm64"),
        ("artifact", "trust_level", "unverified"),
        ("artifact", "source_commit", "b" * 40),
        ("network", "enforcement", "unavailable"),
        ("network", "isolated", "allowed"),
        ("network", "positive_control", ["ipv4_tcp", "ipv6_tcp"]),
        ("provider_info", "scoped_projection_profiles", []),
    ],
)
def test_incomplete_or_different_evidence_refuses(section: str, field: str, value: object) -> None:
    observed = report()
    observed[section][field] = value
    with pytest.raises(ValueError):
        INSPECTION.validate_report(observed, "codex", "0.0.95", COMMIT)


@pytest.mark.parametrize("field", ["installed", "harness_written"])
def test_inspection_never_accepts_an_effect_claim(field: str) -> None:
    observed = report()
    observed[field] = True
    with pytest.raises(ValueError):
        INSPECTION.validate_report(observed, "codex", "0.0.95", COMMIT)
