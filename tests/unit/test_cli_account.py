"""Account intent drains device-code login without uploading."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path

import httpx
import pytest

from ai_stp_cli.application import account as account_service
from ai_stp_cli.application import auth as auth_commands
from ai_stp_cli.cloud import login, session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.http import API_BASE_PATH
from ai_stp_contracts.machine_help import AuthStatus, DeviceApproval
from ai_stp_contracts.mock import MOCK_BASE_URL, build_transport
from ai_stp_foundation.ids import new_id

FIXTURE_DEVICE = "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
FIXTURE_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
FIXTURE_NAME = "fixture-device"
APPROVED_CODE = "FIXTUREdeviceCODE0123456789abcdefGHIJKLM"
FORBIDDEN_PATH_FRAGMENTS = ("/publications", "/sync-plans", "/revisions")


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


def test_login_blocks_external_then_one_exchange_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exchanges: list[int] = []
    monkeypatch.setattr(account_service, "begin", _approval)
    monkeypatch.setattr(account_service, "sync_now", _forbid_sync)

    def complete_once() -> AuthStatus:
        exchanges.append(1)
        if len(exchanges) == 1:
            raise CliFailure("AI_STP_AUTHORIZATION_PENDING", "not yet")
        return _authenticated()

    monkeypatch.setattr(account_service, "complete_once", complete_once)
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-login-exchange-0001",
            "input": _facts(tmp_path, {"action": "login", "provider": "google"}),
        }
    )
    assert started.payload.state == "blocked"
    question = started.payload.questions[0]
    assert question.question_id == "authorization"
    assert question.actor == "external"
    assert question.recommended == "ABCD-EFGH"
    assert started.continuations[0].actor == "external"
    assert started.continuations[0].argv[1] == "continue"
    replay = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-login-exchange-0001",
            "input": _facts(tmp_path, {"action": "login", "provider": "google"}),
        }
    )
    assert replay.payload.task_id == started.payload.task_id
    assert replay.payload.state == "blocked"
    assert replay.payload.questions[0].question_id == "authorization"
    assert replay.continuations[0].actor == "external"
    pending = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert pending.payload.state == "blocked"
    assert pending.payload.questions[0].actor == "external"
    assert exchanges == [1]
    finished = task_command.continue_(
        {"task": pending.payload.task_id, "revision": pending.payload.revision}
    )
    assert finished.payload.state == "completed"
    outcome = finished.payload.outcome
    assert outcome is not None
    assert outcome.kind == "account"
    assert outcome.action == "login"
    assert outcome.authenticated is True
    assert outcome.login_uploaded is False
    assert outcome.synced is False
    assert exchanges == [1, 1]


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


def test_logout_completes_without_questions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def logout() -> AuthStatus:
        return _authenticated(state="local_only")

    monkeypatch.setattr(account_service, "logout", logout)
    monkeypatch.setattr(account_service, "sync_now", _forbid_sync)
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-logout-0001",
            "input": _facts(tmp_path, {"action": "logout"}),
        }
    )
    finished = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert finished.payload.state == "completed"
    outcome = finished.payload.outcome
    assert outcome is not None
    assert outcome.kind == "account"
    assert outcome.action == "logout"
    assert outcome.authenticated is False
    assert outcome.login_uploaded is False


def test_login_http_is_auth_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    recording = _RecordingTransport(build_transport())
    monkeypatch.setattr(
        auth_commands,
        "endpoint",
        lambda: Endpoint(MOCK_BASE_URL, transport=recording),
    )
    monkeypatch.setattr(login, "device_display_name", lambda: FIXTURE_NAME)
    _adopt_fixture_device(monkeypatch)
    from ai_stp_cli.commands import passport

    passport.developer_init({})
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-login-http-0001",
            "input": _facts(tmp_path, {"action": "login", "provider": "google"}),
        }
    )
    assert started.payload.questions[0].actor == "external"
    store, _warning = open_store()
    pending = session.load_pending(store)
    assert pending is not None
    session.save_pending(store, dataclasses.replace(pending, device_code=APPROVED_CODE))
    finished = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert finished.payload.state == "completed"
    outcome = finished.payload.outcome
    assert outcome is not None
    assert outcome.kind == "account"
    assert outcome.login_uploaded is False
    paths = [path for _method, path in recording.calls]
    assert paths
    assert all(path.startswith(f"{API_BASE_PATH}/auth/") for path in paths)
    joined = " ".join(paths)
    for fragment in FORBIDDEN_PATH_FRAGMENTS:
        assert fragment not in joined
    assert "PUT" not in {method for method, _path in recording.calls}


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


def _adopt_fixture_device(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_stp_cli import identity, paths
    from ai_stp_cli import secrets as secrets_module

    current, _warning = identity.load_or_create()
    store = secrets_module.FileStore()
    minted = store.get(identity.key_entry(current.device_id))
    assert minted is not None
    store.put(identity.key_entry(FIXTURE_DEVICE), minted)
    paths.write_private(
        paths.device_file(),
        f'{{"device_id": "{FIXTURE_DEVICE}", "created_at": "{current.created_at}", '
        '"state": "active", "retired": []}',
    )
    monkeypatch.setattr(login, "local_identity", lambda: (FIXTURE_DEVICE, FIXTURE_KEY, None))


class _RecordingTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner
        self.calls: list[tuple[str, str]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method.upper(), request.url.path))
        return self._inner.handle_request(request)


def _facts(tmp_path: Path, body: Mapping[str, str]) -> str:
    place = tmp_path / "input.json"
    place.write_text(json.dumps(body), encoding="utf-8")
    return str(place)
