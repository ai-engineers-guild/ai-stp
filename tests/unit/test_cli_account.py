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
from ai_stp_cli.cloud import sync as cloud_sync
from ai_stp_cli.commands import config_show
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.http import PageInfo
from ai_stp_contracts.machine_help import AuthStatus, DeviceApproval, SyncPullView, SyncPushView
from ai_stp_contracts.sync import SyncPullResponse
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


def test_a_pending_record_without_a_code_restarts_the_flow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record written before the display fields were kept cannot be approved:
    the code the person must type is not in it. The task drops the husk and
    starts an authorization that can actually complete."""
    store, _warning = open_store()
    session.save_pending(
        store,
        session.Pending(provider="google", device_code="old", interval=5, expires_in=600),
    )
    begun: list[str] = []

    def begin(provider: str) -> DeviceApproval:
        begun.append(provider)
        session.save_pending(
            store,
            session.Pending(
                provider=provider,
                device_code="new",
                interval=5,
                expires_in=600,
                user_code="ABCD-EFGH",
                verification_uri="https://example.test/device",
            ),
        )
        return _approval(provider)

    def complete_once() -> AuthStatus:
        raise CliFailure("AI_STP_AUTHORIZATION_PENDING", "authorization pending")

    monkeypatch.setattr(account_service, "begin", begin)
    monkeypatch.setattr(account_service, "complete_once", complete_once)
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-login-codeless-0001",
            "input": _facts(tmp_path, {"action": "login", "provider": "google"}),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    # The husk was dropped and a completable authorization began instead of
    # the task trying to complete a code nobody was ever shown.
    assert begun == ["google"]
    question = continued.payload.questions[0]
    assert question.question_id == "authorization"
    assert "ABCD-EFGH" in question.prompt
    pending = session.load_pending(store)
    assert pending is not None and pending.device_code == "new"


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

    def sync_now(*, scope: str, project_root: str) -> SyncPushView:
        calls.append((scope, project_root))
        return SyncPushView(
            stable_id=new_id("project"),
            processed_events=1,
            local_revision_id="local-revision",
            event_id="event-00000001",
            remote_revision_id="local-revision",
            state="accepted",
            server_head_revision_id="local-revision",
            conflicting_entity_id=None,
        )

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


def test_explicit_pull_reaches_the_sync_transport_without_a_second_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hold_session()
    config_show.set_({"set": ("sync.enabled=true",)})
    calls: list[object] = []

    def pull(*args: object) -> SyncPullResponse:
        calls.append(args[-1])
        return SyncPullResponse(items=[], page=PageInfo(next_cursor=None, page_size=20))

    monkeypatch.setattr(cloud_sync, "pull", pull)
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-real-pull-0001",
            "input": _facts(tmp_path, {"action": "sync", "scope": "pull"}),
        }
    )
    assert started.payload.goal_satisfied
    assert len(calls) == 1
    outcome = started.payload.outcome
    assert outcome is not None and outcome.kind == "account"
    assert outcome.model_dump()["sync_result"]["state"] == "up_to_date"


@pytest.mark.parametrize("state", ["accepted", "rejected", "conflict", "superseded"])
def test_account_push_preserves_the_receipt_and_only_acceptance_satisfies_the_goal(
    state: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hold_session()
    receipt = SyncPushView.model_validate(
        {
            "stable_id": new_id("project"),
            "processed_events": 1,
            "local_revision_id": "local-revision",
            "event_id": "event-00000001",
            "remote_revision_id": "remote-revision",
            "state": state,
            "server_head_revision_id": "remote-revision",
            "conflict_fields": ["/facts/name"] if state == "conflict" else [],
            "conflicting_entity_id": None,
        }
    )

    def sync_now(**_kwargs: object) -> SyncPushView:
        return receipt

    monkeypatch.setattr(account_service, "sync_now", sync_now)
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-push-receipt-0001",
            "input": _facts(
                tmp_path,
                {"action": "sync", "scope": "push", "project_root": str(tmp_path)},
            ),
        }
    )
    outcome = started.payload.outcome
    assert outcome is not None and outcome.kind == "account"
    assert outcome.synced is (state == "accepted")
    assert started.payload.goal_satisfied is (state == "accepted")
    assert outcome.model_dump()["sync_result"] == receipt.model_dump()


@pytest.mark.parametrize("terminal", ["up_to_date", "partial", "repeated-cursor"])
@pytest.mark.parametrize("first_state", ["pulling", "partial"])
def test_account_pull_exposes_progress_and_stops_on_empty_or_unchanged_pages(
    terminal: str, first_state: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _hold_session()
    first = SyncPullView.model_validate(
        {
            "received": 1,
            "applied": 1,
            "replayed": 0,
            "state": first_state,
            "next_cursor": "cursor-1",
        }
    )
    last = (
        first
        if terminal == "repeated-cursor"
        else SyncPullView.model_validate(
            {
                "received": 0,
                "applied": 0,
                "replayed": 0,
                "state": terminal,
                "next_cursor": "cursor-1",
                "pending_version_count": 1 if terminal == "partial" else 0,
                "pending_versions": [
                    {
                        "stable_id": new_id("setup"),
                        "version": "1.0",
                        "passport_digest": "sha256:" + "a" * 64,
                        "revision_id": "missing-revision",
                        "event_id": "legacy-event",
                    }
                ]
                if terminal == "partial"
                else [],
            }
        )
    )
    calls: list[object] = []

    def sync_now(**_kwargs: object) -> SyncPullView:
        calls.append(None)
        return first if len(calls) == 1 else last

    monkeypatch.setattr(account_service, "sync_now", sync_now)
    started = task_command.start(
        {
            "intent": "account",
            "idempotency-key": "account-pull-pages-0001",
            "input": _facts(tmp_path, {"action": "sync", "scope": "pull"}),
        }
    )
    assert started.payload.state == "planned"
    assert not started.payload.goal_satisfied
    assert started.continuations[0].actor == "cli"
    assert started.continuations[0].argv[1] == "continue"
    finished = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert finished.payload.state == "completed"
    assert finished.payload.goal_satisfied is (terminal == "up_to_date")
    assert not finished.continuations
    outcome = finished.payload.outcome
    assert outcome is not None and outcome.kind == "account"
    assert outcome.synced is (terminal == "up_to_date")
    assert outcome.model_dump()["sync_result"] == last.model_dump()
    replay = task_command.continue_(
        {"task": finished.payload.task_id, "revision": finished.payload.revision}
    )
    assert replay.payload == finished.payload
    assert len(calls) == 2


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
