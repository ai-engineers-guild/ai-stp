"""Catalog assignment coordinates cannot change kind or use floating versions."""

import pytest
from pydantic import ValidationError

from ai_stp_contracts.corporate import (
    CorporateAssignmentPlan,
    CorporateAssignmentPlanRequest,
    CorporateCatalogAssignmentRequest,
    CorporateDistributionRequest,
    CorporateDistributionResult,
    CorporateDistributionStateList,
    CorporateDistributionStateQuery,
    CorporateEffectiveAssignmentQuery,
)
from ai_stp_contracts.machine_help import ManagedVerification, ManagedVerificationItem
from ai_stp_foundation.ids import new_id


def _base() -> dict[str, object]:
    return {
        "subject_kind": "team",
        "subject_id": new_id("operation"),
        "object_kind": "setup",
        "stable_id": new_id("setup"),
        "version": "1.0",
        "expected_revision": 0,
        "authorization_revision": 1,
        "idempotency_key": "assignment-fixture",
    }


def test_assignment_requires_typed_subject_and_exact_version() -> None:
    payload = _base()
    assert CorporateCatalogAssignmentRequest.model_validate(payload).version == "1.0"
    for changes in (
        {"subject_kind": "employee"},
        {"object_kind": "component"},
        {"version": "latest"},
        {"version": "1.0.0"},
        {"version": "*"},
        {"state": "retired"},
        {"expected_revision": -1},
        {"install": True},
    ):
        with pytest.raises(ValidationError):
            CorporateCatalogAssignmentRequest.model_validate({**payload, **changes})


def test_technology_is_a_typed_assignment_subject() -> None:
    payload = {
        "subject_kind": "technology",
        "subject_id": new_id("technology"),
        "object_kind": "component",
        "stable_id": new_id("component"),
        "version": "2.0",
        "expected_revision": 0,
        "authorization_revision": 1,
        "idempotency_key": "technology-assignment-fixture",
    }
    assert CorporateCatalogAssignmentRequest.model_validate(payload).subject_kind == "technology"


def test_organization_is_a_typed_assignment_subject() -> None:
    payload = {
        **_base(),
        "subject_kind": "organization",
        "subject_id": new_id("organization"),
        "selector": "latest",
        "version": None,
    }
    del payload["version"]
    request = CorporateCatalogAssignmentRequest.model_validate(payload)
    assert request.subject_kind == "organization"
    assert request.selector == "latest"


def test_latest_selector_never_pins_a_mutable_coordinate() -> None:
    payload = {**_base(), "selector": "latest", "version": None}
    del payload["version"]
    request = CorporateCatalogAssignmentRequest.model_validate(payload)
    assert request.selector == "latest"
    for changes in (
        {"version": "1.0"},
        {"passport_digest": "sha256:" + "0" * 64},
        {"selector": "exact"},
    ):
        with pytest.raises(ValidationError):
            CorporateCatalogAssignmentRequest.model_validate({**payload, **changes})


def test_exact_selector_accepts_digest_and_harness_pins() -> None:
    request = CorporateCatalogAssignmentRequest.model_validate(
        {
            **_base(),
            "passport_digest": "sha256:" + "a" * 64,
            "harness": "claude-code",
        }
    )
    assert request.harness == "claude-code"
    with pytest.raises(ValidationError):
        CorporateCatalogAssignmentRequest.model_validate(
            {**_base(), "passport_digest": "not-a-digest"}
        )
    with pytest.raises(ValidationError):
        CorporateCatalogAssignmentRequest.model_validate({**_base(), "harness": "unknown"})


def test_effective_query_requires_typed_catalog_identity() -> None:
    query = CorporateEffectiveAssignmentQuery.model_validate(
        {
            "account_id": new_id("account"),
            "object_kind": "setup",
            "stable_id": new_id("setup"),
            "harness": "codex",
        }
    )
    assert query.harness == "codex"
    with pytest.raises(ValidationError):
        CorporateEffectiveAssignmentQuery.model_validate(
            {
                "account_id": new_id("account"),
                "object_kind": "component",
                "stable_id": new_id("setup"),
            }
        )


def _distribution_base() -> dict[str, object]:
    return {
        "source_assignment_id": new_id("operation"),
        "action": "assign",
        "dry_run": True,
        "expected_revision": 1,
        "authorization_revision": 1,
        "idempotency_key": "distribution-fixture",
    }


