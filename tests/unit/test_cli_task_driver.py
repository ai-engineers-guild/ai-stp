# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportIndexIssue=false
"""Deterministic argv driver for the agent corpus. No LLM. Native cells stay not_run."""

from __future__ import annotations

import json
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final, cast

import pytest

from ai_stp_cli.answer import Answer
from ai_stp_cli.app import main as cli_main
from ai_stp_cli.application import account as account_service
from ai_stp_cli.application import change as change_service
from ai_stp_cli.application import initialize as initialize_service
from ai_stp_cli.application import install as install_service
from ai_stp_cli.application import install_task as install_task_service
from ai_stp_cli.application import publish as publish_service
from ai_stp_cli.application import switch as switch_service
from ai_stp_cli.application.initialize import (
    ANTIGRAVITY_LIMITATION,
    PATCH_OPERATION,
    SECTION_BEGIN,
    PatchObservation,
    extract_section,
    instruction_path,
    patch_file_text,
    section_digest,
)
from ai_stp_cli.application.qualify import (
    AGENT_RUNS,
    AGENT_SCENARIOS,
    PLATFORMS,
    agent_cells,
    extra_status,
    native_cells,
    tree_digest,
    wheel_status,
)
from ai_stp_cli.cloud import session
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import preserved_setups, setup_derive
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.cli_copy import INITIALIZE_PROMPT, INITIALIZE_START, INTENTS_BOOTSTRAP
from ai_stp_contracts.first_party import FirstPartyCatalogMember, catalog_identity
from ai_stp_contracts.machine_help import (
    AuthStatus,
    DeviceApproval,
    InstallationView,
    PublicationPlanView,
    TaskView,
)
from ai_stp_foundation.harnesses import HARNESS_ID_ORDER
from ai_stp_foundation.ids import new_id
from ai_stp_passports.versions import SetupVersionPassport

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_SKILL = ROOT / "skills" / "canonical" / "ai-stp" / "SKILL.md"
CORPUS = AGENT_SCENARIOS
STABLE = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
PLAN = "plan_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
PLAN_HASH = "plan_" + "c" * 64
ACCOUNT = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
DEVICE = "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
CORPUS_DRIVERS: Final[tuple[tuple[str, str], ...]] = (
    ("fresh-initialize-prompt", "test_website_initialize_prompt_is_the_task_start_line"),
    ("no-reinit-on-coding", "test_inspect_argv_loop_does_not_run_initialize"),
    ("install-exact-pin", "test_install_exact_pin_uses_emitted_argv"),
    ("install-without-pin", "test_install_without_pin_uses_emitted_argv"),
    ("change-add-component", "test_change_add_component_uses_emitted_argv"),
    ("switch-preserved-setup", "test_switch_preserved_setup_argv_restores_user_snapshot"),
    ("unsupported-project-local", "test_relative_project_root_argv_stays_blocked"),
    ("login-skipped", "test_login_skipped_argv_does_not_begin"),
    ("login-idle-no-upload", "test_login_idle_argv_does_not_upload"),
    ("publish-private", "test_publish_private_argv_omits_git_binding"),
    ("publish-public-filesystem", "test_publish_public_argv_uses_filesystem_provenance"),
    ("author-directory", "test_author_directory_argv_mints_one_setup"),
    ("compensated-install", "test_compensated_install_argv_is_not_ok"),
    ("kill-after-apply", "test_kill_after_apply_argv_resumes_the_held_operation"),
    ("concurrent-continue", "test_concurrent_continue_argv_has_one_winner"),
    ("pending-reload-not-loaded", "test_pending_reload_argv_is_not_session_loaded"),
    ("auth-required-publish", "test_auth_required_publish_argv_shows_one_user_code"),
    ("antigravity-limitation", "test_antigravity_initialize_argv_does_not_invent_a_file"),
    ("custom-home-section", "test_custom_home_section_argv_uses_provider_hooks"),
    ("expert-recovery-no-dump", "test_canonical_skill_does_not_dump_the_registry"),
)


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, object]]:
    code = cli_main(argv)
    captured = capsys.readouterr()
    parsed: object = json.loads(captured.out)
    assert isinstance(parsed, dict)
    return code, cast(dict[str, object], parsed)


