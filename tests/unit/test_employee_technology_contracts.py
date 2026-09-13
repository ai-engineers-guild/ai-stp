"""Competence requests are strict operational links, not evidence or authority."""

import pytest
from pydantic import ValidationError

from ai_stp_contracts.technology import EmployeeTechnologyRequest
from ai_stp_foundation.ids import new_id


def test_competence_request_validates_identity_revision_and_forbids_metadata() -> None:
    payload = {
        "account_id": new_id("account"),
        "technology_id": new_id("technology"),
        "expected_revision": 0,
        "authorization_revision": 1,
        "idempotency_key": "competence-contract-fixture",
    }
    assert EmployeeTechnologyRequest.model_validate(payload).state == "current"
    assert (
        EmployeeTechnologyRequest.model_validate({**payload, "state": "retired"}).state == "retired"
    )
    for change in [
        {"account_id": new_id("organization")},
        {"technology_id": new_id("project")},
        {"expected_revision": -1},
        {"authorization_revision": 0},
        {"evidence": "manual"},
        {"role": "superadmin"},
        {"state": "confirmed"},
    ]:
        with pytest.raises(ValidationError):
            EmployeeTechnologyRequest.model_validate({**payload, **change})
