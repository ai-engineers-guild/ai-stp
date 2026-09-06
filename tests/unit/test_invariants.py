"""Golden vectors for logical and harness-invariant digests (SPEC-064/065)."""

from __future__ import annotations

import json
import pathlib
from typing import cast

from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.invariants import (
    COMPONENT_LOGICAL_DOMAIN,
    SETUP_INVARIANT_DOMAIN,
    component_logical_digest,
    component_logical_payload,
    setup_harness_invariant_digest,
    setup_invariant_payload,
)

GOLDEN = pathlib.Path(__file__).parents[1] / "golden" / "passports"


def _passport(name: str) -> dict[str, JsonValue]:
    raw = json.loads((GOLDEN / name).read_text(encoding="utf-8"))["value"]
    return cast(dict[str, JsonValue], raw)


def test_component_logical_digest_is_stable_and_excludes_adaptations() -> None:
    component = _passport("component-version.json")
    payload = component_logical_payload(component)
    assert isinstance(payload, dict)
    assert "adaptations" not in payload
    assert "origin_harness_id" not in payload
    first = component_logical_digest(component)
    mutated = dict(component)
    mutated["adaptations"] = []
    mutated["origin_harness_id"] = "codex"
    assert component_logical_digest(mutated) == first
    changed = dict(component)
    changed["component_type"] = "mcp"
    assert component_logical_digest(changed) != first
    assert first.startswith("sha256:")
    assert COMPONENT_LOGICAL_DOMAIN.startswith("ai-stp:component-logical")


def test_setup_invariant_changes_only_for_declared_inputs() -> None:
    setup = _passport("setup-version.json")
    components = setup["components"]
    assert isinstance(components, list)
    members = ["sha256:" + "a" * 64] * len(components)
    first = setup_harness_invariant_digest(setup, members)
    payload = setup_invariant_payload(setup, members)
    assert isinstance(payload, dict)
    assert "harness_id" not in payload
    native = dict(setup)
    native["harness_id"] = "codex"
    native["ported_from"] = {
        "stable_id": "setup_01JQZK7B8N4M6P2R9T5V0X3YC1",
        "version": "1.0",
        "passport_digest": "sha256:" + "b" * 64,
    }
    assert setup_harness_invariant_digest(native, members) == first
    purpose = dict(setup)
    purpose["purpose"] = "other-purpose"
    assert setup_harness_invariant_digest(purpose, members) != first
    assert SETUP_INVARIANT_DOMAIN.startswith("ai-stp:setup-harness-invariant")
    other_members = ["sha256:" + "c" * 64] * len(components)
    assert setup_harness_invariant_digest(setup, other_members) != first
