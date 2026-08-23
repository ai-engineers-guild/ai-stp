"""CLI publication transport preserves exact plans, auth and recovery."""

import json
import sqlite3

import httpx
import pytest

from ai_stp_cli.cloud import publication, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.publication import (
    PublicationConfirmRequest,
    PublicationPlanCreateRequest,
    PublicationPlanResponse,
)

BASE = "https://platform.example"
DEVICE = "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
ACCOUNT = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
STABLE = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DIGEST = "sha256:" + "b" * 64
PLAN = "plan_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
PLAN_HASH = "plan_" + "c" * 64


def _response(state: str = "ready") -> dict[str, object]:
    return {
        "schema_version": 1,
        "plan_id": PLAN,
        "plan_hash": PLAN_HASH,
        "state": state,
        "object_kind": "component",
        "stable_id": STABLE,
        "version": "1.0",
        "content_digest": DIGEST,
        "policy_version": "1",
        "actor_id": ACCOUNT,
        "device_id": DEVICE,
        "expires_at": "2026-08-14T00:00:00.000Z",
        "component_verified": False,
        "evidence": [],
        "effects": ["validate exact digest"],
    }


def test_plan_status_and_confirm_use_the_authenticated_contract_paths() -> None:
    seen: list[tuple[str, str, str | None, dict[str, object] | None]] = []

    def route(request: httpx.Request) -> httpx.Response:
        body = None if not request.content else json.loads(request.content)
        seen.append((request.method, request.url.path, request.headers.get("Authorization"), body))
        state = "validating" if request.url.path.endswith("/confirm") else "ready"
        return httpx.Response(201 if request.method == "POST" else 200, json=_response(state))

    endpoint = Endpoint(BASE, transport=httpx.MockTransport(route))
    create = PublicationPlanCreateRequest(
        object_kind="component",
        stable_id=STABLE,
        version="1.0",
        content_digest=DIGEST,
        passport={"schema_version": 1},
        attestations=[],
        idempotency_key="create-key-012345",
        device_id=DEVICE,
    )
    planned = publication.create(endpoint, "secret-token", create)
    shown = publication.status(endpoint, "secret-token", planned.plan_id)
    confirmed = publication.confirm(
        endpoint,
        "secret-token",
        planned.plan_id,
        PublicationConfirmRequest(
            plan_hash=planned.plan_hash,
            confirmed=True,
            idempotency_key="confirm-key-012345",
        ),
    )

    assert shown.plan_hash == planned.plan_hash
    assert confirmed.state == "validating"
    assert [item[:2] for item in seen] == [
        ("POST", "/v1/publications/plans"),
        ("GET", f"/v1/publications/plans/{PLAN}"),
        ("POST", f"/v1/publications/plans/{PLAN}/confirm"),
    ]
    assert all(item[2] == "Bearer secret-token" for item in seen)
    assert seen[0][3] is not None and seen[0][3]["content_digest"] == DIGEST
    assert seen[2][3] is not None and seen[2][3]["plan_hash"] == PLAN_HASH


def test_bind_puts_exact_artifact_bytes_on_the_plan() -> None:
    seen: list[tuple[str, str, str | None, bytes]] = []
    payload = b"exact-first-party-bytes"

    def route(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                request.method,
                request.url.path,
                request.headers.get("Authorization"),
                request.content,
            )
        )
        assert request.headers.get("Content-Type") == "application/octet-stream"
        return httpx.Response(200, json=_response("ready"))

    bound = publication.bind(
        Endpoint(BASE, transport=httpx.MockTransport(route)),
        "secret-token",
        PLAN,
        payload,
        pause=lambda _seconds: None,
    )

    assert bound.plan_id == PLAN
    assert seen == [
        ("PUT", f"/v1/publications/plans/{PLAN}/artifact", "Bearer secret-token", payload)
    ]


def test_bind_retries_the_same_bytes_when_the_first_answer_is_lost() -> None:
    seen: list[bytes] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        if len(seen) == 1:
            raise httpx.ConnectError("lost response", request=request)
        return httpx.Response(200, json=_response("ready"))

    payload = b"same-bytes"
    result = publication.bind(
        Endpoint(BASE, transport=httpx.MockTransport(flaky)),
        "secret-token",
        PLAN,
        payload,
        pause=lambda _seconds: None,
    )

    assert result.plan_id == PLAN
    assert seen == [payload, payload]


