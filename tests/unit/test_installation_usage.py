"""The installation fact boundary accepts coordinates and refuses content."""

import pytest
from pydantic import ValidationError

from ai_stp_contracts.installation_usage import InstallationOperationFact
from ai_stp_foundation.ids import new_id


def test_installation_fact_has_a_closed_content_free_boundary() -> None:
    fields = {
        "operation_id": new_id("operation"),
        "organization_id": new_id("organization"),
        "employee_id": new_id("account"),
        "device_id": new_id("device"),
        "project_id": new_id("remote_project"),
        "harness": "codex",
        "scope": "project",
        "action": "install",
        "result": "partial",
        "occurred_at": "2026-09-26T00:00:00.000Z",
    }
    fact = InstallationOperationFact(**fields)  # pyright: ignore[reportArgumentType]
    assert not fact.components_complete
    for forbidden in ("absolute_path", "prompt", "arguments", "model_output", "secret"):
        with pytest.raises(ValidationError):
            InstallationOperationFact(**{**fields, forbidden: "private"})  # pyright: ignore[reportArgumentType]