def test_distribution_request_requires_typed_action_and_revisions() -> None:
    payload = _distribution_base()
    request = CorporateDistributionRequest.model_validate(payload)
    assert request.action == "assign"
    assert request.dry_run is True
    changes: tuple[dict[str, object], ...] = (
        {"action": "install"},
        {"action": "grant"},
        {"expected_revision": 0},
        {"authorization_revision": -1},
        {"source_assignment_id": ""},
        {"install": True},
        {"targets": []},
    )
    for change in changes:
        with pytest.raises(ValidationError):
            CorporateDistributionRequest.model_validate({**payload, **change})


def test_distribution_result_carries_typed_target_outcomes() -> None:
    result = CorporateDistributionResult.model_validate(
        {
            "schema_version": 1,
            "organization_id": new_id("organization"),
            "source_assignment_id": new_id("operation"),
            "action": "revoke",
            "dry_run": False,
            "source_revision": 2,
            "targets": [
                {
                    "target_kind": "employee",
                    "target_id": new_id("account"),
                    "result": "applied",
                    "state": "revoked",
                },
                {
                    "target_kind": "project",
                    "target_id": new_id("remote_project"),
                    "result": "conflicted",
                    "overriding_assignment_id": new_id("operation"),
                },
            ],
            "exclusions": [
                {
                    "target_kind": "employee",
                    "target_id": new_id("account"),
                    "reason": "membership_inactive",
                }
            ],
            "counts": {
                "applied": 1,
                "skipped": 0,
                "conflicted": 1,
                "denied": 0,
                "failed": 0,
            },
        }
    )
    assert result.targets[0].state == "revoked"
    assert result.targets[1].result == "conflicted"
    assert result.exclusions[0].reason == "membership_inactive"
    for changes in (
        {"result": "mutated"},
        {"target_kind": "team"},
        {"state": "installing"},
    ):
        with pytest.raises(ValidationError):
            CorporateDistributionResult.model_validate(
                {
                    "schema_version": 1,
                    "organization_id": new_id("organization"),
                    "source_assignment_id": new_id("operation"),
                    "action": "assign",
                    "dry_run": False,
                    "source_revision": 1,
                    "targets": [
                        {
                            "target_kind": "employee",
                            "target_id": new_id("account"),
                            "result": "applied",
                            **changes,
                        }
                    ],
                }
            )


def test_distribution_state_query_and_list_are_bounded() -> None:
    query = CorporateDistributionStateQuery.model_validate(
        {"source_assignment_id": new_id("operation")}
    )
    assert query.limit == 128
    with pytest.raises(ValidationError):
        CorporateDistributionStateQuery.model_validate(
            {"source_assignment_id": new_id("operation"), "limit": 0}
        )
    with pytest.raises(ValidationError):
        CorporateDistributionStateQuery.model_validate(
            {"source_assignment_id": new_id("operation"), "limit": 257}
        )
    state = CorporateDistributionStateList.model_validate(
        {
            "schema_version": 1,
            "organization_id": new_id("organization"),
            "source_assignment_id": new_id("operation"),
            "source_revision": 4,
            "source_state": "retired",
            "items": [
                {
                    "target_kind": "employee",
                    "target_id": new_id("account"),
                    "result": "applied",
                    "state": "revoked",
                    "operation_revision": 4,
                }
            ],
            "total": 1,
        }
    )
    assert state.source_state == "retired"
    assert state.items[0].state == "revoked"


def _plan_base() -> dict[str, object]:
    return {
        "account_id": new_id("account"),
        "harness": "claude-code",
    }


def test_plan_request_requires_harness_and_typed_materialized() -> None:
    payload = _plan_base()
    request = CorporateAssignmentPlanRequest.model_validate(payload)
    assert request.harness == "claude-code"
    assert request.materialized == []
    materialized = {
        "object_kind": "setup",
        "stable_id": new_id("setup"),
        "version": "1.0",
    }
    assert (
        CorporateAssignmentPlanRequest.model_validate({**payload, "materialized": [materialized]})
        .materialized[0]
        .version
        == "1.0"
    )
    changes: tuple[dict[str, object], ...] = (
        {"harness": "vi"},
        {"account_id": "not-an-account"},
        {"materialized": [materialized, materialized]},
        {
            "materialized": [
                {
                    "object_kind": "setup",
                    "stable_id": materialized["stable_id"],
                    "version": "latest",
                }
            ]
        },
        {
            "materialized": [
                {
                    "object_kind": "component",
                    "stable_id": materialized["stable_id"],
                    "version": "1.0",
                }
            ]
        },
        {"install": True},
    )
    for change in changes:
        with pytest.raises(ValidationError):
            CorporateAssignmentPlanRequest.model_validate({**payload, **change})