def test_bind_does_not_retry_a_validation_refusal() -> None:
    seen = 0

    def refused(request: httpx.Request) -> httpx.Response:
        nonlocal seen
        seen += 1
        return httpx.Response(
            400,
            json={
                "schema_version": 1,
                "error": {
                    "code": "AI_STP_VALIDATION_ERROR",
                    "message": "artifact digest or size does not match the plan",
                    "retryable": False,
                },
            },
        )

    with pytest.raises(CliFailure) as raised:
        publication.bind(
            Endpoint(BASE, transport=httpx.MockTransport(refused)),
            "secret-token",
            PLAN,
            b"other-bytes",
            pause=lambda _seconds: None,
        )
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert seen == 1


def test_bind_refuses_a_newer_contract_major() -> None:
    def newer(_request: httpx.Request) -> httpx.Response:
        body = _response("ready")
        body["schema_version"] = 2
        return httpx.Response(200, json=body)

    with pytest.raises(CliFailure) as raised:
        publication.bind(
            Endpoint(BASE, transport=httpx.MockTransport(newer)),
            "secret-token",
            PLAN,
            b"exact-bytes",
            pause=lambda _seconds: None,
        )
    assert raised.value.code == "AI_STP_SCHEMA_UNSUPPORTED"


def test_publication_commands_are_declared_with_exact_confirmation() -> None:
    from ai_stp_cli.registry import COMMANDS

    by_name = {command.name: command for command in COMMANDS}
    plan = by_name["publication plan"]
    status = by_name["publication status"]
    confirm = by_name["publication confirm"]

    assert plan.descriptor.mutability == "plan"
    assert status.descriptor.mutability == "read"
    assert confirm.descriptor.confirmation == "explicit_flag"
    assert confirm.descriptor.result_schema is not None
    assert confirm.descriptor.result_schema.endswith("cli-publication-plan")


def test_create_keeps_one_idempotency_key_when_the_first_answer_is_lost() -> None:
    seen: list[str] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["idempotency_key"])
        if len(seen) == 1:
            raise httpx.ConnectError("lost response", request=request)
        return httpx.Response(201, json=_response())

    request = PublicationPlanCreateRequest(
        object_kind="component",
        stable_id=STABLE,
        version="1.0",
        content_digest=DIGEST,
        passport={"schema_version": 1},
        attestations=[],
        idempotency_key="one-intent-012345",
        device_id=DEVICE,
    )
    result = publication.create(
        Endpoint(BASE, transport=httpx.MockTransport(flaky)), "secret-token", request
    )

    assert result.plan_id == PLAN
    assert seen == ["one-intent-012345", "one-intent-012345"]


def test_confirm_requires_the_exact_explicit_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_stp_cli.commands import publication as command

    monkeypatch.setattr(
        command,
        "_session",
        lambda: session.Session(
            account_id=ACCOUNT,
            device_id=DEVICE,
            access_token="secret-token",
            refresh_token="refresh-token",
            expires_at="2099-01-01T00:00:00.000Z",
        ),
    )
    with pytest.raises(CliFailure) as raised:
        command.confirm({"plan-id": PLAN, "plan-hash": PLAN_HASH})
    assert raised.value.code == "AI_STP_USER_DECISION_REQUIRED"
    assert "--confirm" in raised.value.next_actions[0]


def test_confirm_binds_the_locally_stored_exact_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_stp_cli.commands import publication as command

    held = session.Session(
        account_id=ACCOUNT,
        device_id=DEVICE,
        access_token="secret-token",
        refresh_token="refresh-token",
        expires_at="2099-01-01T00:00:00.000Z",
    )
    plan = PublicationPlanResponse.model_validate(_response())
    seen: list[bytes] = []

    def _open(_path: object) -> sqlite3.Connection:
        return sqlite3.connect(":memory:")

    def _status(*_args: object) -> PublicationPlanResponse:
        return plan

    def _get(*_args: object) -> bytes:
        return b"exact-bytes"

    def _bind(*args: object, **_kwargs: object) -> PublicationPlanResponse:
        seen.append(args[-1] if isinstance(args[-1], bytes) else b"")
        return plan

    def _confirm(*_args: object, **_kwargs: object) -> PublicationPlanResponse:
        return plan.model_copy(update={"state": "validating"})

    monkeypatch.setattr(command, "_session", lambda: held)
    monkeypatch.setattr(command, "endpoint", lambda: Endpoint(BASE))
    monkeypatch.setattr(command, "open_readonly", _open)
    monkeypatch.setattr("ai_stp_cli.commands.publication.publication.status", _status)
    monkeypatch.setattr("ai_stp_cli.commands.publication.content.get", _get)
    monkeypatch.setattr("ai_stp_cli.commands.publication.publication.bind", _bind)
    monkeypatch.setattr("ai_stp_cli.commands.publication.publication.confirm", _confirm)

    result = command.confirm({"plan-id": PLAN, "plan-hash": PLAN_HASH, "confirm": True}).payload

    assert result.state == "validating"
    assert seen == [b"exact-bytes"]
