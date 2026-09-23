"""The CI dashboard receives only a closed summary of a local verification."""

import json
from collections.abc import Mapping

import httpx
import pytest

import ai_stp_cli.application.managed_verify as managed_verify
import ai_stp_cli.commands.corporate as command
from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import corporate as cloud_corporate
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.cloud.session import Session
from ai_stp_contracts.dashboard import CorporateCiCheckRequest
from ai_stp_contracts.machine_help import ManagedVerification, ManagedVerificationItem

ORGANIZATION = "organization_01J0000000000000000000000B"
ACCOUNT = "account_01J0000000000000000000000C"
DEVICE = "device_01J0000000000000000000000D"
PROJECT = "remote_project_01J0000000000000000000000E"
SETUP = "setup_01J0000000000000000000000A"
ENDPOINT = Endpoint(base_url="http://corporate.test")


def _verification(
    *, account_id: str = ACCOUNT, remote_project_id: str = PROJECT
) -> ManagedVerification:
    return ManagedVerification(
        status="fail",
        project_id="project_local",
        harness_id="claude-code",
        organization_id=ORGANIZATION,
        account_id=account_id,
        remote_project_id=remote_project_id,
        checked_at="2026-09-23T01:00:00.000Z",
        corporate="evaluated",
        diagnostics=["secret=never-send-this or C:/private/source.py"],
        items=[
            ManagedVerificationItem(
                subject="setup", stable_id=SETUP, classification="locally_modified"
            ),
            ManagedVerificationItem(
                subject="path",
                path="private/source.py",
                classification="locally_modified",
            ),
        ],
    )


def test_verify_reports_closed_ci_summary_without_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Session(ACCOUNT, DEVICE, "secret-token", "refresh-token", "2099-01-01T00:00:00Z")

    def held_session(_purpose: str) -> Session:
        return session

    monkeypatch.setattr(command, "_session", held_session)
    monkeypatch.setattr(command, "endpoint", lambda: ENDPOINT)

    def fake_verify(
        _parameters: Mapping[str, object],
        *,
        endpoint_url: Endpoint,
        access_token: str,
        account_id: str,
    ) -> Answer[ManagedVerification]:
        return Answer(_verification())

    monkeypatch.setattr(managed_verify, "verify_managed", fake_verify)
    sent: list[CorporateCiCheckRequest] = []

    def report(
        _endpoint: Endpoint, _token: str, _organization: str, request: CorporateCiCheckRequest
    ) -> None:
        sent.append(request)

    monkeypatch.setattr(cloud_corporate, "report_ci_check", report)
    answer = command.verify({"project": PROJECT})
    assert answer.payload.status == "fail"
    assert len(sent) == 1
    assert sent[0].model_dump() == {
        "schema_version": 1,
        "project_id": PROJECT,
        "account_id": ACCOUNT,
        "device_id": DEVICE,
        "harness": "claude-code",
        "setup_id": SETUP,
        "status": "fail",
        "reason": "target_drift",
        "checked_at": "2026-09-23T01:00:00.000Z",
    }


def test_ci_report_transport_uses_the_closed_request() -> None:
    request = CorporateCiCheckRequest(
        project_id=PROJECT,
        account_id=ACCOUNT,
        device_id=DEVICE,
        harness="claude-code",
        setup_id=SETUP,
        status="pass",
        checked_at="2026-09-23T01:00:00.000Z",
    )

    def route(inbound: httpx.Request) -> httpx.Response:
        assert inbound.method == "PUT"
        assert inbound.url.path == (
            f"/v1/corporate/organizations/{ORGANIZATION}/dashboard/ci-check"
        )
        assert inbound.headers["Authorization"] == "Bearer secret-token"
        body = json.loads(inbound.content)
        assert body == request.model_dump(mode="json")
        return httpx.Response(
            200,
            json={
                **body,
                "organization_id": ORGANIZATION,
                "received_at": "2026-09-23T01:00:01.000Z",
                "revision": 1,
            },
        )

    endpoint = Endpoint(
        "https://corporate.test", max_attempts=1, transport=httpx.MockTransport(route)
    )
    response = cloud_corporate.report_ci_check(endpoint, "secret-token", ORGANIZATION, request)
    assert response.status == "pass"


@pytest.mark.parametrize(
    ("parameters", "verified_account_id", "remote_project_id", "warns"),
    [
        ({"offline": True}, ACCOUNT, PROJECT, False),
        ({}, ACCOUNT, "", True),
        ({}, "account_01J0000000000000000000000F", PROJECT, True),
    ],
)
def test_verify_skips_unreportable_context(
    monkeypatch: pytest.MonkeyPatch,
    parameters: Mapping[str, object],
    verified_account_id: str,
    remote_project_id: str,
    warns: bool,
) -> None:
    session = Session(ACCOUNT, DEVICE, "secret-token", "refresh-token", "2099-01-01T00:00:00Z")

    def held_session(_purpose: str) -> Session:
        return session

    monkeypatch.setattr(command, "_session", held_session)
    monkeypatch.setattr(command, "endpoint", lambda: ENDPOINT)

    def fake_verify(
        _parameters: Mapping[str, object],
        *,
        endpoint_url: Endpoint,
        access_token: str,
        account_id: str,
    ) -> Answer[ManagedVerification]:
        return Answer(
            _verification(account_id=verified_account_id, remote_project_id=remote_project_id)
        )

    monkeypatch.setattr(managed_verify, "verify_managed", fake_verify)

    def unexpected(*_args: object) -> None:
        raise AssertionError("CI report must not be sent")

    monkeypatch.setattr(cloud_corporate, "report_ci_check", unexpected)
    answer = command.verify(parameters)
    assert bool(answer.warnings) is warns
