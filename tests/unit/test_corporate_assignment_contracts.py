"""Catalog assignment coordinates cannot change kind or use floating versions."""

import pytest
from pydantic import ValidationError

from ai_stp_contracts.corporate import (
    CorporateCatalogAssignmentRequest,
    CorporateEffectiveAssignmentQuery,
)
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
