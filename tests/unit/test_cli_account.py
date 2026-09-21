"""The `account` task intent: questions, spies, and refusal drains.

The login/logout journeys that drove the `#71` corpus mock moved to
`tests/api/cli/test_account_tasks.py`, where the task engine talks to the
real `/v1` auth surface. What remains stubs the application seams
(`begin`/`complete_once`/`logout`/`sync_now`) — question shape, idempotent
replays, and the decline path the API deliberately does not expose.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from ai_stp_cli.application import account as account_service
from ai_stp_cli.cloud import session
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.machine_help import AuthStatus, DeviceApproval
from ai_stp_foundation.ids import new_id


def test_account_asks_for_action_once() -> None:
    started = task_command.start(
        {"intent": "account", "idempotency-key": "account-ask-action-0001"}
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "blocked"
    assert continued.payload.questions[0].question_id == "action"
    assert continued.payload.questions[0].choices == ["login", "logout", "sync"]
    assert continued.continuations[0].actor == "human"
    assert continued.continuations[0].argv[:2] == ["task", "answer"]
    assert "--value" not in continued.continuations[0].argv


def test_account_asks_for_provider_once(tmp_path: Path) -> None:
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-ask-provider-0001",
            "input": _facts(tmp_path, {"action": "login"}),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    question = continued.payload.questions[0]
    assert question.question_id == "provider"
    assert question.choices == ["google", "github"]


def test_declined_login_fails_the_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(account_service, "begin", _approval)

    def complete_once() -> AuthStatus:
        raise CliFailure("AI_STP_AUTHORIZATION_DECLINED", "the sign-in was declined")

    monkeypatch.setattr(account_service, "complete_once", complete_once)
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-login-declined-0001",
            "input": _facts(tmp_path, {"action": "login", "provider": "google"}),
        }
    )
    assert started.payload.state == "blocked"
    with pytest.raises(CliFailure) as raised:
        task_command.continue_(
            {"task": started.payload.task_id, "revision": started.payload.revision}
        )
    assert raised.value.code == "AI_STP_AUTHORIZATION_DECLINED"
    status = task_command.status({"task": started.payload.task_id})
    assert status.payload.state == "failed"


def test_a_task_opened_after_auth_login_shows_the_pending_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`auth login` then a task start: the code must survive the handoff.

    Without the display fields on the pending record, the task could only say
    "approve at the verification URI" — the code the person must type was gone
    from every surface the task owns (#359).
    """
    store, _warning = open_store()
    session.save_pending(
        store,
        session.Pending(
            provider="google",
            device_code="the-device-code",
            interval=5,
            expires_in=600,
            user_code="WXYZ-1234",
            verification_uri="https://example.test/device",
        ),
    )

    def complete_once() -> AuthStatus:
        raise CliFailure("AI_STP_AUTHORIZATION_PENDING", "authorization pending")

    monkeypatch.setattr(account_service, "complete_once", complete_once)
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-login-pending-0001",
            "input": _facts(tmp_path, {"action": "login", "provider": "google"}),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    question = continued.payload.questions[0]
    assert question.question_id == "authorization"
    assert question.actor == "external"
    assert "WXYZ-1234" in question.prompt
    assert question.recommended == "WXYZ-1234"


def test_already_signed_in_login_skips_device_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    begun: list[str] = []

    def begin(provider: str) -> DeviceApproval:
        begun.append(provider)
        return _approval(provider)

    monkeypatch.setattr(account_service, "begin", begin)
    monkeypatch.setattr(account_service, "sync_now", _forbid_sync)
    _hold_session()
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-login-reuse-0001",
            "input": _facts(tmp_path, {"action": "login", "provider": "google"}),
        }
    )
    finished = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert finished.payload.state == "completed"
    outcome = finished.payload.outcome
    assert outcome is not None
    assert outcome.kind == "account"
    assert outcome.authenticated is True
    assert outcome.login_uploaded is False
    assert begun == []


def test_explicit_sync_is_not_implied_by_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(account_service, "begin", _approval)
    monkeypatch.setattr(account_service, "complete_once", _authenticated)
    monkeypatch.setattr(account_service, "sync_now", _forbid_sync)
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-login-no-sync-0001",
            "input": _facts(tmp_path, {"action": "login", "provider": "google"}),
        }
    )
    assert started.payload.state == "blocked"
    finished = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert finished.payload.outcome is not None
    assert finished.payload.outcome.kind == "account"
    assert finished.payload.outcome.synced is False


def test_explicit_sync_push_asks_for_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(account_service, "sync_now", _forbid_sync)
    _hold_session()
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-sync-root-0001",
            "input": _facts(tmp_path, {"action": "sync", "scope": "push"}),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.questions[0].question_id == "project-root"


def test_explicit_sync_calls_sync_now_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    def sync_now(*, scope: str, project_root: str) -> object:
        calls.append((scope, project_root))
        return object()

    monkeypatch.setattr(account_service, "sync_now", sync_now)
    _hold_session()
    root = str(tmp_path.resolve())
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-sync-push-0001",
            "input": _facts(tmp_path, {"action": "sync", "scope": "push", "project_root": root}),
        }
    )
    finished = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert finished.payload.state == "completed"
    outcome = finished.payload.outcome
    assert outcome is not None
    assert outcome.kind == "account"
    assert outcome.action == "sync"
    assert outcome.synced is True
    assert outcome.login_uploaded is False
    assert calls == [("push", root)]


def test_account_module_does_not_poll_or_spawn_nested_cli() -> None:
    source = Path(account_service.__file__).read_text(encoding="utf-8")
    assert "Popen" not in source
    assert "subprocess" not in source
    assert "login.poll" not in source
    assert '"wait"' not in source
    assert "open-browser" not in source


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


def _authenticated(*, state: str = "authenticated") -> AuthStatus:
    return AuthStatus(
        state=state,  # pyright: ignore[reportArgumentType]
        account_id=None if state != "authenticated" else new_id("account"),
        expires_at=None if state != "authenticated" else "2026-09-16T00:00:00.000Z",
        credential_store=None if state != "authenticated" else "file",
    )


def _forbid_sync(*, scope: str, project_root: str) -> object:
    raise AssertionError(f"login must not sync ({scope}, {project_root})")


def _hold_session() -> None:
    store, _warning = open_store()
    session.save(
        store,
        session.Session(
            account_id=new_id("account"),
            device_id=new_id("device"),
            access_token="a",
            refresh_token="r",
            expires_at=session.expiry(3600),
        ),
    )


def _facts(tmp_path: Path, body: Mapping[str, str]) -> str:
    place = tmp_path / "input.json"
    place.write_text(json.dumps(body), encoding="utf-8")
    return str(place)
