"""Install intent drains acquire/plan/approve/apply without a catalog quiz."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli import identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.app import main as cli_main
from ai_stp_cli.application import author as author_service
from ai_stp_cli.application import catalog as catalog_service
from ai_stp_cli.application import install as install_service
from ai_stp_cli.application import install_task as install_task_service
from ai_stp_cli.application.install_task import SetupPin
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import passports, setup_author
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.machine_help import InstallationView
from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_foundation.ids import new_id


def test_install_asks_for_harness_once() -> None:
    started = task_command.start(
        {"intent": "install", "idempotency-key": "install-ask-harness-0001"}
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "blocked"
    assert continued.payload.questions[0].question_id == "harness-id"
    assert continued.continuations[0].actor == "human"
    assert continued.continuations[0].arguments["question-id"] == "harness-id"
    assert continued.continuations[0].missing == ["value"]
    assert continued.continuations[0].argv[:2] == ["task", "answer"]
    assert "--question-id" in continued.continuations[0].argv
    assert "--value" not in continued.continuations[0].argv


def test_install_picks_first_party_baseline_without_a_catalog_quiz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin = install_task_service.recommend_setup("cursor")
    assert pin is not None
    assert pin.why == "First-party baseline setup for cursor."
    acquired: list[tuple[str, str]] = []
    _stub_lifecycle(monkeypatch, acquired)
    started = task_command.start(
        {
            "intent": "install",
            "idempotency-key": "install-pick-baseline-0001",
            "input": _facts(
                tmp_path,
                {
                    "harness_id": "cursor",
                    "project_root": str(tmp_path.resolve()),
                },
            ),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.questions == []
    assert continued.payload.state == "completed"
    assert continued.payload.outcome is not None
    assert continued.payload.outcome.kind == "install"
    assert continued.payload.outcome.setup_id == pin.setup_id
    assert continued.payload.outcome.setup_version == pin.setup_version
    assert acquired == [(pin.setup_id, pin.setup_version)]


def test_install_asks_for_setup_pin_when_no_recommendation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(install_task_service, "recommend_setup", _no_recommendation)
    started = task_command.start(
        {
            "intent": "install",
            "idempotency-key": "install-ask-setup-0001",
            "input": _facts(tmp_path, {"harness_id": "cursor"}),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.questions[0].question_id == "setup-ref"
    assert continued.payload.questions[0].choices == []


@pytest.mark.parametrize("intent", ["install", "change"])
@pytest.mark.parametrize("field", ["setup_id", "setup_version"])
def test_partial_setup_pin_never_falls_back_to_baseline(
    tmp_path: Path, intent: str, field: str
) -> None:
    facts = {"harness_id": "antigravity", field: new_id("setup") if field == "setup_id" else "1.0"}
    started = task_command.start(
        {
            "intent": intent,
            "idempotency-key": "partial-setup-pin-01",
            "input": _facts(tmp_path, facts),
        }
    )
    assert started.payload.state == "blocked"
    assert started.payload.questions[0].question_id == "setup-ref"
    assert not started.payload.child_operation_ids


def test_install_an_owned_authored_pin_without_public_catalog_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = tmp_path / "local-skill"
    tree.mkdir()
    (tree / "SKILL.md").write_text("# Local skill\n", encoding="utf-8")
    authored = author_service.persist(
        directory=tree,
        harness_id="antigravity",
        component_type="skill",
        name="local-skill",
        license_spdx="MIT",
    )

    def no_catalog(_parameters: Mapping[str, object]) -> None:
        raise AssertionError("an owned local setup is not a public catalog object")

    monkeypatch.setattr(catalog_service, "acquire", no_catalog)
    operation = new_id("operation")
    digest = "sha256:" + "a" * 64
    planned: list[Mapping[str, object]] = []

    def plan(parameters: Mapping[str, object]) -> Answer[InstallationView]:
        planned.append(parameters)
        return Answer(_installation(operation, "planned", digest))

    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(install_service, "approve", _answer(operation, "approved", digest))
    monkeypatch.setattr(install_service, "apply", _answer(operation, "verified", digest))
    started = task_command.start(
        {
            "intent": "install",
            "idempotency-key": "install-owned-authored-01",
            "input": _facts(
                tmp_path,
                {
                    "harness_id": "antigravity",
                    "setup_id": authored.setup_id,
                    "setup_version": authored.setup_version,
                    "project_root": str(tmp_path),
                },
            ),
        }
    )
    assert started.payload.goal_satisfied
    assert len(planned) == 1
    assert planned[0]["setup"] == f"{authored.setup_id}@{authored.setup_version}"


@pytest.mark.parametrize("case", ["foreign-owner", "missing-version"])
def test_local_pin_shortcut_requires_current_ownership_and_exact_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    tree = tmp_path / "local-skill"
    tree.mkdir()
    (tree / "SKILL.md").write_text("# Local skill\n", encoding="utf-8")
    current, _warning = identity.load_or_create()
    publisher = new_id("account") if case == "foreign-owner" else passports.owner().account_id
    with closing(open_registry(configured_path(), create=True)) as connection:
        authored = setup_author.record(
            connection,
            directory=tree,
            harness_id="antigravity",
            component_type="skill",
            name="local-skill",
            license_spdx="MIT",
            publisher_id=publisher,
            device_id=current.device_id,
            at=passports.moment(),
        )
    requested_version = "2.0" if case == "missing-version" else authored.setup_version
    calls: list[Mapping[str, object]] = []

    def acquire(parameters: Mapping[str, object]) -> None:
        calls.append(parameters)

    monkeypatch.setattr(catalog_service, "acquire", acquire)
    install_task_service.acquire_pin(authored.setup_id, requested_version)
    assert calls == [{"id": authored.setup_id, "version": requested_version}]


def test_every_harness_has_one_baseline_pin() -> None:
    for harness_id in HARNESS_IDS:
        pin = install_task_service.recommend_setup(harness_id)
        assert pin is not None, harness_id
        assert pin.setup_id.startswith("setup_")
        assert pin.why == f"First-party baseline setup for {harness_id}."


def test_install_asks_for_absolute_project_root(tmp_path: Path) -> None:
    started = task_command.start(
        {
            "intent": "install",
            "idempotency-key": "install-ask-project-0001",
            "input": _facts(
                tmp_path,
                {
                    "harness_id": "cursor",
                    "setup_id": new_id("setup"),
                    "setup_version": "1.0",
                },
            ),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    question = continued.payload.questions[0]
    assert question.question_id == "project-root"
    cwd = Path.cwd()
    if (cwd / ".git").is_dir():
        assert question.recommended == str(cwd)
        assert question.choices == [str(cwd)]


def test_install_drains_acquire_plan_approve_apply_without_returning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    operation_id = new_id("operation")
    digest = "sha256:" + "a" * 64
    calls: list[str] = []
    acquired: list[tuple[str, str]] = []
    setup_id = new_id("setup")

    monkeypatch.setattr(install_task_service, "acquire_pin", _capture_acquire(acquired))

    def plan(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        calls.append("plan")
        return Answer(_installation(operation_id, "planned", digest))

    def approve(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        calls.append("approve")
        return Answer(_installation(operation_id, "approved", digest))

    def apply(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        calls.append("apply")
        return Answer(_installation(operation_id, "verified", digest))

    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(install_service, "approve", approve)
    monkeypatch.setattr(install_service, "apply", apply)

    started = task_command.start(
        {
            "intent": "install",
            "idempotency-key": "install-drain-in-process-01",
            "input": _facts(
                tmp_path,
                {
                    "harness_id": "cursor",
                    "setup_id": setup_id,
                    "setup_version": "1.4",
                    "project_root": str(tmp_path.resolve()),
                },
            ),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert acquired == [(setup_id, "1.4")]
    assert calls == ["plan", "approve", "apply"]
    assert continued.payload.state == "completed"
    assert continued.payload.goal_satisfied is True
    assert continued.payload.outcome is not None
    assert continued.payload.outcome.kind == "install"
    assert continued.payload.outcome.verified is True
    assert continued.payload.child_operation_ids == [operation_id]
    assert continued.continuations == ()


def test_install_apply_failure_is_not_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    operation_id = new_id("operation")
    digest = "sha256:" + "a" * 64
    monkeypatch.setattr(install_task_service, "acquire_pin", _skip_acquire)
    monkeypatch.setattr(install_service, "plan", _answer(operation_id, "planned", digest))
    monkeypatch.setattr(install_service, "approve", _answer(operation_id, "approved", digest))

    def apply(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        raise CliFailure(
            "AI_STP_COMPENSATED",
            "the requested install did not complete; compensation finished",
            operation_id=operation_id,
        )

    monkeypatch.setattr(install_service, "apply", apply)

    with pytest.raises(CliFailure) as raised:
        task_command.start(
            {
                "intent": "install",
                "idempotency-key": "install-compensated-0001",
                "input": _facts(
                    tmp_path,
                    {
                        "harness_id": "cursor",
                        "setup_id": new_id("setup"),
                        "setup_version": "1.4",
                        "project_root": str(tmp_path.resolve()),
                    },
                ),
            }
        )
    assert raised.value.code == "AI_STP_COMPENSATED"
    status = task_command.status({"task": raised.value.details["task"]})
    assert status.payload.state == "failed"
    assert status.payload.goal_satisfied is False


def test_isolated_home_install_loop_uses_emitted_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    pin = install_task_service.recommend_setup("cursor")
    assert pin is not None
    _stub_lifecycle(monkeypatch, [])
    project = tmp_path / "project"
    project.mkdir()
    facts = tmp_path / "input.json"
    facts.write_text(
        json.dumps(
            {
                "harness_id": "cursor",
                "project_root": str(project.resolve()),
            }
        ),
        encoding="utf-8",
    )
    code = cli_main(
        [
            "task",
            "start",
            "--intent",
            "install",
            "--idempotency-key",
            "install-isolated-home-01",
            "--input",
            str(facts),
            "--json",
        ]
    )
    body = json.loads(capsys.readouterr().out)
    assert code == 0
    assert body["ok"] is True
    while body["continuations"]:
        argv = list(body["continuations"][0]["argv"])
        code = cli_main(argv)
        body = json.loads(capsys.readouterr().out)
        assert code == 0
        assert body["ok"] is True
    assert body["data"]["state"] == "completed"
    assert body["data"]["outcome"]["kind"] == "install"
    assert body["data"]["outcome"]["setup_id"] == pin.setup_id
    assert body["data"]["outcome"]["verified"] is True


def test_partial_apply_is_recover_not_retry_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    operation_id = new_id("operation")
    digest = "sha256:" + "c" * 64
    planned = 0
    applied = 0

    def plan(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        nonlocal planned
        planned += 1
        return Answer(_installation(operation_id, "planned", digest))

    def apply(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        nonlocal applied
        applied += 1
        raise CliFailure(
            "AI_STP_PARTIAL_OPERATION",
            "the requested install did not complete and needs recovery",
            operation_id=operation_id,
            continuations=[],
        )

    monkeypatch.setattr(install_task_service, "acquire_pin", _skip_acquire)
    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(install_service, "approve", _answer(operation_id, "approved", digest))
    monkeypatch.setattr(install_service, "apply", apply)
    with pytest.raises(CliFailure) as raised:
        task_command.start(
            {
                "intent": "install",
                "idempotency-key": "install-partial-recover-0001",
                "input": _facts(
                    tmp_path,
                    {
                        "harness_id": "cursor",
                        "setup_id": new_id("setup"),
                        "setup_version": "1.4",
                        "project_root": str(tmp_path.resolve()),
                    },
                ),
            }
        )
    assert raised.value.code == "AI_STP_PARTIAL_OPERATION"
    status = task_command.status({"task": raised.value.details["task"]})
    assert status.payload.state == "failed"
    assert status.payload.goal_satisfied is False
    assert status.payload.child_operation_ids == [operation_id]
    with pytest.raises(CliFailure) as again:
        task_command.continue_(
            {"task": status.payload.task_id, "revision": status.payload.revision}
        )
    assert again.value.code == "AI_STP_CONFLICT"
    assert planned == 1
    assert applied == 1


def test_kill_after_plan_resumes_the_held_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    operation_id = new_id("operation")
    digest = "sha256:" + "d" * 64
    planned = 0
    applied = 0
    resumed = 0

    def plan(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        nonlocal planned
        planned += 1
        return Answer(_installation(operation_id, "planned", digest))

    def apply(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        nonlocal applied
        applied += 1
        if applied == 1:
            raise RuntimeError("killed after apply")
        raise AssertionError("apply must not run again")

    def resume(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        nonlocal resumed
        resumed += 1
        return Answer(_installation(operation_id, "verified", digest))

    monkeypatch.setattr(install_task_service, "acquire_pin", _skip_acquire)
    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(install_service, "approve", _answer(operation_id, "approved", digest))
    monkeypatch.setattr(install_service, "apply", apply)
    monkeypatch.setattr(install_service, "resume", resume)
    with pytest.raises(CliFailure) as raised:
        task_command.start(
            {
                "intent": "install",
                "idempotency-key": "install-kill-resume-0001",
                "input": _facts(
                    tmp_path,
                    {
                        "harness_id": "cursor",
                        "setup_id": new_id("setup"),
                        "setup_version": "1.4",
                        "project_root": str(tmp_path.resolve()),
                    },
                ),
            }
        )
    assert raised.value.code == "AI_STP_INTERNAL"
    status = task_command.status({"task": raised.value.details["task"]})
    assert status.payload.state == "running"
    assert status.payload.child_operation_ids == [operation_id]
    finished = task_command.continue_(
        {"task": status.payload.task_id, "revision": status.payload.revision}
    )
    assert planned == 1
    assert applied == 1
    assert resumed == 1
    assert finished.payload.state == "completed"
    assert finished.payload.outcome is not None
    assert finished.payload.outcome.kind == "install"
    assert finished.payload.outcome.verified is True


def test_install_mints_missing_context_passports_before_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import closing

    from ai_stp_cli.local import passports, project_passport
    from ai_stp_cli.local.database import configured_path, open_readonly

    _stub_lifecycle(monkeypatch, [])
    project = tmp_path / "project"
    project.mkdir()
    started = task_command.start(
        {
            "intent": "install",
            "idempotency-key": "install-mint-passport-0001",
            "input": _facts(
                tmp_path,
                {"harness_id": "cursor", "project_root": str(project.resolve())},
            ),
        }
    )
    assert started.payload.state == "completed"
    with closing(open_readonly(configured_path())) as connection:
        assert project_passport.stable_id_for(connection, project.resolve())
        assert passports.developer_stable_id(connection)
        assert passports.device_stable_id(connection)


def test_install_plan_receives_the_catalogued_harness_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Mapping[str, object]] = []

    def plan(parameters: Mapping[str, object]) -> Answer[InstallationView]:
        seen.append(parameters)
        return Answer(_installation(new_id("operation"), "planned", "sha256:" + "a" * 64))

    monkeypatch.setattr(install_task_service, "acquire_pin", _skip_acquire)
    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(
        install_service, "approve", _answer(new_id("operation"), "approved", "sha256:" + "a" * 64)
    )
    monkeypatch.setattr(
        install_service, "apply", _answer(new_id("operation"), "verified", "sha256:" + "a" * 64)
    )
    project = tmp_path / "project"
    project.mkdir()
    task_command.start(
        {
            "intent": "install",
            "idempotency-key": "install-plan-target-0001",
            "input": _facts(
                tmp_path,
                {"harness_id": "cursor", "project_root": str(project.resolve())},
            ),
        }
    )
    assert seen
    target = Path(str(seen[0]["target"]))
    assert target.is_dir()
    assert target.is_absolute()
    assert target == install_task_service.harness_target("cursor")


def test_install_drain_failure_names_the_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def plan(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "provider isolation is unavailable",
            next_actions=[
                "provider network --json",
                "install plan --json",
                "install recover --operation operation_01 --json",
            ],
        )

    monkeypatch.setattr(install_task_service, "acquire_pin", _skip_acquire)
    monkeypatch.setattr(install_service, "plan", plan)
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(CliFailure) as raised:
        task_command.start(
            {
                "intent": "install",
                "idempotency-key": "install-fail-names-task-01",
                "input": _facts(
                    tmp_path,
                    {"harness_id": "cursor", "project_root": str(project.resolve())},
                ),
            }
        )
    assert str(raised.value.details.get("task", "")).startswith("task_")
    assert raised.value.details.get("state") == "failed"
    assert raised.value.next_actions == ["install recover --operation operation_01 --json"]


def test_relative_project_root_does_not_become_global(tmp_path: Path) -> None:
    started = task_command.start(
        {
            "intent": "install",
            "idempotency-key": "install-relative-root-0001",
            "input": _facts(
                tmp_path,
                {
                    "harness_id": "cursor",
                    "setup_id": new_id("setup"),
                    "setup_version": "1.4",
                    "project_root": "relative",
                },
            ),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "blocked"
    assert continued.payload.questions[0].question_id == "project-root"


def test_install_reasks_when_project_root_is_harness_config(tmp_path: Path) -> None:
    from ai_stp_cli.local import harnesses

    detector = next(item for item in harnesses.DETECTORS if item.harness_id == "cursor")
    config = harnesses.config_root(detector)
    started = task_command.start(
        {
            "intent": "install",
            "idempotency-key": "install-reject-config-root-01",
            "input": _facts(tmp_path, {"harness_id": "cursor", "project_root": str(config)}),
        }
    )
    assert started.payload.state == "blocked"
    assert started.payload.questions[0].question_id == "project-root"
    assert "harness config" in started.payload.questions[0].why


def test_install_task_module_does_not_start_a_process() -> None:
    source = Path("apps/cli/src/ai_stp_cli/application/install_task.py").read_text("utf-8")
    assert "Popen" not in source
    assert "subprocess" not in source


def _stub_lifecycle(monkeypatch: pytest.MonkeyPatch, acquired: list[tuple[str, str]]) -> str:
    operation_id = new_id("operation")
    digest = "sha256:" + "b" * 64
    monkeypatch.setattr(install_task_service, "acquire_pin", _capture_acquire(acquired))
    monkeypatch.setattr(install_service, "plan", _answer(operation_id, "planned", digest))
    monkeypatch.setattr(install_service, "approve", _answer(operation_id, "approved", digest))
    monkeypatch.setattr(install_service, "apply", _answer(operation_id, "verified", digest))
    return operation_id


def _no_recommendation(_harness: str) -> SetupPin | None:
    return None


def _skip_acquire(_setup_id: str, _setup_version: str) -> None:
    return None


def _capture_acquire(
    acquired: list[tuple[str, str]],
) -> Callable[[str, str], None]:
    def acquire_pin(setup_id: str, setup_version: str) -> None:
        acquired.append((setup_id, setup_version))

    return acquire_pin


def _answer(
    operation_id: str, state: str, digest: str
) -> Callable[[Mapping[str, object]], Answer[InstallationView]]:
    def handler(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return Answer(_installation(operation_id, state, digest))

    return handler


def _installation(operation_id: str, state: str, digest: str) -> InstallationView:
    return InstallationView.model_validate(
        {
            "operation_id": operation_id,
            "action": "install",
            "state": state,
            "plan_digest": digest,
            "target_id": "project:cursor",
            "expected_target_digest": digest,
            "expires_at": "2026-09-15T00:00:00.000Z",
        }
    )


def _facts(tmp_path: Path, body: dict[str, str]) -> str:
    place = tmp_path / "input.json"
    place.write_text(json.dumps(body), encoding="utf-8")
    return str(place)
