"""Exact vs claimed-portable projection rules (SPEC-064)."""

from __future__ import annotations

import pytest

from ai_stp_contracts.assurance import (
    ClaimTargetRow,
    ExactTargetRow,
    TargetMatrix,
)
from ai_stp_platform.catalog_targets import (
    alignment_state,
    assurance_counts,
    claimed_harness_ids,
    conservative_component_verified,
    homogeneous_projection_kind,
    missing_exact_adaptation_pins,
    owner_target_gaps,
    setup_composition,
)

pytestmark = pytest.mark.platform


def test_claimed_harness_ids_exclude_exact_adaptations() -> None:
    passport = {
        "adaptations": [{"harness_id": "claude-code"}],
        "portability_claims": [{"target_harness_ids": ["claude-code", "pi"]}],
    }
    assert claimed_harness_ids(passport) == ["pi"]


def test_assurance_counts_ignore_claim_rows() -> None:
    matrix = TargetMatrix(
        exact=[
            ExactTargetRow(
                harness_id="claude-code",
                adaptation_id="adaptation_" + "a" * 64,
                scope="global",
                implementation_mode="native",
                projection_kind="native_files",
                technical_support="experimental",
                assessment_state="not_verified",
            )
        ],
        claimed_portable=[
            ClaimTargetRow(
                harness_id="pi",
                claim_id="claim_" + "b" * 64,
                transform_family="portable-source",
                transform_version="1.0",
                issued_at="2026-09-06T00:00:00.000Z",
            )
        ],
    )
    counts = assurance_counts(matrix)
    assert counts.verified_targets == 0
    assert counts.assessed_targets == 1
    passed_checks = {
        "checks": [
            {"mandatory": True, "result": "passed"},
            {"mandatory": True, "result": "passed"},
        ]
    }
    assert conservative_component_verified(checks_summary=passed_checks, matrix=matrix) is False
    verified_matrix = TargetMatrix(
        exact=[
            ExactTargetRow(
                harness_id="claude-code",
                adaptation_id="adaptation_" + "a" * 64,
                scope="global",
                implementation_mode="native",
                projection_kind="native_files",
                technical_support="supported",
                assessment_state="verified",
            ),
            ExactTargetRow(
                harness_id="codex",
                adaptation_id="adaptation_" + "c" * 64,
                scope="global",
                implementation_mode="native",
                projection_kind="native_files",
                technical_support="supported",
                assessment_state="verified",
            ),
            ExactTargetRow(
                harness_id="pi",
                adaptation_id="adaptation_" + "d" * 64,
                scope="global",
                implementation_mode="native",
                projection_kind="native_files",
                technical_support="supported",
                assessment_state="stale",
            ),
        ]
    )
    assert (
        conservative_component_verified(checks_summary=passed_checks, matrix=verified_matrix)
        is False
    )
    all_verified = TargetMatrix(
        exact=[
            row.model_copy(update={"assessment_state": "verified"}) for row in verified_matrix.exact
        ]
    )
    assert (
        conservative_component_verified(checks_summary=passed_checks, matrix=all_verified) is True
    )
    assert conservative_component_verified(checks_summary=None, matrix=all_verified) is False
    gaps = owner_target_gaps(matrix)
    assert any(item.reason_code == "claim_only" for item in gaps)
    assert all(item.state != "verified" for item in gaps)


def test_setup_composition_rejects_a_claim_only_target() -> None:
    from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport
    from ai_stp_platform.catalog_seed import seed_corpus

    setup_document = next(passport for kind, passport, *_ in seed_corpus() if kind == "setup")
    setup = SetupVersionPassport.model_validate({**setup_document, "harness_id": "pi"})
    pin = setup.components[0]
    component = ComponentVersionPassport.model_validate(
        next(
            passport
            for kind, passport, *_ in seed_corpus()
            if kind == "component"
            and passport["stable_id"] == pin.stable_id
            and passport["version"] == pin.version
        )
    )
    assert missing_exact_adaptation_pins(setup, {component.stable_id: component}) == [
        component.stable_id
    ]
    with pytest.raises(ValueError, match="exact adaptation"):
        setup_composition(setup, {component.stable_id: component})


def test_alignment_states_cover_the_closed_set() -> None:
    assert (
        alignment_state(
            member_digest="sha256:" + "a" * 64,
            baseline_digest="sha256:" + "a" * 64,
            member_accessible=True,
            authorized=False,
        )
        == "aligned"
    )
    assert (
        alignment_state(
            member_digest="sha256:" + "a" * 64,
            baseline_digest="sha256:" + "b" * 64,
            member_accessible=True,
            authorized=False,
        )
        == "diverged"
    )
    assert (
        alignment_state(
            member_digest=None,
            baseline_digest="sha256:" + "a" * 64,
            member_accessible=True,
            authorized=False,
        )
        == "unknown"
    )
    assert (
        alignment_state(
            member_digest=None,
            baseline_digest=None,
            member_accessible=False,
            authorized=True,
        )
        == "missing"
    )
    assert (
        alignment_state(
            member_digest=None,
            baseline_digest=None,
            member_accessible=False,
            authorized=False,
        )
        == "unknown"
    )


def test_homogeneous_projection_kind_is_omitted_when_adaptations_differ() -> None:
    from types import SimpleNamespace

    same = SimpleNamespace(
        adaptations=[
            SimpleNamespace(scope_adaptations=[SimpleNamespace(projection_kind="native_files")]),
            SimpleNamespace(scope_adaptations=[SimpleNamespace(projection_kind="native_files")]),
        ]
    )
    mixed = SimpleNamespace(
        adaptations=[
            SimpleNamespace(scope_adaptations=[SimpleNamespace(projection_kind="native_files")]),
            SimpleNamespace(scope_adaptations=[SimpleNamespace(projection_kind="marketplace")]),
        ]
    )
    assert homogeneous_projection_kind(same) == "native_files"  # type: ignore[arg-type]
    assert homogeneous_projection_kind(mixed) is None  # type: ignore[arg-type]
