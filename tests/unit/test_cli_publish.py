"""Publish intent drains the no-binding publication plan. Receipt is not readable."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from ai_stp_cli.application import account as account_service
from ai_stp_cli.application import publish as publish_service
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.machine_help import AuthStatus, DeviceApproval, PublicationPlanView
from ai_stp_foundation.ids import new_id

STABLE = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
PLAN = "plan_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
PLAN_HASH = "plan_" + "c" * 64
ACCOUNT = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DEVICE = "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DIGEST = "sha256:" + "b" * 64


def test_publish_asks_for_object_id_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(account_service, "ensure_session", _signed_in)
    started = task_command.start({"intent": "publish", "idempotency-key": "publish-ask-id-0001"})
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.questions[0].question_id == "object-id"


def test_publish_defaults_private_and_omits_source_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    planned: list[Mapping[str, object]] = []
    monkeypatch.setattr(account_service, "ensure_session", _signed_in)

    def plan_publication(parameters: Mapping[str, object]) -> PublicationPlanView:
        planned.append(dict(parameters))
        return _plan("validating")

    def confirm_publication(*, plan_id: str, plan_hash: str) -> PublicationPlanView:
        return _plan("validating", plan_id=plan_id, plan_hash=plan_hash)

    monkeypatch.setattr(publish_service, "plan_publication", plan_publication)
    monkeypatch.setattr(publish_service, "confirm_publication", confirm_publication)
    started = task_command.start(
        {
            "intent": "publish",
            "idempotency-key": "publish-private-0001",
            "input": _facts(tmp_path, {"object_id": STABLE, "object_version": "1.0"}),
        }
    )
    finished = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert finished.payload.state == "completed"
    assert finished.payload.goal_satisfied is False
    outcome = finished.payload.outcome
    assert outcome is not None
    assert outcome.kind == "publish"
    assert outcome.visibility == "private"
    assert outcome.source_binding_id == ""
    assert outcome.readable is False
    assert outcome.provenance == "filesystem"
    assert outcome.state == "validating"
    assert planned == [{"id": STABLE, "version": "1.0", "visibility": "private"}]
    assert "source-binding-id" not in planned[0]
    assert "git" not in json.dumps(planned[0])


def test_published_state_is_readable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(account_service, "ensure_session", _signed_in)

    def plan_ready(_parameters: Mapping[str, object]) -> PublicationPlanView:
        return _plan("ready")

    def confirm_published(*, plan_id: str, plan_hash: str) -> PublicationPlanView:
        return _plan("published", plan_id=plan_id, plan_hash=plan_hash)

    monkeypatch.setattr(publish_service, "plan_publication", plan_ready)
    monkeypatch.setattr(publish_service, "confirm_publication", confirm_published)
    started = task_command.start(
        {
            "intent": "publish",
            "idempotency-key": "publish-readable-0001",
            "input": _facts(tmp_path, {"object_id": STABLE, "object_version": "1.0"}),
        }
    )
    finished = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert finished.payload.goal_satisfied is True
    outcome = finished.payload.outcome
    assert outcome is not None
    assert outcome.kind == "publish"
    assert outcome.readable is True
    assert outcome.state == "published"


def test_auth_required_publish_shows_one_user_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(account_service, "begin", _approval)
    started = task_command.start(
        {
            "intent": "publish",
            "idempotency-key": "publish-auth-0001",
            "input": _facts(
                tmp_path,
                {"object_id": STABLE, "object_version": "1.0", "provider": "google"},
            ),
        }
    )
    assert started.payload.state == "blocked"
    question = started.payload.questions[0]
    assert question.question_id == "authorization"
    assert question.actor == "external"
    assert question.recommended == "ABCD-EFGH"
    assert started.continuations[0].argv.count("continue") == 1


def test_publish_refuses_a_bound_git_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(account_service, "ensure_session", _signed_in)
    bound = _plan("ready")

    def plan_bound(_parameters: Mapping[str, object]) -> PublicationPlanView:
        return bound.model_copy(update={"source_binding_id": PLAN})

    monkeypatch.setattr(publish_service, "plan_publication", plan_bound)
    with pytest.raises(CliFailure) as raised:
        task_command.start(
            {
                "intent": "publish",
                "idempotency-key": "publish-git-refused-0001",
                "input": _facts(tmp_path, {"object_id": STABLE, "object_version": "1.0"}),
            }
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert "filesystem" in raised.value.message


def test_publish_module_does_not_spawn_nested_cli_or_invent_git() -> None:
    source = Path(publish_service.__file__).read_text(encoding="utf-8")
    assert "Popen" not in source
    assert "subprocess" not in source
    assert "source-binding-id" not in source
    assert "github.com" not in source


def _signed_in(_facts: object) -> AuthStatus:
    return AuthStatus(
        state="authenticated",
        account_id=ACCOUNT,
        expires_at="2026-09-16T00:00:00.000Z",
        credential_store="file",
    )


def _plan(state: str, *, plan_id: str = PLAN, plan_hash: str = PLAN_HASH) -> PublicationPlanView:
    return PublicationPlanView.model_validate(
        {
            "schema_version": 1,
            "plan_id": plan_id,
            "plan_hash": plan_hash,
            "state": state,
            "object_kind": "component",
            "stable_id": STABLE,
            "version": "1.0",
            "content_digest": DIGEST,
            "visibility": "private",
            "policy_version": "1",
            "actor_id": ACCOUNT,
            "device_id": DEVICE,
            "expires_at": "2026-09-16T00:00:00.000Z",
            "component_verified": False,
            "evidence": [],
            "effects": ["validate exact digest"],
        }
    )


def _approval(_provider: str = "google") -> DeviceApproval:
    return DeviceApproval(
        provider="google",
        user_code="ABCD-EFGH",
        verification_uri="https://example.test/device",
        verification_uri_complete="https://example.test/device?code=ABCD-EFGH",
        expires_in=600,
        browser_opened=False,
        device_id=new_id("device"),
    )


def _facts(tmp_path: Path, body: Mapping[str, str]) -> str:
    place = tmp_path / "input.json"
    place.write_text(json.dumps(body), encoding="utf-8")
    return str(place)
