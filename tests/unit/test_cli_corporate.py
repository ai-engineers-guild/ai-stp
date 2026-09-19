"""The CLI reads the same effective-assignment contract the API serves."""

import httpx

from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.cloud.corporate import effective_assignment
from ai_stp_contracts.corporate import CorporateEffectiveAssignmentQuery
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
