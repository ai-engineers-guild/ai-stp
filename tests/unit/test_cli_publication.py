"""CLI publication transport: wire, retry and local confirmation seams.

The create/bind/confirm journeys live in `tests/api/cli/test_publication.py`
against the real `/v1` app; what remains here is what a mock legitimately
owns — dropped-answer retries, refusal mapping, contract-version rejection,
command declarations and the local explicit-decision gate.
"""

import json
import sqlite3
from types import SimpleNamespace

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
        "visibility": "private",
        "policy_version": "1",
        "actor_id": ACCOUNT,
        "device_id": DEVICE,
        "expires_at": "2026-08-14T00:00:00.000Z",
        "component_verified": False,
        "evidence": [],
        "effects": ["validate exact digest"],
    }


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
        artifact_inventory=[],
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
    from ai_stp_cli.application import publication as service

    monkeypatch.setattr(
        service,
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
        service.confirm({"plan-id": PLAN, "plan-hash": PLAN_HASH})
    assert raised.value.code == "AI_STP_USER_DECISION_REQUIRED"
    assert "--confirm" in raised.value.next_actions[0]


def test_confirm_binds_all_locally_stored_exact_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_stp_cli.application import publication as service

    held = session.Session(
        account_id=ACCOUNT,
        device_id=DEVICE,
        access_token="secret-token",
        refresh_token="refresh-token",
        expires_at="2099-01-01T00:00:00.000Z",
    )
    plan = PublicationPlanResponse.model_validate(_response())
    seen: list[bytes] = []
    seen_keys: list[str] = []
    projection_digest = "sha256:" + "a" * 64
    seen_projections: list[tuple[str, bytes]] = []

    def _open(_path: object) -> sqlite3.Connection:
        return sqlite3.connect(":memory:")

    def _status(*_args: object) -> PublicationPlanResponse:
        return plan

    def _get(*_args: object) -> bytes:
        return b"projection-bytes" if _args[-1] == projection_digest else b"exact-bytes"

    def _bind(*args: object, **_kwargs: object) -> PublicationPlanResponse:
        seen.append(args[-1] if isinstance(args[-1], bytes) else b"")
        return plan

    def _confirm(*_args: object, **_kwargs: object) -> PublicationPlanResponse:
        request = _args[-1]
        assert isinstance(request, PublicationConfirmRequest)
        seen_keys.append(request.idempotency_key)
        return plan.model_copy(update={"state": "validating"})

    def _bind_projection(*args: object, **_kwargs: object) -> PublicationPlanResponse:
        payload = args[-1]
        assert isinstance(payload, bytes)
        seen_projections.append((str(args[-2]), payload))
        return plan

    def _passport(*_args: object) -> SimpleNamespace:
        return SimpleNamespace(
            adaptations=[
                SimpleNamespace(
                    scope_adaptations=[
                        SimpleNamespace(
                            projection_artifact=SimpleNamespace(digest=projection_digest)
                        )
                    ]
                )
            ]
        )

    monkeypatch.setattr(service, "_session", lambda: held)
    monkeypatch.setattr(service, "endpoint", lambda: Endpoint(BASE))
    monkeypatch.setattr(service, "open_readonly", _open)
    monkeypatch.setattr("ai_stp_cli.local.component_passports.version_passport", _passport)
    monkeypatch.setattr("ai_stp_cli.application.publication.publication.status", _status)
    monkeypatch.setattr("ai_stp_cli.application.publication.content.get", _get)
    monkeypatch.setattr("ai_stp_cli.application.publication.publication.bind", _bind)
    monkeypatch.setattr(
        "ai_stp_cli.application.publication.publication.bind_projection",
        _bind_projection,
    )
    monkeypatch.setattr("ai_stp_cli.application.publication.publication.confirm", _confirm)

    result = service.confirm(
        {"plan-id": PLAN, "plan-hash": PLAN_HASH, "confirm": True, "idempotency-key": PLAN}
    ).payload

    assert result.state == "validating"
    assert seen == [b"exact-bytes"]
    assert seen_projections == [(projection_digest, b"projection-bytes")]
    assert seen_keys == [PLAN]


def test_confirm_reconciles_an_accepted_plan_without_another_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_stp_cli.application import publication as service

    held = session.Session(
        account_id=ACCOUNT,
        device_id=DEVICE,
        access_token="secret-token",
        refresh_token="refresh-token",
        expires_at="2099-01-01T00:00:00.000Z",
    )
    plan = PublicationPlanResponse.model_validate(_response("validating"))
    monkeypatch.setattr(service, "_session", lambda: held)
    monkeypatch.setattr(service, "endpoint", lambda: Endpoint(BASE))

    def status(*_args: object) -> PublicationPlanResponse:
        return plan

    monkeypatch.setattr(publication, "status", status)

    def duplicate_post(*_args: object, **_kwargs: object) -> PublicationPlanResponse:
        raise AssertionError("accepted publication must be reconciled through status")

    monkeypatch.setattr(publication, "confirm", duplicate_post)
    result = service.confirm({"plan-id": PLAN, "plan-hash": PLAN_HASH, "confirm": True}).payload
    assert result.state == "validating"
