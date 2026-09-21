"""The CLI reads the same effective-assignment contract the API serves."""

import httpx
import pytest

from ai_stp_cli.cloud import corporate, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.cloud.corporate import (
    assignment_distribution,
    assignment_plan,
    distribute_assignment,
    effective_assignment,
)
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.corporate import (
    CorporateAssignmentPlan,
    CorporateAssignmentPlanRequest,
    CorporateDistributionRequest,
    CorporateDistributionResult,
    CorporateDistributionStateList,
    CorporateDistributionStateQuery,
    CorporateEffectiveAssignment,
    CorporateEffectiveAssignmentQuery,
    CorporatePlanMaterializedItem,
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


def test_distribute_assignment_posts_the_shared_contract() -> None:
    organization_id = new_id("organization")
    source_id = new_id("operation")
    seen: dict[str, str] = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        seen["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "distribution_id": "catalog-distribution-0001",
                "organization_id": organization_id,
                "source_assignment_id": source_id,
                "action": "assign",
                "dry_run": False,
                "source_revision": 3,
                "targets": [
                    {
                        "target_kind": "employee",
                        "target_id": new_id("account"),
                        "result": "applied",
                        "state": "pending",
                    }
                ],
                "exclusions": [],
                "counts": {
                    "applied": 1,
                    "skipped": 0,
                    "conflicted": 0,
                    "denied": 0,
                    "failed": 0,
                },
            },
        )

    endpoint = Endpoint(base_url=MOCK_BASE_URL, transport=httpx.MockTransport(answer))
    result = distribute_assignment(
        endpoint,
        "token",
        organization_id,
        CorporateDistributionRequest(
            source_assignment_id=source_id,
            action="assign",
            dry_run=False,
            expected_revision=3,
            authorization_revision=1,
            idempotency_key="catalog-distribution-0001",
        ),
    )
    assert seen["method"] == "POST"
    assert seen["path"].endswith("/catalog-assignments/distribution")
    assert '"expected_revision":3' in seen["body"]
    assert result.distribution_id == "catalog-distribution-0001"
    assert result.counts.applied == 1
    assert result.targets[0].state == "pending"


def test_assignment_distribution_reads_the_shared_contract() -> None:
    organization_id = new_id("organization")
    source_id = new_id("operation")
    seen: dict[str, str] = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["query"] = str(request.url.query)
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "organization_id": organization_id,
                "source_assignment_id": source_id,
                "source_revision": 2,
                "source_state": "current",
                "items": [
                    {
                        "target_kind": "project",
                        "target_id": new_id("remote_project"),
                        "result": "applied",
                        "state": "outdated",
                        "operation_revision": 1,
                    }
                ],
                "total": 1,
            },
        )

    endpoint = Endpoint(base_url=MOCK_BASE_URL, transport=httpx.MockTransport(answer))
    result = assignment_distribution(
        endpoint,
        "token",
        organization_id,
        CorporateDistributionStateQuery(source_assignment_id=source_id, limit=10),
    )
    assert seen["path"].endswith("/catalog-assignments/distribution")
    assert "limit=10" in seen["query"]
    assert result.source_revision == 2
    assert result.items[0].state == "outdated"


def test_distribute_command_requires_confirmation_without_dry_run() -> None:
    from ai_stp_cli.commands import corporate as command
    from ai_stp_cli.errors import CliFailure

    with pytest.raises(CliFailure, match="explicit confirmation"):
        command.distribute(
            {
                "organization": new_id("organization"),
                "source": new_id("operation"),
                "action": "assign",
                "expected-revision": "1",
                "authorization-revision": "1",
                "idempotency-key": "catalog-distribution-0002",
            }
        )


def test_distribute_command_passes_the_typed_request_to_the_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.commands import corporate as command

    account_id = new_id("account")
    organization_id = new_id("organization")
    source_id = new_id("operation")
    seen: dict[str, object] = {}

    def authenticated(_purpose: str) -> session.Session:
        return session.Session(
            account_id=account_id,
            device_id=new_id("device"),
            access_token="bearer",
            refresh_token="refresh",
            expires_at="2099-01-01T00:00:00.000Z",
        )

    def distributed(
        _endpoint: Endpoint,
        _token: str,
        organization: str,
        request: CorporateDistributionRequest,
    ) -> CorporateDistributionResult:
        seen["organization"] = organization
        seen["request"] = request
        return CorporateDistributionResult.model_validate(
            {
                "schema_version": 1,
                "distribution_id": request.idempotency_key,
                "organization_id": organization,
                "source_assignment_id": request.source_assignment_id,
                "action": request.action,
                "dry_run": request.dry_run,
                "source_revision": request.expected_revision,
                "targets": [],
                "exclusions": [],
                "counts": {},
            }
        )

    monkeypatch.setattr(command, "_session", authenticated)
    monkeypatch.setattr(corporate, "distribute_assignment", distributed)

    result = command.distribute(
        {
            "organization": organization_id,
            "source": source_id,
            "action": "revoke",
            "confirm": True,
            "expected-revision": "2",
            "authorization-revision": "1",
            "idempotency-key": "catalog-distribution-0003",
        }
    )

    assert seen["organization"] == organization_id
    request = seen["request"]
    assert isinstance(request, CorporateDistributionRequest)
    assert request.source_assignment_id == source_id
    assert request.action == "revoke"
    assert request.dry_run is False
    assert request.expected_revision == 2
    assert result.payload.action == "revoke"


