"""Portability claim contract (SPEC-064 REQ-6412/6413)."""

from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.invariants import portability_claim_id
from ai_stp_passports.versions import PortabilityClaim, seal_portability_claim


def _claim(**overrides: object) -> dict[str, JsonValue]:
    body: dict[str, JsonValue] = {
        "source_artifact_digest": "sha256:" + "a" * 64,
        "target_harness_ids": ["pi"],
        "transform_family": "portable-source",
        "transform_version": "1.0",
        "component_types": ["skill"],
        "scopes": ["project"],
        "evidence_refs": ["sha256:" + "b" * 64],
        "limitations": ["mcp tools are host-specific"],
        "issued_at": "2026-09-06T00:00:00.000Z",
        "expires_at": "2026-12-06T00:00:00.000Z",
    }
    body.update({key: cast(JsonValue, value) for key, value in overrides.items()})
    return body


def test_seal_portability_claim_binds_content_id() -> None:
    claim = seal_portability_claim(_claim())
    assert claim.claim_id == portability_claim_id(_claim())
    assert claim.target_harness_ids == ["pi"]


def test_portability_claim_rejects_duplicate_and_expired_targets() -> None:
    with pytest.raises(ValidationError):
        seal_portability_claim(_claim(target_harness_ids=["pi", "pi"]))
    with pytest.raises(ValidationError):
        seal_portability_claim(
            _claim(issued_at="2026-09-06T00:00:00.000Z", expires_at="2026-09-06T00:00:00.000Z")
        )
    with pytest.raises(ValidationError):
        PortabilityClaim.model_validate(_claim() | {"claim_id": "claim_" + "0" * 64})
