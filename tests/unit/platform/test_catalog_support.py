"""Provider support projection tests (SPEC-033, ADR-0072)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_stp_contracts.catalog import CatalogSupport, ComponentSearchRequest
from ai_stp_platform.catalog_read import CatalogIntegrityError
from ai_stp_platform.catalog_support import (
    project_support,
    support_matches_filters,
    support_tier_for_harness,
)

pytestmark = pytest.mark.platform

_NOW = datetime(2026, 8, 8, 12, tzinfo=UTC)
_PASSPORT = {"harness_id": "opencode"}


def evidence(**overrides: object) -> dict[str, object]:
    return {
        "check_id": "provider-startup",
        "policy_version": "support-v1",
        "result": "passed",
        "source": "provider_release_evidence",
        "provider_id": "opencode",
        "provider_version": "1.17.7",
        "release_reference": "a" * 40,
        "operating_system": "ubuntu",
        "architecture": "x86_64",
        "mandatory": True,
        "observed_at": "2026-08-07T12:00:00.000Z",
        "expires_at": "2026-09-07T12:00:00.000Z",
        **overrides,
    }


def test_support_is_beta_until_mandatory_evidence_passes() -> None:
    missing = project_support(_PASSPORT, [], now=_NOW)
    verified = project_support(_PASSPORT, [evidence()], now=_NOW)

    assert missing.tier == "beta"
    assert missing.state == "missing"
    assert verified.state == "verified"


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ("warning", "not_verified"),
        ("failed", "not_verified"),
        ("degraded", "not_verified"),
        ("not_run", "not_verified"),
    ],
)
def test_non_passing_mandatory_evidence_is_not_verified(result: str, expected: str) -> None:
    support = project_support(_PASSPORT, [evidence(result=result)], now=_NOW)

    assert support.state == expected


def test_expired_evidence_is_stale() -> None:
    support = project_support(
        _PASSPORT,
        [evidence(expires_at="2026-08-08T11:59:59.000Z")],
        now=_NOW,
    )

    assert support.state == "stale"


def test_malformed_evidence_cannot_become_verified() -> None:
    support = project_support(
        _PASSPORT,
        [evidence(release_reference="not-a-release")],
        now=_NOW,
    )

    assert support.state == "not_verified"
    assert support.evidence == []


def test_support_accepts_exact_digest_reference() -> None:
    support = project_support(
        _PASSPORT,
        [evidence(release_reference="sha256:" + "b" * 64)],
        now=_NOW,
    )

    assert support.state == "verified"
    assert support.evidence[0].release_reference.startswith("sha256:")


def test_conflicting_evidence_for_one_matrix_context_is_not_verified() -> None:
    support = project_support(
        _PASSPORT,
        [evidence(), evidence(result="failed")],
        now=_NOW,
    )

    assert support.state == "not_verified"


def test_verified_support_requires_mandatory_passed_evidence() -> None:
    with pytest.raises(ValidationError):
        CatalogSupport(tier="beta", state="verified", evidence=[])


def test_support_evidence_rejects_missing_exact_provenance() -> None:
    invalid = evidence()
    invalid.pop("release_reference")
    support = project_support(_PASSPORT, [invalid], now=_NOW)

    assert support.state == "not_verified"
    assert support.evidence == []


def test_support_request_rejects_unknown_enum_values() -> None:
    with pytest.raises(ValidationError):
        ComponentSearchRequest(support_tier="experimental")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ComponentSearchRequest(support_state="fresh")  # type: ignore[arg-type]


def test_support_filters_are_independent_from_trust_lane() -> None:
    support = project_support(_PASSPORT, [evidence()], now=_NOW)

    assert support_matches_filters(support, support_tier="beta", support_state="verified")
    assert not support_matches_filters(support, support_tier="primary", support_state=None)
    assert not support_matches_filters(support, support_tier=None, support_state="missing")


def test_unknown_harness_cannot_receive_a_support_tier() -> None:
    with pytest.raises(CatalogIntegrityError, match="unsupported harness"):
        support_tier_for_harness("unknown-harness")


def test_explicitly_expired_evidence_is_stale() -> None:
    support = project_support(_PASSPORT, [evidence(result="expired")], now=_NOW)

    assert support.state == "stale"


def test_evidence_without_expiry_uses_the_passed_result() -> None:
    support = project_support(_PASSPORT, [evidence(expires_at=None)], now=_NOW)

    assert support.state == "verified"
