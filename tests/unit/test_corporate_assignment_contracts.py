"""Catalog assignment coordinates cannot change kind or use floating versions."""

import pytest
from pydantic import ValidationError

from ai_stp_contracts.corporate import CorporateCatalogAssignmentRequest
from ai_stp_foundation.ids import new_id


def test_assignment_requires_typed_subject_and_exact_version() -> None:
    payload = {
        "subject_kind": "team",
        "subject_id": new_id("operation"),
        "object_kind": "setup",
        "stable_id": new_id("setup"),
        "version": "1.0",
        "expected_revision": 0,
        "authorization_revision": 1,
        "idempotency_key": "assignment-fixture",
    }
    assert CorporateCatalogAssignmentRequest.model_validate(payload).version == "1.0"
    for changes in (
        {"subject_kind": "employee"},
        {"object_kind": "component"},
        {"version": "latest"},
        {"version": "1.0.0"},
        {"state": "retired"},
        {"expected_revision": -1},
        {"install": True},
    ):
        with pytest.raises(ValidationError):
            CorporateCatalogAssignmentRequest.model_validate({**payload, **changes})
