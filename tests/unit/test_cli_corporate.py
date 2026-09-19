"""The CLI reads the same effective-assignment contract the API serves."""

import httpx
import pytest

from ai_stp_cli.cloud import corporate, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.cloud.corporate import effective_assignment
from ai_stp_contracts.corporate import (
    CorporateEffectiveAssignment,
    CorporateEffectiveAssignmentQuery,
)
from ai_stp_contracts.mock import MOCK_BASE_URL
from ai_stp_foundation.ids import new_id


def test_effective_assignment_round_trips_the_shared_contract() -> None:
    account_id = new_id("account")
    stable_id = new_id("setup")
    seen: dict[str, str] = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.query)
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "organization_id": new_id("organization"),
                "account_id": account_id,
                "object_kind": "setup",
                "stable_id": stable_id,
                "state": "assigned",
                "assignment_id": new_id("operation"),
                "source_scope": "team",
                "source_subject_id": new_id("operation"),
                "selector": "latest",
                "version": "2.0",
                "passport_digest": "sha256:" + "a" * 64,
                "harness": None,
                "candidates": [],
            },
        )

    endpoint = Endpoint(base_url=MOCK_BASE_URL, transport=httpx.MockTransport(answer))
    result = effective_assignment(
        endpoint,
        "token",
        new_id("organization"),
        CorporateEffectiveAssignmentQuery(
            account_id=account_id,
            object_kind="setup",
            stable_id=stable_id,
            harness="codex",
        ),
    )
    assert seen["path"].endswith("/catalog-assignments/effective")
    assert "harness=codex" in seen["query"]
    assert "project_id" not in seen["query"]
    assert result.state == "assigned"
    assert result.selector == "latest"
    assert result.version == "2.0"
    assert result.passport_digest == "sha256:" + "a" * 64


def test_effective_command_passes_the_typed_query_to_the_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.commands import corporate as command

    account_id = new_id("account")
    organization_id = new_id("organization")
    stable_id = new_id("setup")
    project_id = new_id("remote_project")
    technology_id = new_id("technology")
    seen: dict[str, object] = {}

    def authenticated(_purpose: str) -> session.Session:
        return session.Session(
            account_id=account_id,
            device_id=new_id("device"),
            access_token="bearer",
            refresh_token="refresh",
            expires_at="2099-01-01T00:00:00.000Z",
        )

    def resolved(
        _endpoint: Endpoint,
        _token: str,
        organization: str,
        request: CorporateEffectiveAssignmentQuery,
    ) -> CorporateEffectiveAssignment:
        seen["organization"] = organization
        seen["request"] = request
        return CorporateEffectiveAssignment.model_validate(
            {
                "schema_version": 1,
                "organization_id": organization,
                "account_id": request.account_id,
                "object_kind": request.object_kind,
                "stable_id": request.stable_id,
                "state": "assigned",
                "assignment_id": new_id("operation"),
                "source_scope": "project",
                "source_subject_id": request.project_id,
                "selector": "latest",
                "version": "2.0",
                "passport_digest": "sha256:" + "b" * 64,
                "harness": request.harness,
                "candidates": [],
            }
        )

    monkeypatch.setattr(command, "_session", authenticated)
    monkeypatch.setattr(corporate, "effective_assignment", resolved)

    result = command.effective(
        {
            "organization": organization_id,
            "account": account_id,
            "kind": "setup",
            "id": stable_id,
            "project": project_id,
            "technology": technology_id,
            "harness": "codex",
        }
    )

    assert seen["organization"] == organization_id
    request = seen["request"]
    assert isinstance(request, CorporateEffectiveAssignmentQuery)
    assert request.account_id == account_id
    assert request.object_kind == "setup"
    assert request.stable_id == stable_id
    assert request.project_id == project_id
    assert request.technology_id == technology_id
    assert request.harness == "codex"
    assert result.payload.source_scope == "project"
    assert result.payload.version == "2.0"
