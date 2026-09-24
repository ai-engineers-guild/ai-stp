"""The `account` task intent drained against the real `/v1` auth surface.

`tests/unit/test_cli_account.py` keeps the question-shape and spy cases;
these are the journeys that used to stub `begin`/`complete_once`/`logout`
outright — the task engine now drives the deployed device flow, so a blocked
task's recommended user code is approved through the same endpoint a browser
session calls.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path

import httpx
import pytest
from tests.api.cli.conftest import WebApprover
from tests.support.asgi_sync import SyncAsgiServer

from ai_stp_cli.application import auth as auth_commands
from ai_stp_cli.application import sync as sync_commands
from ai_stp_cli.cloud import session
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.commands import config_show
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.http import API_BASE_PATH
from ai_stp_contracts.machine_help import SyncPullView

FORBIDDEN_PATH_FRAGMENTS = ("/publications", "/sync-plans", "/revisions")

#: `web_approver` is a factory fixture; this alias keeps the annotation honest.
ApproverFactory = Callable[[], WebApprover]


def _facts(tmp_path: Path, body: Mapping[str, str]) -> str:
    place = tmp_path / "input.json"
    place.write_text(json.dumps(body), encoding="utf-8")
    return str(place)


def _sign_in(cli_endpoint: Endpoint, approver: WebApprover) -> None:
    """A complete device sign-in through the application layer.

    `auth.complete` is what persists the session and pending-record changes;
    raw `login.exchange` returns tokens without storing them.
    """
    approval = auth_commands.begin({"provider": "github"}).payload
    assert approver.approve(approval.user_code).status_code == 200
    finished = auth_commands.complete({}).payload
    assert finished.state == "authenticated"


def test_login_blocks_external_then_one_exchange_completes(
    cli_endpoint: Endpoint,
    web_approver: ApproverFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_commands, "endpoint", lambda: cli_endpoint)
    approver = web_approver()
    facts = _facts(tmp_path, {"action": "login", "provider": "github"})

    started = task_command.start(
        {"intent": "account", "idempotency-key": "account-real-login-0001", "input": facts}
    )
    assert started.payload.state == "blocked"
    question = started.payload.questions[0]
    assert question.question_id == "authorization"
    assert question.actor == "external"
    user_code = question.recommended
    assert user_code
    assert started.continuations[0].actor == "external"
    assert started.continuations[0].argv[1] == "continue"

    replay = task_command.start(
        {"intent": "account", "idempotency-key": "account-real-login-0001", "input": facts}
    )
    assert replay.payload.task_id == started.payload.task_id
    assert replay.payload.state == "blocked"

    pending = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert pending.payload.state == "blocked"
    assert pending.payload.questions[0].actor == "external"

    assert approver.approve(user_code).status_code == 200

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

    store, _warning = open_store()
    held = session.load(store)
    assert held is not None
    assert held.account_id == approver.account_id


def test_login_http_is_auth_only(
    cli_server: SyncAsgiServer,
    web_approver: ApproverFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert cli_server.transport is not None
    recording = _RecordingTransport(cli_server.transport)
    monkeypatch.setattr(
        auth_commands,
        "endpoint",
        lambda: Endpoint("http://127.0.0.1", transport=recording),
    )
    approver = web_approver()

    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-real-http-0001",
            "input": _facts(tmp_path, {"action": "login", "provider": "github"}),
        }
    )
    user_code = started.payload.questions[0].recommended
    assert user_code
    # The approval goes through the browser-side client, not the recorded one.
    assert approver.approve(user_code).status_code == 200
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


def test_logout_completes_without_questions(
    cli_endpoint: Endpoint,
    web_approver: ApproverFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_commands, "endpoint", lambda: cli_endpoint)
    _sign_in(cli_endpoint, web_approver())

    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-real-logout-0001",
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

    store, _warning = open_store()
    assert session.load(store) is None


def test_explicit_account_pull_drains_the_real_sync_endpoint(
    cli_endpoint: Endpoint,
    web_approver: ApproverFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_commands, "endpoint", lambda: cli_endpoint)
    monkeypatch.setattr(sync_commands, "endpoint", lambda: cli_endpoint)
    _sign_in(cli_endpoint, web_approver())
    config_show.set_({"set": ("sync.enabled=true",)})
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-real-sync-pull-01",
            "input": _facts(tmp_path, {"action": "sync", "scope": "pull"}),
        }
    )
    assert started.payload.state == "completed"
    assert started.payload.goal_satisfied
    outcome = started.payload.outcome
    assert outcome is not None and outcome.kind == "account"
    assert outcome.synced
    assert isinstance(outcome.sync_result, SyncPullView)
    assert outcome.sync_result.state == "up_to_date"
    assert outcome.sync_result.pending_version_count == 0


class _RecordingTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner
        self.calls: list[tuple[str, str]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method.upper(), request.url.path))
        return self._inner.handle_request(request)