def test_plan_carries_typed_outcomes_and_exact_coordinates() -> None:
    plan = CorporateAssignmentPlan.model_validate(
        {
            "schema_version": 1,
            "organization_id": new_id("organization"),
            "account_id": new_id("account"),
            "harness": "codex",
            "items": [
                {
                    "object_kind": "setup",
                    "stable_id": new_id("setup"),
                    "state": "assigned",
                    "outcome": "outdated",
                    "action": "update",
                    "source_scope": "team",
                    "source_subject_id": new_id("operation"),
                    "version": "2.0",
                    "installed_version": "1.0",
                },
                {
                    "object_kind": "component",
                    "stable_id": new_id("component"),
                    "state": "unassigned",
                    "outcome": "unassigned",
                    "action": "remove",
                    "installed_version": "3.0",
                },
            ],
            "total": 2,
        }
    )
    assert plan.items[0].outcome == "outdated"
    assert plan.items[0].version == "2.0"
    assert plan.items[1].action == "remove"
    for changes in (
        {"outcome": "absent"},
        {"action": "deploy"},
        {"version": "latest"},
        {"state": "current"},
    ):
        with pytest.raises(ValidationError):
            CorporateAssignmentPlan.model_validate(
                {
                    "schema_version": 1,
                    "organization_id": new_id("organization"),
                    "account_id": new_id("account"),
                    "harness": "codex",
                    "items": [
                        {
                            "object_kind": "setup",
                            "stable_id": new_id("setup"),
                            "state": "assigned",
                            "outcome": "missing",
                            "action": "install",
                            **changes,
                        }
                    ],
                    "total": 1,
                }
            )


def test_managed_verification_binds_context_and_classifies_items() -> None:
    verification = ManagedVerification.model_validate(
        {
            "schema_version": 1,
            "status": "fail",
            "project_id": "project_local",
            "harness_id": "claude-code",
            "organization_id": new_id("organization"),
            "account_id": new_id("account"),
            "target_id": "project_local:claude-code",
            "operation_id": new_id("operation"),
            "verified_at": "2026-09-19T10:00:00.000Z",
            "checked_at": "2026-09-20T10:00:00.000Z",
            "corporate": "evaluated",
            "verified_target_digest": "sha256:" + "0" * 64,
            "observed_target_digest": "sha256:" + "f" * 64,
            "items": [
                {
                    "schema_version": 1,
                    "subject": "component",
                    "stable_id": new_id("component"),
                    "component_kind": "skill",
                    "version": "1.0",
                    "passport_digest": "sha256:" + "b" * 64,
                    "classification": "locally_modified",
                    "outcome": "installed",
                },
                {
                    "schema_version": 1,
                    "subject": "path",
                    "path": "skills/review/SKILL.md",
                    "change": "modified",
                    "expected_digest": "sha256:" + "a" * 64,
                    "observed_digest": "sha256:" + "c" * 64,
                    "classification": "locally_modified",
                },
            ],
            "diagnostics": ["a managed file changed outside the provider path"],
        }
    )
    assert verification.status == "fail"
    assert verification.items[0].outcome == "installed"
    assert verification.items[1].path == "skills/review/SKILL.md"
    for changes in (
        {"status": "dirty"},
        {"corporate": "cached"},
    ):
        with pytest.raises(ValidationError):
            ManagedVerification.model_validate(
                {
                    "schema_version": 1,
                    "status": "pass",
                    "project_id": "project_local",
                    "harness_id": "claude-code",
                    **changes,
                }
            )
    for changes in (
        {"classification": "tampered"},
        {"subject": "file"},
        {"outcome": "deploy"},
    ):
        with pytest.raises(ValidationError):
            ManagedVerificationItem.model_validate(
                {"schema_version": 1, "subject": "setup", "classification": "unchanged", **changes}
            )
