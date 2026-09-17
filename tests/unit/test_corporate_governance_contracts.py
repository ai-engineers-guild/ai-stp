"""Typed corporate governance coordinates stay tenant-safe and exact."""

import pytest
from pydantic import ValidationError

from ai_stp_api.errors import ApiError
from ai_stp_api.slices.corporate.governance import validate_lifecycle_transition
from ai_stp_contracts.corporate_catalog_ownership import CorporateCatalogOwnershipRequest
from ai_stp_foundation.ids import new_id


def test_ownership_accepts_non_employee_subjects() -> None:
    payload = CorporateCatalogOwnershipRequest(
        object_kind="setup",
        stable_id=new_id("setup"),
        version="1.0",
        owner_kind="team",
        owner_id=new_id("operation"),
        expected_revision=0,
        authorization_revision=1,
        idempotency_key="corporate-owner-team-0001",
    )
    assert payload.owner_id is not None


def test_ownership_rejects_mixed_typed_subjects() -> None:
    with pytest.raises(ValidationError):
        CorporateCatalogOwnershipRequest(
            object_kind="setup",
            stable_id=new_id("setup"),
            version="1.0",
            owner_kind="team",
            owner_id=new_id("operation"),
            owner_account_id=new_id("account"),
            expected_revision=1,
            authorization_revision=1,
            idempotency_key="corporate-owner-team-0002",
        )


def test_corporate_lifecycle_transitions_support_hide_restore_and_retire() -> None:
    for previous, next_state in (
        (None, "visible"),
        ("visible", "hidden"),
        ("hidden", "visible"),
        ("visible", "deprecated"),
        ("deprecated", "retired"),
        ("retired", "visible"),
    ):
        validate_lifecycle_transition(previous, next_state)
    with pytest.raises(ApiError):
        validate_lifecycle_transition("retired", "hidden")