def _follow(body: dict[str, object], capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    current = body
    while current.get("continuations"):
        continuations = current["continuations"]
        assert isinstance(continuations, list)
        first = cast(dict[str, object], continuations[0])
        if first.get("actor") != "cli":
            return current
        raw_argv = first["argv"]
        assert isinstance(raw_argv, list)
        argv = [str(item) for item in cast(list[object], raw_argv)]
        code, current = _run(argv, capsys)
        assert code == 0
        assert current["ok"] is True
    return current


def test_corpus_names_the_twenty_agent_scenarios() -> None:
    assert len(CORPUS) == 20
    assert len(set(CORPUS)) == 20
    assert tuple(name for name, _ in CORPUS_DRIVERS) == CORPUS
    missing = [name for _, name in CORPUS_DRIVERS if name not in globals()]
    assert missing == []
    assert wheel_status() == "not_built"
    assert extra_status() == "not_built"


def test_idempotent_start_joins_a_running_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    operation_id = "operation_01JQZK7B8N4M6P2R9T5V0X3Y8D"
    digest = "sha256:" + "a" * 64
    entered = threading.Event()
    gate = threading.Event()
    applied = 0

    def acquire_pin(_setup_id: str, _setup_version: str) -> None:
        return None

    def plan(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "planned", digest)

    def approve(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "approved", digest)

    def apply(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        nonlocal applied
        applied += 1
        entered.set()
        assert gate.wait(timeout=5)
        return _answer_install(operation_id, "verified", digest)

    monkeypatch.setattr(install_task_service, "acquire_pin", acquire_pin)
    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(install_service, "approve", approve)
    monkeypatch.setattr(install_service, "apply", apply)
    facts = _facts_file(tmp_path, {"harness_id": "cursor", "project_root": str(tmp_path.resolve())})
    parameters: dict[str, object] = {
        "intent": "install",
        "idempotency-key": "driver-install-join-running-01",
        "input": str(facts),
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(lambda: task_command.start(parameters))
        if not entered.wait(timeout=60):
            if first.done():
                first.result()
            raise AssertionError("install apply never started")
        second = pool.submit(lambda: task_command.start(parameters))
        gate.set()
        # Deadlock guards, not performance assertions: the join path polls up
        # to RUNNING_JOIN_SECONDS, and a slow runner must not trip the test.
        winner = first.result(timeout=60)
        joined = second.result(timeout=60)
    assert winner.payload.state == "completed"
    assert joined.payload.state == "completed"
    assert winner.payload.task_id == joined.payload.task_id
    assert winner.continuations == ()
    assert joined.continuations == ()
    assert applied == 1


def test_idempotent_start_joins_a_same_key_insert_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    operation_id = "operation_01JQZK7B8N4M6P2R9T5V0X3Y8E"
    digest = "sha256:" + "b" * 64
    applied = 0

    def acquire_pin(_setup_id: str, _setup_version: str) -> None:
        return None

    def plan(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "planned", digest)

    def approve(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "approved", digest)

    def apply(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        nonlocal applied
        applied += 1
        return _answer_install(operation_id, "verified", digest)

    monkeypatch.setattr(install_task_service, "acquire_pin", acquire_pin)
    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(install_service, "approve", approve)
    monkeypatch.setattr(install_service, "apply", apply)
    facts = _facts_file(tmp_path, {"harness_id": "cursor", "project_root": str(tmp_path.resolve())})
    parameters: dict[str, object] = {
        "intent": "install",
        "idempotency-key": "driver-install-insert-race-01",
        "input": str(facts),
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(lambda: task_command.start(parameters))
        second = pool.submit(lambda: task_command.start(parameters))
        # Same rationale: 10s was within reach of a loaded Windows worker.
        winner = first.result(timeout=60)
        joined = second.result(timeout=60)
    assert winner.payload.state == "completed"
    assert joined.payload.state == "completed"
    assert winner.payload.task_id == joined.payload.task_id
    assert winner.continuations == ()
    assert joined.continuations == ()
    assert applied == 1


def test_website_initialize_prompt_is_the_task_start_line() -> None:
    assert INTENTS_BOOTSTRAP == "ai-stp task intents --json"
    assert "task start --intent initialize" in INITIALIZE_START
    assert INITIALIZE_START in INITIALIZE_PROMPT
    assert "plan" not in INITIALIZE_PROMPT
    assert "approve" not in INITIALIZE_PROMPT


def test_inspect_argv_loop_does_not_run_initialize(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, catalog = _run(["task", "intents", "--json"], capsys)
    assert code == 0
    names = [item["name"] for item in catalog["data"]["intents"]]  # type: ignore[index]
    assert names[0] == "inspect"
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "inspect",
            "--idempotency-key",
            "driver-inspect-no-reinit-01",
            "--json",
        ],
        capsys,
    )
    assert code == 0
    finished = _follow(started, capsys)
    assert finished["data"]["outcome"]["kind"] == "inspect"  # type: ignore[index]
    assert finished["data"]["goal_satisfied"] is True  # type: ignore[index]


def test_antigravity_initialize_argv_does_not_invent_a_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    facts = tmp_path / "input.json"
    facts.write_text(json.dumps({"harness_id": "antigravity"}), encoding="utf-8")
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "initialize",
            "--idempotency-key",
            "driver-antigravity-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    finished = _follow(started, capsys)
    outcome = finished["data"]["outcome"]  # type: ignore[index]
    assert outcome["kind"] == "initialize"
    assert outcome["wrote"] is False
    assert outcome["limitation"] == ANTIGRAVITY_LIMITATION
    assert outcome["surface"] == ""
    marker = SECTION_BEGIN.encode()
    written = [
        path
        for path in (tmp_path / "home").rglob("*")
        if path.is_file() and marker in path.read_bytes()
    ]
    assert written == []


def test_claude_initialize_blocks_without_writing_a_global_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    facts = tmp_path / "input.json"
    facts.write_text(json.dumps({"harness_id": "claude-code"}), encoding="utf-8")
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "initialize",
            "--idempotency-key",
            "driver-claude-block-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    blocked = started
    assert blocked["ok"] is True
    assert blocked["data"]["state"] == "blocked"  # type: ignore[index]
    assert blocked["data"]["questions"][0]["question_id"] == "provider-too-old"  # type: ignore[index]
    assert blocked["continuations"][0]["actor"] == "external"  # type: ignore[index]
    continuation = blocked["continuations"][0]
    assert isinstance(continuation, dict)
    raw_argv = continuation["argv"]
    assert isinstance(raw_argv, list)
    code, again = _run([str(item) for item in raw_argv], capsys)
    assert code == 0
    assert again["ok"] is True
    assert again["data"]["state"] == "blocked"  # type: ignore[index]
    assert again["data"]["questions"][0]["question_id"] == "provider-too-old"  # type: ignore[index]
    home = tmp_path / "home"
    marker = SECTION_BEGIN.encode()
    written = [path for path in home.rglob("*") if path.is_file() and marker in path.read_bytes()]
    assert written == []


def test_canonical_skill_does_not_dump_the_registry() -> None:
    text = CANONICAL_SKILL.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 500
    assert "203" not in text
    assert "help --agent" not in text.split("## Start here", 1)[1].split("##", 1)[0]
    recover = (CANONICAL_SKILL.parent / "references" / "recover.md").read_text(encoding="utf-8")
    assert "install recover" in recover
    assert "task intents --json" in recover
    assert "Do not dump" in recover or "do not dump" in recover.lower()
    assert "provider-too-old" in text
    assert "not login" in text


def test_unrun_native_and_agent_cells_stay_not_run() -> None:
    native = native_cells()
    agent = agent_cells()
    assert CORPUS == AGENT_SCENARIOS
    assert len(native) == len(HARNESS_ID_ORDER) * len(PLATFORMS) == 21
    assert len(agent) == len(CORPUS) * AGENT_RUNS == 100
    assert set(native.values()) == {"not_run"}
    assert set(agent.values()) == {"not_run"}


def test_install_without_pin_uses_emitted_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pin = install_task_service.recommend_setup("cursor")
    assert pin is not None
    operation_id = "operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
    digest = "sha256:" + "e" * 64

    def acquire_pin(_setup_id: str, _setup_version: str) -> None:
        return None

    def plan(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "planned", digest)

    def approve(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "approved", digest)

    def apply(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "verified", digest)

    monkeypatch.setattr(install_task_service, "acquire_pin", acquire_pin)
    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(install_service, "approve", approve)
    monkeypatch.setattr(install_service, "apply", apply)
    facts = tmp_path / "input.json"
    facts.write_text(
        json.dumps({"harness_id": "cursor", "project_root": str(tmp_path.resolve())}),
        encoding="utf-8",
    )
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "install",
            "--idempotency-key",
            "driver-install-no-pin-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    finished = _follow(started, capsys)
    outcome = finished["data"]["outcome"]  # type: ignore[index]
    assert outcome["kind"] == "install"
    assert outcome["setup_id"] == pin.setup_id
    assert outcome["verified"] is True


def test_install_exact_pin_uses_emitted_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pin = install_task_service.recommend_setup("cursor")
    assert pin is not None
    operation_id = "operation_01JQZK7B8N4M6P2R9T5V0X3Y8A"
    native_root = tmp_path / "native"
    native_file = native_root / ".cursor" / "rules" / "ai-stp.mdc"
    digest = ""

    def acquire_pin(setup_id: str, setup_version: str) -> None:
        assert setup_id == pin.setup_id
        assert setup_version == pin.setup_version

    def plan(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "planned", "sha256:" + "d" * 64)

    def approve(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "approved", "sha256:" + "d" * 64)

    def apply(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        native_file.parent.mkdir(parents=True, exist_ok=True)
        native_file.write_text("alwaysApply: true\n", encoding="utf-8")
        nonlocal digest
        digest = tree_digest(native_root)
        return _answer_install(operation_id, "verified", digest)

    monkeypatch.setattr(install_task_service, "acquire_pin", acquire_pin)
    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(install_service, "approve", approve)
    monkeypatch.setattr(install_service, "apply", apply)
    facts = tmp_path / "input.json"
    facts.write_text(
        json.dumps(
            {
                "harness_id": "cursor",
                "setup_id": pin.setup_id,
                "setup_version": pin.setup_version,
                "project_root": str(tmp_path.resolve()),
            }
        ),
        encoding="utf-8",
    )
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "install",
            "--idempotency-key",
            "driver-install-exact-pin-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    finished = _follow(started, capsys)
    outcome = finished["data"]["outcome"]  # type: ignore[index]
    assert outcome["kind"] == "install"
    assert outcome["setup_id"] == pin.setup_id
    assert outcome["setup_version"] == pin.setup_version
    assert outcome["verified"] is True
    assert native_file.is_file()
    assert digest.startswith("sha256:")
    assert tree_digest(native_root) == digest


def test_custom_home_section_argv_uses_provider_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    target = instruction_path("codex")
    assert target is not None
    target.write_text("keep-me\n", encoding="utf-8")
    _install_initialize_hooks(monkeypatch)
    facts = tmp_path / "input.json"
    facts.write_text(json.dumps({"harness_id": "codex"}), encoding="utf-8")
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "initialize",
            "--idempotency-key",
            "driver-custom-home-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    finished = _follow(started, capsys)
    outcome = finished["data"]["outcome"]  # type: ignore[index]
    assert outcome["kind"] == "initialize"
    assert outcome["wrote"] is True
    assert outcome["surface"] == "AGENTS.md"
    text = target.read_text(encoding="utf-8")
    assert text.startswith("keep-me\n")
    assert SECTION_BEGIN in text


def test_compensated_install_argv_is_not_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    operation_id = "operation_01JQZK7B8N4M6P2R9T5V0X3Y7A"
    digest = "sha256:" + "c" * 64

    def acquire_pin(_setup_id: str, _setup_version: str) -> None:
        return None

    def plan(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "planned", digest)

    def approve(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "approved", digest)

    def apply(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        raise CliFailure(
            "AI_STP_COMPENSATED",
            "the requested install did not complete; compensation finished",
            operation_id=operation_id,
        )

    monkeypatch.setattr(install_task_service, "acquire_pin", acquire_pin)
    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(install_service, "approve", approve)
    monkeypatch.setattr(install_service, "apply", apply)
    facts = tmp_path / "input.json"
    facts.write_text(
        json.dumps({"harness_id": "cursor", "project_root": str(tmp_path.resolve())}),
        encoding="utf-8",
    )
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "install",
            "--idempotency-key",
            "driver-compensated-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code != 0
    assert started["ok"] is False
    error = started["error"]
    assert isinstance(error, dict)
    assert error["code"] == "AI_STP_COMPENSATED"
    dumped = json.dumps(started)
    assert "install apply" not in dumped
    task_id = _error_task_id(started)
    code, status = _run(["task", "status", "--task", task_id, "--json"], capsys)
    assert code == 0
    assert status["data"]["state"] == "failed"  # type: ignore[index]
    assert status["data"]["goal_satisfied"] is False  # type: ignore[index]


def test_pending_reload_argv_is_not_session_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = preserved_setups.PreservedSetup(
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

    def resolve_saved(
        *,
        harness_id: str,
        project_root: str,
        preserved_setup_id: str | None,
    ) -> preserved_setups.PreservedSetup:
        del harness_id, project_root, preserved_setup_id
        return saved

    def capture_drift(_saved: preserved_setups.PreservedSetup) -> str:
        return new_id("setup")

    def restore(_saved: preserved_setups.PreservedSetup) -> InstallationView:
        return _answer_install(new_id("operation"), "verified", "sha256:" + "b" * 64).payload

    monkeypatch.setattr(switch_service, "resolve_saved", resolve_saved)
    monkeypatch.setattr(switch_service, "capture_drift", capture_drift)
    monkeypatch.setattr(switch_service, "restore", restore)
    facts = tmp_path / "input.json"
    facts.write_text(
        json.dumps({"harness_id": "cursor", "project_root": str(tmp_path.resolve())}),
        encoding="utf-8",
    )
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "switch",
            "--idempotency-key",
            "driver-pending-reload-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    blocked = started
    assert blocked["ok"] is True
    payload = blocked["data"]
    assert isinstance(payload, dict)
    assert payload["state"] == "blocked"
    assert payload["goal_satisfied"] is False
    assert payload["outcome"] is None
    questions = cast(list[object], payload["questions"])
    question = cast(dict[str, object], questions[0])
    assert question["question_id"] == "reload-session"
    dumped = json.dumps(blocked)
    assert '"session_loaded": true' not in dumped


def test_switch_preserved_setup_argv_restores_user_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    saved = preserved_setups.PreservedSetup(
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
    restored: list[str] = []

    def resolve_saved(
        *,
        harness_id: str,
        project_root: str,
        preserved_setup_id: str | None,
    ) -> preserved_setups.PreservedSetup:
        del harness_id, project_root, preserved_setup_id
        return saved

    def capture_drift(_saved: preserved_setups.PreservedSetup) -> str:
        return new_id("setup")

    def restore(item: preserved_setups.PreservedSetup) -> InstallationView:
        restored.append(item.stable_id)
        return _answer_install(new_id("operation"), "verified", "sha256:" + "b" * 64).payload

    monkeypatch.setattr(switch_service, "resolve_saved", resolve_saved)
    monkeypatch.setattr(switch_service, "capture_drift", capture_drift)
    monkeypatch.setattr(switch_service, "restore", restore)
    facts = _facts_file(tmp_path, {"harness_id": "cursor", "project_root": str(tmp_path.resolve())})
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "switch",
            "--idempotency-key",
            "driver-switch-preserved-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    blocked = started
    payload = blocked["data"]
    assert isinstance(payload, dict)
    assert payload["state"] == "blocked"
    questions = cast(list[object], payload["questions"])
    question = cast(dict[str, object], questions[0])
    assert question["question_id"] == "reload-session"
    assert restored == [saved.stable_id]
    code, replayed = _run(
        [
            "task",
            "start",
            "--intent",
            "switch",
            "--idempotency-key",
            "driver-switch-preserved-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    replay_payload = replayed["data"]
    assert isinstance(replay_payload, dict)
    assert replay_payload["task_id"] == payload["task_id"]
    assert replay_payload["state"] == "blocked"
    assert restored == [saved.stable_id]


def test_relative_project_root_argv_stays_blocked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    facts = _facts_file(
        tmp_path,
        {
            "harness_id": "cursor",
            "setup_id": new_id("setup"),
            "setup_version": "1.4",
            "project_root": "relative",
        },
    )
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "install",
            "--idempotency-key",
            "driver-relative-root-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    blocked = started
    payload = blocked["data"]
    assert isinstance(payload, dict)
    assert payload["state"] == "blocked"
    questions = cast(list[object], payload["questions"])
    question = cast(dict[str, object], questions[0])
    assert question["question_id"] == "project-root"
    assert payload["goal_satisfied"] is False


def test_change_add_component_uses_emitted_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pin = install_task_service.recommend_setup("cursor")
    assert pin is not None
    extra = _extra_cursor_component()
    derived_id = new_id("setup")
    operation_id = "operation_01JQZK7B8N4M6P2R9T5V0X3Y8B"
    digest = "sha256:" + "b" * 64
    seen: list[str] = []

    def derive_setup(**kwargs: object) -> setup_derive.DerivedSetup:
        source = kwargs["source"]
        assert isinstance(source, SetupVersionPassport)
        seen.append(source.stable_id)
        return setup_derive.DerivedSetup(
            setup_id=derived_id,
            setup_version="1.0",
            minted=True,
            source_setup_id=pin.setup_id,
            source_setup_version=pin.setup_version,
        )

    monkeypatch.setattr(change_service, "derive_setup", derive_setup)
    _stub_install_ok(monkeypatch, operation_id, digest)
    facts = _facts_file(
        tmp_path,
        {
            "harness_id": "cursor",
            "component_id": extra.stable_id,
            "component_version": extra.version,
            "project_root": str(tmp_path.resolve()),
        },
    )
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "change",
            "--idempotency-key",
            "driver-change-add-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    finished = _follow(started, capsys)
    outcome = finished["data"]["outcome"]  # type: ignore[index]
    assert outcome["kind"] == "change"
    assert outcome["setup_id"] == derived_id
    assert outcome["source_setup_id"] == pin.setup_id
    assert outcome["minted"] is True
    assert seen == [pin.setup_id]


def test_author_directory_argv_mints_one_setup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tree = tmp_path / "demo-skill"
    tree.mkdir()
    (tree / "SKILL.md").write_text("# Demo\n\nA local skill.\n", encoding="utf-8")
    facts = _facts_file(
        tmp_path,
        {
            "directory": str(tree),
            "harness_id": "cursor",
            "component_type": "skill",
            "name": "demo",
            "license_spdx": "MIT",
        },
    )
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "author",
            "--idempotency-key",
            "driver-author-directory-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    finished = _follow(started, capsys)
    outcome = _mapping(finished["data"])
    outcome = _mapping(outcome["outcome"])
    assert outcome["kind"] == "author"
    setup_id = outcome["setup_id"]
    component_id = outcome["component_id"]
    assert isinstance(setup_id, str)
    assert isinstance(component_id, str)
    assert setup_id.startswith("setup_")
    assert component_id.startswith("component_")
    assert outcome["minted"] is True


def test_publish_private_argv_omits_git_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    planned: list[Mapping[str, object]] = []
    monkeypatch.setattr(account_service, "ensure_session", _signed_in)

    def plan_publication(parameters: Mapping[str, object]) -> PublicationPlanView:
        planned.append(dict(parameters))
        return _publication_plan("validating")

    def confirm_publication(*, plan_id: str, plan_hash: str) -> PublicationPlanView:
        return _publication_plan("validating", plan_id=plan_id, plan_hash=plan_hash)

    monkeypatch.setattr(publish_service, "plan_publication", plan_publication)
    monkeypatch.setattr(publish_service, "confirm_publication", confirm_publication)
    facts = _facts_file(tmp_path, {"object_id": STABLE, "object_version": "1.0"})
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "publish",
            "--idempotency-key",
            "driver-publish-private-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    finished = _follow(started, capsys)
    payload = _mapping(finished["data"])
    assert payload["goal_satisfied"] is False
    outcome = _mapping(payload["outcome"])
    assert outcome["kind"] == "publish"
    assert outcome["visibility"] == "private"
    assert outcome["source_binding_id"] == ""
    assert outcome["readable"] is False
    assert outcome["provenance"] == "filesystem"
    assert planned == [{"id": STABLE, "version": "1.0", "visibility": "private"}]
    dumped = json.dumps(planned[0])
    assert "source-binding-id" not in dumped
    assert "git" not in dumped


def test_publish_public_argv_uses_filesystem_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    planned: list[Mapping[str, object]] = []
    monkeypatch.setattr(account_service, "ensure_session", _signed_in)

    def plan_publication(parameters: Mapping[str, object]) -> PublicationPlanView:
        planned.append(dict(parameters))
        return _publication_plan("published", visibility="public")

    def confirm_publication(*, plan_id: str, plan_hash: str) -> PublicationPlanView:
        return _publication_plan(
            "published", plan_id=plan_id, plan_hash=plan_hash, visibility="public"
        )

    monkeypatch.setattr(publish_service, "plan_publication", plan_publication)
    monkeypatch.setattr(publish_service, "confirm_publication", confirm_publication)
    facts = _facts_file(
        tmp_path,
        {"object_id": STABLE, "object_version": "1.0", "visibility": "public"},
    )
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "publish",
            "--idempotency-key",
            "driver-publish-public-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    finished = _follow(started, capsys)
    payload = _mapping(finished["data"])
    assert payload["goal_satisfied"] is True
    outcome = _mapping(payload["outcome"])
    assert outcome["kind"] == "publish"
    assert outcome["visibility"] == "public"
    assert outcome["provenance"] == "filesystem"
    assert outcome["source_binding_id"] == ""
    assert planned[0]["visibility"] == "public"
    assert "git" not in json.dumps(planned[0])


def test_login_skipped_argv_does_not_begin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    begun: list[str] = []

    def begin(provider: str) -> DeviceApproval:
        begun.append(provider)
        return _approval(provider)

    monkeypatch.setattr(account_service, "begin", begin)
    monkeypatch.setattr(account_service, "sync_now", _forbid_sync)
    _hold_session()
    facts = _facts_file(tmp_path, {"action": "login", "provider": "google"})
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "account",
            "--idempotency-key",
            "driver-login-skipped-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    finished = _follow(started, capsys)
    outcome = finished["data"]["outcome"]  # type: ignore[index]
    assert outcome["kind"] == "account"
    assert outcome["authenticated"] is True
    assert outcome["login_uploaded"] is False
    assert begun == []


def test_login_idle_argv_does_not_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(account_service, "begin", _approval)
    monkeypatch.setattr(account_service, "sync_now", _forbid_sync)
    facts = _facts_file(tmp_path, {"action": "login", "provider": "google"})
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "account",
            "--idempotency-key",
            "driver-login-idle-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    blocked = started
    payload = blocked["data"]
    assert isinstance(payload, dict)
    assert payload["state"] == "blocked"
    questions = cast(list[object], payload["questions"])
    question = cast(dict[str, object], questions[0])
    assert question["question_id"] == "authorization"
    assert question["actor"] == "external"
    assert question["recommended"] == "ABCD-EFGH"
    dumped = json.dumps(blocked)
    assert "/publications" not in dumped
    assert "/sync-plans" not in dumped
    assert "/revisions" not in dumped
    assert '"login_uploaded": true' not in dumped


def test_auth_required_publish_argv_shows_one_user_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(account_service, "begin", _approval)
    facts = _facts_file(
        tmp_path,
        {"object_id": STABLE, "object_version": "1.0", "provider": "google"},
    )
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "publish",
            "--idempotency-key",
            "driver-auth-required-publish-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    blocked = started
    payload = blocked["data"]
    assert isinstance(payload, dict)
    assert payload["state"] == "blocked"
    questions = cast(list[object], payload["questions"])
    question = cast(dict[str, object], questions[0])
    assert question["question_id"] == "authorization"
    assert question["actor"] == "external"
    assert question["recommended"] == "ABCD-EFGH"
    argv = _first_argv(blocked)
    assert argv.count("continue") == 1


def test_kill_after_apply_argv_resumes_the_held_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    operation_id = "operation_01JQZK7B8N4M6P2R9T5V0X3Y8C"
    digest = "sha256:" + "d" * 64
    planned = 0
    applied = 0
    resumed = 0

    def acquire_pin(_setup_id: str, _setup_version: str) -> None:
        return None

    def plan(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        nonlocal planned
        planned += 1
        return _answer_install(operation_id, "planned", digest)

    def approve(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "approved", digest)

    def apply(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        nonlocal applied
        applied += 1
        if applied == 1:
            raise RuntimeError("killed after apply")
        raise AssertionError("apply must not run again")

    def resume(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        nonlocal resumed
        resumed += 1
        return _answer_install(operation_id, "verified", digest)

    monkeypatch.setattr(install_task_service, "acquire_pin", acquire_pin)
    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(install_service, "approve", approve)
    monkeypatch.setattr(install_service, "apply", apply)
    monkeypatch.setattr(install_service, "resume", resume)
    facts = _facts_file(tmp_path, {"harness_id": "cursor", "project_root": str(tmp_path.resolve())})
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "install",
            "--idempotency-key",
            "driver-kill-after-apply-01",
            "--input",
            str(facts),
            "--json",
        ],
        capsys,
    )
    assert code != 0
    assert started["ok"] is False
    error = started["error"]
    assert isinstance(error, dict)
    assert error["code"] == "AI_STP_INTERNAL"
    continuations = started["continuations"]
    assert isinstance(continuations, list)
    assert continuations
    argv = _first_argv(started)
    assert "continue" in argv
    assert "--task" in argv
    task_id = _error_task_id(started)
    code, status = _run(["task", "status", "--task", task_id, "--json"], capsys)
    assert code == 0
    payload = _mapping(status["data"])
    assert payload["state"] == "running"
    assert payload["child_operation_ids"] == [operation_id]
    assert isinstance(payload["revision"], int)
    code, finished = _run(
        [
            "task",
            "continue",
            "--task",
            task_id,
            "--revision",
            str(payload["revision"]),
            "--json",
        ],
        capsys,
    )
    assert code == 0
    assert planned == 1
    assert applied == 1
    assert resumed == 1
    outcome = finished["data"]["outcome"]  # type: ignore[index]
    assert outcome["kind"] == "install"
    assert outcome["verified"] is True


def test_concurrent_continue_argv_has_one_winner(capsys: pytest.CaptureFixture[str]) -> None:
    code, started = _run(
        [
            "task",
            "start",
            "--intent",
            "initialize",
            "--idempotency-key",
            "driver-concurrent-continue-01",
            "--json",
        ],
        capsys,
    )
    assert code == 0
    payload = _mapping(started["data"])
    assert payload["state"] == "blocked"
    parameters = {"task": payload["task_id"], "revision": payload["revision"]}
    won: list[Answer[TaskView]] = []
    lost: list[CliFailure] = []

    def work() -> None:
        try:
            won.append(task_command.continue_(parameters))
        except CliFailure as error:
            lost.append(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(work), pool.submit(work)]
        for future in futures:
            future.result()
    # One executor drains; the second caller joins its committed result or
    # conflicts on the stale revision — it never runs a parallel drain.
    assert len(won) + len(lost) == 2
    assert all(error.code == "AI_STP_CONFLICT" for error in lost)
    assert all(item.payload.task_id == payload["task_id"] for item in won)
    assert any(item.payload.state == "blocked" for item in won)
    assert all(item.payload.state in {"blocked", "planned", "running"} for item in won)


def _first_argv(body: dict[str, object]) -> list[str]:
    continuations = body["continuations"]
    assert isinstance(continuations, list)
    first = cast(dict[str, object], continuations[0])
    raw_argv = first["argv"]
    assert isinstance(raw_argv, list)
    return [str(item) for item in cast(list[object], raw_argv)]


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _error_task_id(body: dict[str, object]) -> str:
    details = _mapping(_mapping(body["error"])["details"])
    task_id = details["task"]
    assert isinstance(task_id, str)
    return task_id


def _install_initialize_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        initialize_service, "provider_operations", lambda: frozenset({PATCH_OPERATION})
    )

    def patcher(harness_id: str, section: str) -> PatchObservation:
        path = instruction_path(harness_id)
        assert path is not None
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        updated, wrote = patch_file_text(existing, section)
        if wrote:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(updated, encoding="utf-8")
        observed = extract_section(updated) or updated
        return PatchObservation(section_digest=section_digest(observed), wrote=wrote)

    monkeypatch.setattr(initialize_service, "patch_via_provider", patcher)


def _answer_install(operation_id: str, state: str, digest: str) -> Answer[InstallationView]:
    return Answer(
        InstallationView.model_validate(
            {
                "operation_id": operation_id,
                "action": "install",
                "state": state,
                "plan_digest": digest,
                "target_id": "project:cursor",
                "expected_target_digest": digest,
                "expires_at": "2026-09-16T00:00:00.000Z",
            }
        )
    )


def _facts_file(tmp_path: Path, body: Mapping[str, str]) -> Path:
    place = tmp_path / "input.json"
    place.write_text(json.dumps(body), encoding="utf-8")
    return place


def _stub_install_ok(monkeypatch: pytest.MonkeyPatch, operation_id: str, digest: str) -> None:
    def plan(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "planned", digest)

    def approve(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "approved", digest)

    def apply(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return _answer_install(operation_id, "verified", digest)

    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(install_service, "approve", approve)
    monkeypatch.setattr(install_service, "apply", apply)


def _extra_cursor_component() -> FirstPartyCatalogMember:
    base = catalog_identity("cursor", "baseline")
    full = catalog_identity("cursor", "full-auto")
    held = {item.stable_id for item in base.component_refs}
    return next(item for item in full.component_refs if item.stable_id not in held)


def _signed_in(_facts: object) -> AuthStatus:
    return AuthStatus(
        state="authenticated",
        account_id=ACCOUNT,
        expires_at="2026-09-16T00:00:00.000Z",
        credential_store="file",
    )


def _publication_plan(
    state: str,
    *,
    plan_id: str = PLAN,
    plan_hash: str = PLAN_HASH,
    visibility: str = "private",
) -> PublicationPlanView:
    return PublicationPlanView.model_validate(
        {
            "schema_version": 1,
            "plan_id": plan_id,
            "plan_hash": plan_hash,
            "state": state,
            "object_kind": "component",
            "stable_id": STABLE,
            "version": "1.0",
            "content_digest": "sha256:" + "b" * 64,
            "visibility": visibility,
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


def _forbid_sync(*, scope: str, stable_id: str) -> object:
    raise AssertionError(f"login must not sync ({scope}, {stable_id})")
