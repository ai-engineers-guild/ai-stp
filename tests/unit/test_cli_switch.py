"""Switch restores last user working config and never kills the caller."""

from __future__ import annotations

import json
from contextlib import closing
from hashlib import sha256
from pathlib import Path

import pytest

from ai_stp_cli.application import switch as switch_service
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation, preserved_setups
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.provider.status import BackupObservation, NativeSnapshotObservation
from ai_stp_contracts.machine_help import InstallationView
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import new_id


def test_switch_asks_for_harness_once() -> None:
    started = task_command.start({"intent": "switch", "idempotency-key": "switch-ask-harness-0001"})
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "blocked"
    assert continued.payload.questions[0].question_id == "harness-id"
    assert continued.continuations[0].actor == "human"
    assert continued.continuations[0].argv[:2] == ["task", "answer"]
    assert "--value" not in continued.continuations[0].argv


def test_switch_asks_for_absolute_project_root(tmp_path: Path) -> None:
    started = task_command.start(
        {
            "intent": "switch",
            "idempotency-key": "switch-ask-project-0001",
            "input": _facts(tmp_path, {"harness_id": "cursor"}),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.questions[0].question_id == "project-root"
    assert "Not a harness config directory" in continued.payload.questions[0].prompt


def test_switch_reasks_when_project_root_is_inside_harness_config(tmp_path: Path) -> None:
    from ai_stp_cli.local import harnesses

    detector = next(item for item in harnesses.DETECTORS if item.harness_id == "antigravity")
    nested = harnesses.config_root(detector) / "antigravity-cli"
    started = task_command.start(
        {
            "intent": "switch",
            "idempotency-key": "switch-reject-config-root-01",
            "input": _facts(tmp_path, {"harness_id": "antigravity", "project_root": str(nested)}),
        }
    )
    assert started.payload.state == "blocked"
    assert started.payload.questions[0].question_id == "project-root"
    assert "harness config" in started.payload.questions[0].why


def test_switch_refuses_when_no_preserved_user_setup(tmp_path: Path) -> None:
    with pytest.raises(CliFailure) as raised:
        task_command.start(
            {
                "intent": "switch",
                "idempotency-key": "switch-missing-snapshot-0001",
                "input": _facts(
                    tmp_path,
                    {"harness_id": "cursor", "project_root": str(tmp_path.resolve())},
                ),
            }
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"
    assert "preserved user setup" in raised.value.message
    assert "baseline" not in raised.value.message
    assert "catalog" not in raised.value.message.lower()
    assert raised.value.details.get("state") == "failed"
    status = task_command.status({"task": raised.value.details["task"]})
    assert status.payload.state == "failed"


def test_latest_for_returns_the_newest_user_snapshot(tmp_path: Path) -> None:
    target_id = f"{new_id('project')}:cursor"
    older = _register(tmp_path, target_id=target_id, at="2026-09-01T00:00:00.000Z", payload=b"old")
    newer = _register(tmp_path, target_id=target_id, at="2026-09-02T00:00:00.000Z", payload=b"new")
    with closing(open_registry(configured_path(), create=True)) as connection:
        latest = preserved_setups.latest_for(connection, target_id)
    assert latest is not None
    assert latest.stable_id == newer.stable_id
    assert latest.stable_id != older.stable_id


def test_switch_restores_then_asks_reload_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = _saved()
    leftover_id = new_id("setup")
    restore_calls: list[str] = []

    def resolve_saved(
        *,
        harness_id: str,
        project_root: str,
        preserved_setup_id: str | None,
    ) -> preserved_setups.PreservedSetup:
        return saved

    def capture_drift(_saved: preserved_setups.PreservedSetup) -> str:
        return leftover_id

    monkeypatch.setattr(switch_service, "resolve_saved", resolve_saved)
    monkeypatch.setattr(switch_service, "capture_drift", capture_drift)

    def restore(_saved: preserved_setups.PreservedSetup) -> InstallationView:
        restore_calls.append(_saved.stable_id)
        return _installation(new_id("operation"), "verified")

    monkeypatch.setattr(switch_service, "restore", restore)
    started = task_command.start(
        {
            "intent": "switch",
            "idempotency-key": "switch-reload-session-0001",
            "input": _facts(
                tmp_path,
                {"harness_id": "cursor", "project_root": str(tmp_path.resolve())},
            ),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "blocked"
    assert continued.payload.goal_satisfied is False
    question = continued.payload.questions[0]
    assert question.question_id == "reload-session"
    assert question.actor == "human"
    assert continued.continuations[0].actor == "human"
    assert continued.continuations[0].argv[:2] == ["task", "answer"]
    assert "--value" not in continued.continuations[0].argv
    assert restore_calls == [saved.stable_id]
    replay = task_command.start(
        {
            "intent": "switch",
            "idempotency-key": "switch-reload-session-0001",
            "input": _facts(
                tmp_path,
                {"harness_id": "cursor", "project_root": str(tmp_path.resolve())},
            ),
        }
    )
    assert replay.payload.task_id == started.payload.task_id
    assert replay.payload.state == "blocked"
    assert replay.payload.questions[0].question_id == "reload-session"
    assert replay.continuations[0].actor == "human"
    assert replay.continuations[0].argv[:2] == ["task", "answer"]
    assert restore_calls == [saved.stable_id]
    with pytest.raises(CliFailure) as raised:
        task_command.start(
            {
                "intent": "switch",
                "idempotency-key": "switch-reload-session-0001",
                "input": _facts(
                    tmp_path,
                    {"harness_id": "cursor", "project_root": str(tmp_path / "other")},
                ),
            }
        )
    assert raised.value.code == "AI_STP_CONFLICT"
    assert "different input" in raised.value.message
    answered = task_command.answer(
        {
            "task": continued.payload.task_id,
            "revision": continued.payload.revision,
            "question-id": "reload-session",
            "value": "done",
        }
    )
    assert answered.payload.state == "completed"
    outcome = answered.payload.outcome
    assert outcome is not None
    assert outcome.kind == "switch"
    assert outcome.preserved_setup_id == saved.stable_id
    assert outcome.drift_preserved_setup_id == leftover_id
    assert outcome.process_killed is False
    assert outcome.session_loaded is False
    assert restore_calls == [saved.stable_id]
    assert not answered.continuations


def test_switch_skips_reload_question_when_already_answered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = _saved()

    def resolve_saved(
        *,
        harness_id: str,
        project_root: str,
        preserved_setup_id: str | None,
    ) -> preserved_setups.PreservedSetup:
        return saved

    def capture_drift(_saved: preserved_setups.PreservedSetup) -> str:
        return new_id("setup")

    def restore(_saved: preserved_setups.PreservedSetup) -> InstallationView:
        return _installation(new_id("operation"), "verified")

    monkeypatch.setattr(switch_service, "resolve_saved", resolve_saved)
    monkeypatch.setattr(switch_service, "capture_drift", capture_drift)
    monkeypatch.setattr(switch_service, "restore", restore)
    started = task_command.start(
        {
            "intent": "switch",
            "idempotency-key": "switch-reload-already-0001",
            "input": _facts(
                tmp_path,
                {
                    "harness_id": "cursor",
                    "project_root": str(tmp_path.resolve()),
                    "reload_session": "done",
                },
            ),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "completed"
    outcome = continued.payload.outcome
    assert outcome is not None
    assert outcome.kind == "switch"
    assert outcome.session_loaded is False


def test_switch_maps_compensated_restore_to_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def resolve_saved(
        *,
        harness_id: str,
        project_root: str,
        preserved_setup_id: str | None,
    ) -> preserved_setups.PreservedSetup:
        return _saved()

    def capture_drift(_saved: preserved_setups.PreservedSetup) -> str:
        return new_id("setup")

    monkeypatch.setattr(switch_service, "resolve_saved", resolve_saved)
    monkeypatch.setattr(switch_service, "capture_drift", capture_drift)

    def restore(_saved: preserved_setups.PreservedSetup) -> InstallationView:
        raise CliFailure("AI_STP_COMPENSATED", "the restore rolled back")

    monkeypatch.setattr(switch_service, "restore", restore)
    with pytest.raises(CliFailure) as raised:
        task_command.start(
            {
                "intent": "switch",
                "idempotency-key": "switch-compensated-0001",
                "input": _facts(
                    tmp_path,
                    {"harness_id": "cursor", "project_root": str(tmp_path.resolve())},
                ),
            }
        )
    assert raised.value.code == "AI_STP_COMPENSATED"
    assert raised.value.details.get("state") == "failed"
    status = task_command.status({"task": raised.value.details["task"]})
    assert status.payload.state == "failed"


def test_switch_module_does_not_kill_or_spawn_nested_cli() -> None:
    source = Path(switch_service.__file__).read_text(encoding="utf-8")
    assert "Popen" not in source
    assert "subprocess" not in source
    assert "os.kill" not in source
    assert "SIGKILL" not in source
    assert "SIGTERM" not in source
    assert "killpg" not in source
    assert "recommend_setup" not in source
    assert "first_party" not in source


def _saved() -> preserved_setups.PreservedSetup:
    return preserved_setups.PreservedSetup(
        stable_id=new_id("setup"),
        operation_id=new_id("operation"),
        target_id=f"{new_id('project')}:cursor",
        provider_target="/tmp/native-target",
        target_scope="global",
        provider_id="cursor",
        backup_ref="slot-000000000001",
        snapshot_digest="sha256:" + "a" * 64,
        roots=("skills",),
        excluded=(),
        created_at="2026-09-01T00:00:00.000Z",
    )


def _register(
    tmp_path: Path, *, target_id: str, at: str, payload: bytes
) -> preserved_setups.PreservedSetup:
    identity = "sha256:" + sha256(payload).hexdigest()
    with closing(open_registry(configured_path(), create=True)) as connection:
        plan = installation.propose(
            connection,
            action="backup",
            author=new_id("account"),
            target_id=target_id,
            expected_target_digest=identity,
            provider_version="1.0.0",
            effects=("preserve the complete native setup",),
            recovery_action="restore the captured setup",
            idempotency_key=new_id("operation"),
            at=at,
            expires_at="2099-01-01T00:00:00.000Z",
            provider_target=str(tmp_path),
        )
    snapshot = NativeSnapshotObservation(
        identity, plan.operation_id, ("skills",), (), "verified", "matches"
    )
    artifact: dict[str, JsonValue] = {
        "native_capture": {
            "roots": ["skills"],
            "excluded": [],
            "current_digest": identity,
            "restore_digest": None,
        }
    }
    observed = BackupObservation("slot-000000000001", True, "preserved native setup", snapshot)
    with closing(open_registry(configured_path(), create=True)) as connection:
        return preserved_setups.register(
            connection,
            plan=plan,
            artifact=artifact,
            observed=observed,
            provider_id="cursor",
            at=at,
        )


def _installation(operation_id: str, state: str) -> InstallationView:
    digest = "sha256:" + "b" * 64
    return InstallationView.model_validate(
        {
            "operation_id": operation_id,
            "action": "rollback",
            "state": state,
            "plan_digest": digest,
            "target_id": "project:cursor",
            "expected_target_digest": digest,
            "expires_at": "2026-09-16T00:00:00.000Z",
        }
    )


def _facts(tmp_path: Path, body: dict[str, str]) -> str:
    place = tmp_path / "input.json"
    place.write_text(json.dumps(body), encoding="utf-8")
    return str(place)