def test_distribution_command_passes_the_typed_query_to_the_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.commands import corporate as command

    account_id = new_id("account")
    organization_id = new_id("organization")
    source_id = new_id("operation")
    seen: dict[str, object] = {}

    def authenticated(_purpose: str) -> session.Session:
        return session.Session(
            account_id=account_id,
            device_id=new_id("device"),
            access_token="bearer",
            refresh_token="refresh",
            expires_at="2099-01-01T00:00:00.000Z",
        )

    def listed(
        _endpoint: Endpoint,
        _token: str,
        organization: str,
        request: CorporateDistributionStateQuery,
    ) -> CorporateDistributionStateList:
        seen["organization"] = organization
        seen["request"] = request
        return CorporateDistributionStateList.model_validate(
            {
                "schema_version": 1,
                "organization_id": organization,
                "source_assignment_id": request.source_assignment_id,
                "source_revision": 1,
                "source_state": "current",
                "items": [],
                "total": 0,
            }
        )

    monkeypatch.setattr(command, "_session", authenticated)
    monkeypatch.setattr(corporate, "assignment_distribution", listed)

    result = command.distribution(
        {
            "organization": organization_id,
            "source": source_id,
            "offset": "5",
            "limit": "25",
        }
    )

    assert seen["organization"] == organization_id
    request = seen["request"]
    assert isinstance(request, CorporateDistributionStateQuery)
    assert request.source_assignment_id == source_id
    assert request.offset == 5
    assert request.limit == 25
    assert result.payload.total == 0


def test_plan_command_defaults_account_and_reports_materialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.commands import corporate as command

    account_id = new_id("account")
    organization_id = new_id("organization")
    setup_id = new_id("setup")
    seen: dict[str, object] = {}

    def authenticated(_purpose: str) -> session.Session:
        return session.Session(
            account_id=account_id,
            device_id=new_id("device"),
            access_token="bearer",
            refresh_token="refresh",
            expires_at="2099-01-01T00:00:00.000Z",
        )

    def planned(
        _endpoint: Endpoint,
        _token: str,
        organization: str,
        request: CorporateAssignmentPlanRequest,
    ) -> CorporateAssignmentPlan:
        seen["organization"] = organization
        seen["request"] = request
        return CorporateAssignmentPlan.model_validate(
            {
                "schema_version": 1,
                "organization_id": organization,
                "account_id": request.account_id,
                "harness": request.harness,
                "items": [],
                "total": 0,
            }
        )

    monkeypatch.setattr(command, "_session", authenticated)
    monkeypatch.setattr(corporate, "assignment_plan", planned)

    result = command.plan(
        {
            "organization": organization_id,
            "harness": "claude-code",
            "materialized": (f"setup:{setup_id}@1.0",),
        }
    )

    assert seen["organization"] == organization_id
    request = seen["request"]
    assert isinstance(request, CorporateAssignmentPlanRequest)
    assert request.account_id == account_id
    assert request.harness == "claude-code"
    assert request.materialized[0].object_kind == "setup"
    assert request.materialized[0].stable_id == setup_id
    assert request.materialized[0].version == "1.0"
    assert result.payload.total == 0


def test_plan_command_rejects_a_malformed_materialized_coordinate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.commands import corporate as command

    def authenticated(_purpose: str) -> session.Session:
        return session.Session(
            account_id=new_id("account"),
            device_id=new_id("device"),
            access_token="bearer",
            refresh_token="refresh",
            expires_at="2099-01-01T00:00:00.000Z",
        )

    monkeypatch.setattr(command, "_session", authenticated)

    with pytest.raises(CliFailure, match="materialized coordinate"):
        command.plan(
            {
                "organization": new_id("organization"),
                "harness": "claude-code",
                "materialized": ("setup@1.0",),
            }
        )


def test_assignment_plan_round_trips_the_shared_contract() -> None:
    account_id = new_id("account")
    setup_id = new_id("setup")
    seen: dict[str, str] = {}

    def answer(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "schema_version": 1,
                "organization_id": new_id("organization"),
                "account_id": account_id,
                "harness": "claude-code",
                "items": [
                    {
                        "object_kind": "setup",
                        "stable_id": setup_id,
                        "state": "assigned",
                        "outcome": "missing",
                        "action": "install",
                        "assignment_id": new_id("operation"),
                        "source_scope": "organization",
                        "source_subject_id": new_id("organization"),
                        "selector": "exact",
                        "version": "1.0",
                        "passport_digest": "sha256:" + "b" * 64,
                    }
                ],
                "total": 1,
            },
        )

    endpoint = Endpoint(base_url=MOCK_BASE_URL, transport=httpx.MockTransport(answer))
    result = assignment_plan(
        endpoint,
        "token",
        new_id("organization"),
        CorporateAssignmentPlanRequest(
            account_id=account_id,
            harness="claude-code",
            materialized=[
                CorporatePlanMaterializedItem(
                    object_kind="setup", stable_id=setup_id, version="1.0"
                )
            ],
        ),
    )
    assert seen["path"].endswith("/catalog-assignments/plan")
    assert '"stable_id":"' + setup_id in seen["body"]
    item = result.items[0]
    assert item.outcome == "missing"
    assert item.action == "install"
    assert item.version == "1.0"
