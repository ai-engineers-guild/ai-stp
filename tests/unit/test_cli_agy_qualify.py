# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false
"""Isolated agy qualify workspace and scoring. Live model runs stay in agy_qualify.main."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_stp_cli.agy_qualify import (
    ANTIGRAVITY,
    AUTH_PUBLISH,
    AUTHOR_DIR,
    CHANGE_ADD,
    COMPENSATED,
    CONCURRENT,
    CUSTOM_HOME,
    FOLLOW_ACTOR,
    FRESH_INIT,
    INPUT_CWD_HINT,
    INSTALL_OPEN,
    INSTALL_PIN,
    KILL_AFTER,
    LOGIN_IDLE,
    LOGIN_SKIP,
    NO_REINIT,
    PENDING_RELOAD,
    PUBLISH_PRIV,
    PUBLISH_PUB,
    RECOVER,
    RELATIVE_ROOT,
    SKILL_TAIL,
    STALE_VERIFIED_SCENARIOS,
    SUPPORTED_SCENARIOS,
    SWITCH_SAVED,
    UNASSISTED_ENV,
    VERIFIED_DRAIN,
    Workspace,
    agy_argv,
    bundled_cli,
    capacity_miss,
    choreographed,
    clear_cell,
    cursor_pin,
    custom_home_section_landed,
    debug_provider,
    drive_native_install,
    escaped_workspace,
    extra_cursor_ref,
    host_home,
    incomplete_capacity_hit,
    invalidate_cell,
    invalidate_scenario,
    invalidate_target,
    main,
    native_install_passed,
    next_fill_cell,
    prepare_workspace,
    prompt_for,
    qualify_one,
    registry_path,
    run_was_background_killed,
    run_was_unavailable,
    score,
    score_no_reinit,
    start_command,
    task_intents,
    unassisted_prompt_for,
    unrun_cells,
    write_cell,
    write_isolation,
    write_native_cell,
)
from ai_stp_cli.application.qualify import AGENT_RUNS, AGENT_SCENARIOS, AGY_MODEL
from ai_stp_contracts.cli_copy import INITIALIZE_PROMPT, INITIALIZE_START


def test_prepare_workspace_copies_the_canonical_skill(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path)
    root = workspace.project / ".agents" / "skills" / "ai-stp"
    skill = root / "SKILL.md"
    assert skill.is_file()
    text = skill.read_text(encoding="utf-8")
    assert "task intents --json" in text
    assert "install plan" in text
    assert not (root / "locale").exists()
    assert (root / "references" / "recover.md").is_file()
    assert workspace.wrapper.is_file()
    wrapper = workspace.wrapper.read_text(encoding="utf-8")
    assert "uv run" not in wrapper
    assert str(workspace.home) in wrapper
    assert "cli.log" in wrapper
    assert "exec " in wrapper
    assert "AI_STP_FORCE_FILE_CREDENTIAL_STORE=1" in wrapper


def test_unscoped_help_is_choreography(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path)
    (workspace.root / "cli.log").write_text("help --json\n", encoding="utf-8")
    assert choreographed(workspace) is True
    (workspace.root / "cli.log").write_text("help\n", encoding="utf-8")
    assert choreographed(workspace) is True
    (workspace.root / "cli.log").write_text("ai-stp help --json\n", encoding="utf-8")
    assert choreographed(workspace) is True
    (workspace.root / "cli.log").write_text("task intents --json\n", encoding="utf-8")
    assert choreographed(workspace) is False


def test_capabilities_dump_is_choreography(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path)
    (workspace.root / "cli.log").write_text("capabilities --json\n", encoding="utf-8")
    assert choreographed(workspace) is True
    (workspace.root / "cli.log").write_text("ai-stp capabilities\n", encoding="utf-8")
    assert choreographed(workspace) is True
    (workspace.root / "cli.log").write_text("doctor --json\n", encoding="utf-8")
    assert choreographed(workspace) is False


@pytest.mark.skipif(os.name == "nt", reason="the qualify wrapper is a POSIX shell script")
def test_prepare_workspace_resolves_a_relative_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace = prepare_workspace(Path("throwaway"), scenario=CUSTOM_HOME)
    assert workspace.wrapper.is_absolute()
    assert workspace.wrapper.is_file()
    held = subprocess.run(
        [str(workspace.wrapper), "version", "--json"],
        cwd=workspace.project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert held.returncode == 0, held.stderr


@pytest.mark.skipif(os.name == "nt", reason="the qualify wrapper is a POSIX shell script")
def test_wrapper_runs_the_cli_under_isolated_home(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path)
    assert bundled_cli().is_file()
    result = subprocess.run(
        [str(workspace.wrapper), "version", "--json"],
        cwd=workspace.project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert '"ok": true' in result.stdout or '"ok":true' in result.stdout
    log = (workspace.root / "cli.log").read_text(encoding="utf-8")
    assert "version --json" in log
    refused = subprocess.run(
        [str(workspace.wrapper), "inspect", "--root", "/tmp/ai-stp-qualify-escape", "--json"],
        cwd=workspace.project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert refused.returncode == 78
    assert "outside the workspace" in refused.stderr
    inside = subprocess.run(
        [str(workspace.wrapper), "version", "--json"],
        cwd=workspace.project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert inside.returncode == 0, inside.stderr


def test_docker_wrapper_jails_before_docker_and_does_not_uv_run(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path, docker_image="ai-stp-iso:local")
    text = workspace.wrapper.read_text(encoding="utf-8")
    assert "--privileged" in text
    assert "ai-stp-iso:local" in text
    assert "python -m ai_stp_cli" in text
    assert "chown -R" in text
    assert "uv run" not in text
    assert f"exec {bundled_cli()}" not in text
    if os.name == "nt":
        return
    refused = subprocess.run(
        [str(workspace.wrapper), "inspect", "--root", "/tmp/ai-stp-qualify-escape", "--json"],
        cwd=workspace.project,
        check=False,
        capture_output=True,
        text=True,
    )
    assert refused.returncode == 78
    assert "outside the workspace" in refused.stderr


def test_docker_wrapper_mounts_providers_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    providers = tmp_path / "providers"
    providers.mkdir()
    monkeypatch.setenv("AI_STP_QUALIFY_PROVIDERS", str(providers))
    workspace = prepare_workspace(tmp_path / "ws", docker_image="ai-stp-iso:local")
    text = workspace.wrapper.read_text(encoding="utf-8")
    assert str(providers.resolve()) in text
    assert ":/opt/providers:ro" in text


def test_host_home_ignores_uv_temp_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/tmp/uv-fake-home")
    monkeypatch.delenv("AI_STP_HOST_HOME", raising=False)
    assert host_home() != Path("/tmp/uv-fake-home")


def test_score_no_reinit_passes_when_initialize_was_not_started(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path)
    assert task_intents(workspace.home) == ()
    assert score_no_reinit(workspace.home) == "pass"
    place = registry_path(workspace.home)
    place.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(place)) as connection:
        connection.execute("CREATE TABLE agent_task (intent TEXT)")
        connection.execute("INSERT INTO agent_task VALUES ('inspect')")
        connection.commit()
    assert task_intents(workspace.home) == ("inspect",)
    assert score_no_reinit(workspace.home) == "pass"
    with closing(sqlite3.connect(place)) as connection:
        connection.execute("INSERT INTO agent_task VALUES ('initialize')")
        connection.commit()
    assert score_no_reinit(workspace.home) == "fail"
    other = prepare_workspace(tmp_path / "no-reinit-install")
    _insert_intent(other.home, "install")
    assert score_no_reinit(other.home) == "fail"


def _insert_intent(
    home: Path,
    intent: str,
    *,
    state: str = "completed",
    goal_satisfied: bool = True,
    verified: bool = True,
    outcome: dict[str, object] | None = None,
    questions: list[dict[str, object]] | None = None,
) -> None:
    place = registry_path(home)
    place.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {"kind": intent, "verified": verified, "state": "verified"}
    if outcome:
        payload.update(outcome)
    held = json.dumps(payload)
    questions_json = json.dumps(questions or [])
    with closing(sqlite3.connect(place)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_task (
                intent TEXT,
                state TEXT,
                goal_satisfied INTEGER,
                outcome_json TEXT,
                questions_json TEXT
            )
            """
        )
        cols = {str(row[1]) for row in connection.execute("PRAGMA table_info(agent_task)")}
        for name, spec in (
            ("state", "TEXT"),
            ("goal_satisfied", "INTEGER"),
            ("outcome_json", "TEXT"),
            ("questions_json", "TEXT"),
        ):
            if name not in cols:
                connection.execute(f"ALTER TABLE agent_task ADD COLUMN {name} {spec}")
        connection.execute(
            "INSERT INTO agent_task "
            "(intent, state, goal_satisfied, outcome_json, questions_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (intent, state, int(goal_satisfied), held, questions_json),
        )
        connection.commit()


def _drive(workspace: Workspace, intent: str) -> None:
    _insert_intent(workspace.home, intent)
    (workspace.root / "cli.log").write_text(
        f"task start --intent {intent} --json\ntask continue --task t --revision 1 --json\n",
        encoding="utf-8",
    )


def _seed_fault_task(
    home: Path,
    *,
    task_id: str = "task_fault",
    key: str = "fault-key",
    state: str = "completed",
    goal_satisfied: bool = True,
    children: tuple[str, ...] = ("op_fault",),
) -> None:
    """A durable install task row with the columns the fault oracle reads."""
    place = registry_path(home)
    place.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(place)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_task (
                task_id TEXT,
                revision INTEGER,
                intent TEXT,
                state TEXT,
                goal_satisfied INTEGER,
                idempotency_key TEXT,
                payload_json TEXT,
                outcome_json TEXT,
                questions_json TEXT,
                child_operation_ids_json TEXT
            )
            """
        )
        cols = {str(row[1]) for row in connection.execute("PRAGMA table_info(agent_task)")}
        for name, spec in (
            ("task_id", "TEXT"),
            ("revision", "INTEGER"),
            ("idempotency_key", "TEXT"),
            ("child_operation_ids_json", "TEXT"),
            ("state", "TEXT"),
            ("goal_satisfied", "INTEGER"),
        ):
            if name not in cols:
                connection.execute(f"ALTER TABLE agent_task ADD COLUMN {name} {spec}")
        connection.execute(
            "INSERT INTO agent_task "
            "(task_id, revision, intent, state, goal_satisfied, idempotency_key,"
            " child_operation_ids_json) VALUES (?, ?, 'install', ?, ?, ?, ?)",
            (
                task_id,
                3,
                state,
                int(goal_satisfied),
                key,
                json.dumps(list(children)),
            ),
        )
        connection.commit()


def _seed_fault_op(home: Path, *, operation_id: str = "op_fault", state: str = "verified") -> None:
    place = registry_path(home)
    place.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(place)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS operation (
                operation_id TEXT,
                kind TEXT,
                state TEXT,
                started_at TEXT,
                finished_at TEXT,
                detail TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO operation VALUES (?, 'install.install', ?, 't', NULL, NULL)",
            (operation_id, state),
        )
        connection.commit()


def _seed_fault(
    workspace: Workspace,
    *,
    kind: str,
    task_id: str = "task_fault",
    state: str = "completed",
    goal_satisfied: bool = True,
    op_state: str = "verified",
    operation_id: str = "op_fault",
    extra: dict[str, object] | None = None,
) -> None:
    """Fault evidence plus the durable rows the oracle reads it against."""
    _seed_fault_task(
        workspace.home,
        task_id=task_id,
        state=state,
        goal_satisfied=goal_satisfied,
        children=(operation_id,),
    )
    _seed_fault_op(workspace.home, operation_id=operation_id, state=op_state)
    fault: dict[str, object] = {"kind": kind, "task_id": task_id}
    if extra:
        fault.update(extra)
    (workspace.root / "fault.json").write_text(json.dumps(fault), encoding="utf-8")


def _drive_initialize_limitation(workspace: Workspace) -> None:
    _insert_intent(
        workspace.home,
        "initialize",
        outcome={
            "kind": "initialize",
            "harness_id": "antigravity",
            "wrote": False,
            "limitation": "no_global_instruction",
        },
    )
    (workspace.root / "cli.log").write_text(
        "task start --intent initialize --json\n"
        "task answer --task t --revision 1 --question-id harness-id --value antigravity --json\n",
        encoding="utf-8",
    )


def test_supported_scenarios_are_the_full_corpus() -> None:
    assert frozenset(AGENT_SCENARIOS) == SUPPORTED_SCENARIOS
    assert KILL_AFTER in SUPPORTED_SCENARIOS
    assert CONCURRENT in SUPPORTED_SCENARIOS
    assert COMPENSATED in SUPPORTED_SCENARIOS
    assert PENDING_RELOAD in SUPPORTED_SCENARIOS


def test_fresh_initialize_prompt_is_the_website_line(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path, scenario=FRESH_INIT)
    text = prompt_for(FRESH_INIT, workspace)
    assert INITIALIZE_START in text
    assert INITIALIZE_PROMPT in text
    assert "plan" not in INITIALIZE_PROMPT
    assert "yourself" in SKILL_TAIL
    assert "JSON field" in SKILL_TAIL
    pin_prompt = prompt_for(INSTALL_PIN, workspace)
    assert "setup_" in pin_prompt or "@" in pin_prompt
    assert "--intent install" in pin_prompt
    assert "--input install-input.json" in pin_prompt
    assert "--input /" not in pin_prompt
    assert INPUT_CWD_HINT in pin_prompt
    assert "Absolute project root:" not in pin_prompt
    assert str(workspace.project.resolve()) not in pin_prompt
    assert (workspace.project / "install-input.json").is_file()
    assert VERIFIED_DRAIN in pin_prompt
    open_prompt = prompt_for(INSTALL_OPEN, workspace)
    assert VERIFIED_DRAIN in open_prompt
    assert "--input" in open_prompt
    assert INPUT_CWD_HINT in open_prompt
    assert "Absolute project root:" not in open_prompt
    assert str(workspace.project.resolve()) not in open_prompt
    assert VERIFIED_DRAIN in prompt_for(CHANGE_ADD, workspace)
    assert VERIFIED_DRAIN in prompt_for(SWITCH_SAVED, workspace)
    assert VERIFIED_DRAIN not in prompt_for(COMPENSATED, workspace)
    assert VERIFIED_DRAIN not in prompt_for(RELATIVE_ROOT, workspace)
    (workspace.root / "fault.json").write_text(
        json.dumps({"task_id": "task_fault", "kind": "compensated-install"}),
        encoding="utf-8",
    )
    compensated_prompt = prompt_for(COMPENSATED, workspace)
    assert "task status --task task_fault --json" in compensated_prompt
    assert "task continue --task task_fault --revision" in compensated_prompt
    assert "compensation" in compensated_prompt.lower()
    assert "Never start a second install" in compensated_prompt
    assert "Do not type task start" in compensated_prompt
    kill_prompt = prompt_for(KILL_AFTER, workspace)
    assert "task status --task task_fault --json" in kill_prompt
    assert "task continue --task task_fault --revision" in kill_prompt
    assert "Never start a second install" in kill_prompt
    concurrent_prompt = prompt_for(CONCURRENT, workspace)
    assert "Harness: cursor" in concurrent_prompt
    assert "task status --task task_fault --json" in concurrent_prompt
    assert "Never start a second install" in concurrent_prompt
    assert "Never type task get" in prompt_for(RECOVER, workspace)
    assert "task intents --json" in prompt_for(RECOVER, workspace)
    assert start_command("change") in prompt_for(CHANGE_ADD, workspace)
    assert "Harness: cursor" in prompt_for(CHANGE_ADD, workspace)
    assert "Do not wait for a person" in prompt_for(CHANGE_ADD, workspace)
    assert "Do not type component add" in prompt_for(CHANGE_ADD, workspace)
    assert "Answer component-ref" in prompt_for(CHANGE_ADD, workspace)
    assert "Add component" not in prompt_for(CHANGE_ADD, workspace)
    switch_prompt = prompt_for(SWITCH_SAVED, workspace)
    assert "--intent switch" in switch_prompt
    assert "--input" in switch_prompt
    assert INPUT_CWD_HINT in switch_prompt
    assert "Absolute project root:" not in switch_prompt
    assert (workspace.project / "switch-input.json").is_file()
    switch_input = json.loads((workspace.project / "switch-input.json").read_text(encoding="utf-8"))
    assert switch_input["project_root"] == str(workspace.project.resolve())
    assert "Answer reload-session with done" in switch_prompt
    assert "run the emitted task answer argv" in switch_prompt
    pending_prompt = prompt_for(PENDING_RELOAD, workspace)
    assert "--input switch-input.json" in pending_prompt
    assert INPUT_CWD_HINT in pending_prompt
    assert "Absolute project root:" not in pending_prompt
    assert str(workspace.project.resolve()) not in pending_prompt
    assert "session_loaded must stay false" in pending_prompt
    assert (workspace.project / "switch-input.json").is_file()
    assert "--input install-input.json" in prompt_for(RELATIVE_ROOT, workspace)
    assert "--value relative" in prompt_for(RELATIVE_ROOT, workspace)
    assert "Do not invent a path" in prompt_for(RELATIVE_ROOT, workspace)
    assert (workspace.project / "install-input.json").is_file()
    author_prompt = prompt_for(AUTHOR_DIR, workspace)
    assert "--input author-input.json" in author_prompt
    assert INPUT_CWD_HINT in author_prompt
    assert "Do not wait for a person" in author_prompt
    assert "Never type task get" in author_prompt
    assert (workspace.project / "author-input.json").is_file()
    assert (workspace.root / "author-input.json").is_file()
    assert "--input publish-input.json" in prompt_for(PUBLISH_PRIV, workspace)
    assert INPUT_CWD_HINT in prompt_for(PUBLISH_PRIV, workspace)
    assert str(workspace.project.resolve()) not in prompt_for(PUBLISH_PRIV, workspace)
    assert (workspace.project / "publish-input.json").is_file()
    assert json.loads((workspace.project / "publish-input.json").read_text())["visibility"] == (
        "private"
    )
    assert "--input publish-input.json" in prompt_for(PUBLISH_PUB, workspace)
    assert "filesystem provenance" in prompt_for(PUBLISH_PUB, workspace)
    assert "--input publish-input.json" in prompt_for(AUTH_PUBLISH, workspace)
    assert "Auth is required" in prompt_for(AUTH_PUBLISH, workspace)
    assert "Do not type publication plan" in prompt_for(AUTH_PUBLISH, workspace)
    assert "Do not type setup publish plan" in prompt_for(AUTH_PUBLISH, workspace)
    assert "--input account-input.json" in prompt_for(LOGIN_IDLE, workspace)
    assert "Do not task continue" in prompt_for(LOGIN_IDLE, workspace)
    assert "then task continue" not in prompt_for(LOGIN_IDLE, workspace)
    assert (workspace.project / "account-input.json").is_file()
    assert "Do not run ai-stp" in prompt_for(LOGIN_SKIP, workspace)
    assert SKILL_TAIL not in prompt_for(LOGIN_SKIP, workspace)
    assert "--input switch-input.json" in prompt_for(PENDING_RELOAD, workspace)
    assert INITIALIZE_START in prompt_for(ANTIGRAVITY, workspace)
    custom = prepare_workspace(tmp_path / "codex", scenario=CUSTOM_HOME)
    assert "CODEX_HOME" in custom.wrapper.read_text(encoding="utf-8")
    custom_prompt = prompt_for(CUSTOM_HOME, custom)
    assert "--input initialize-input.json" in custom_prompt
    assert "CODEX_HOME/AGENTS.md" in custom_prompt
    assert INPUT_CWD_HINT in custom_prompt
    assert (custom.project / "initialize-input.json").is_file()


def test_unassisted_prompts_are_plain_user_requests(tmp_path: Path) -> None:
    """The unassisted corpus carries goals and user facts, never argv coaching."""
    coaching = (
        "task start",
        "task continue",
        "task answer",
        "task intents",
        "task status",
        "--intent",
        "--idempotency-key",
        "--input ",
        "--value",
        "--json",
        "Do not ",
        "Execute ai-stp",
        "actor is",
        "continuations",
    )
    for scenario in sorted(AGENT_SCENARIOS):
        workspace = prepare_workspace(tmp_path / f"un-{scenario}", scenario=scenario)
        if scenario in {COMPENSATED, KILL_AFTER, CONCURRENT}:
            _seed_fault(workspace, kind="kill-after-apply", task_id="task_un")
        text = unassisted_prompt_for(scenario, workspace)
        assert text, scenario
        if scenario == NO_REINIT:
            assert text == "What is 2+2?"
            continue
        assert UNASSISTED_ENV in text, scenario
        if scenario == FRESH_INIT:
            # The website's own initialize copy is website text, not coaching.
            assert INITIALIZE_PROMPT in text
            continue
        for marker in coaching:
            assert marker not in text, f"{scenario}: coaching marker {marker!r} leaked"


def test_unassisted_prompts_bind_their_user_facts(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path / "un-pin", scenario=INSTALL_PIN)
    assert cursor_pin() in unassisted_prompt_for(INSTALL_PIN, workspace)
    seeded = prepare_workspace(tmp_path / "un-change", scenario=CHANGE_ADD)
    change_text = unassisted_prompt_for(CHANGE_ADD, seeded)
    assert extra_cursor_ref() in change_text
    assert cursor_pin() in change_text
    faulted = prepare_workspace(tmp_path / "un-fault", scenario=KILL_AFTER)
    _seed_fault(faulted, kind="kill-after-apply", task_id="task_un")
    assert "task_un" in unassisted_prompt_for(KILL_AFTER, faulted)
    relative = prepare_workspace(tmp_path / "un-rel", scenario=RELATIVE_ROOT)
    relative_text = unassisted_prompt_for(RELATIVE_ROOT, relative)
    assert "relative" in relative_text
    assert "--value" not in relative_text


def test_unassisted_cells_land_in_their_own_layer(tmp_path: Path) -> None:
    measured = tmp_path / "measured.json"
    write_cell(measured, NO_REINIT, 0, "pass")
    write_cell(measured, NO_REINIT, 0, "fail", layer="unassisted")
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert body["agent"][f"{NO_REINIT}:0"] == "pass"
    assert body["unassisted"][f"{NO_REINIT}:0"] == "fail"
    assert invalidate_cell(measured, NO_REINIT, 0, layer="unassisted") == 1
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert f"{NO_REINIT}:0" not in body["unassisted"]
    assert body["agent"][f"{NO_REINIT}:0"] == "pass"
    with pytest.raises(ValueError):
        write_cell(measured, NO_REINIT, 1, "pass", layer="other")


def test_model_guard_covers_unassisted_cells(tmp_path: Path) -> None:
    measured = tmp_path / "measured.json"
    write_cell(measured, NO_REINIT, 0, "pass", layer="unassisted")
    with pytest.raises(ValueError, match="different or unknown model"):
        write_cell(measured, NO_REINIT, 1, "pass", model="other-model", layer="unassisted")


def test_unassisted_qualify_writes_own_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    measured = tmp_path / "measured.json"
    write_cell(measured, LOGIN_SKIP, 0, "fail")

    def _run(workspace: Workspace, **kwargs: object) -> int:
        prompt = str(kwargs.get("prompt") or "")
        assert "task start" not in prompt
        (workspace.root / "agy.stdout").write_text(
            '{"status":"SUCCESS","response":"already signed in"}\n', encoding="utf-8"
        )
        (workspace.root / "agy.stderr").write_text("", encoding="utf-8")
        return 0

    monkeypatch.setattr("ai_stp_cli.agy_qualify.run_agy", _run)
    code = qualify_one(
        root=tmp_path / "cell",
        scenario=LOGIN_SKIP,
        run=0,
        measured=measured,
        agy=Path("/bin/agy"),
        timeout=5,
        probe=False,
        unassisted=True,
    )
    assert code == 0
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert body["unassisted"][f"{LOGIN_SKIP}:0"] == "pass"
    assert body["agent"][f"{LOGIN_SKIP}:0"] == "fail"


def test_custom_home_score_requires_the_codex_section(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path / "custom-score", scenario=CUSTOM_HOME)
    (workspace.root / "cli.log").write_text(
        "task start --intent initialize --input initialize-input.json --json\n",
        encoding="utf-8",
    )
    assert score(CUSTOM_HOME, workspace) == "fail"
    _insert_intent(
        workspace.home,
        "initialize",
        outcome={"kind": "initialize", "wrote": True, "harness_id": "codex"},
    )
    assert score(CUSTOM_HOME, workspace) == "fail"
    agents = workspace.home / "codex-home" / "AGENTS.md"
    agents.write_text(":::begin-ai-stp\nhello\n:::end-ai-stp\n", encoding="utf-8")
    assert score(CUSTOM_HOME, workspace) == "pass"
    (workspace.home / "CLAUDE.md").write_text("hand-written\n", encoding="utf-8")
    assert score(CUSTOM_HOME, workspace) == "fail"


def test_initialize_score_requires_wrote_or_limitation(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path / "init-score")
    (workspace.root / "cli.log").write_text(
        "task start --intent initialize --json\ntask continue --task t --revision 1 --json\n",
        encoding="utf-8",
    )
    _insert_intent(workspace.home, "initialize")
    assert score(FRESH_INIT, workspace) == "fail"
    assert score(ANTIGRAVITY, workspace) == "fail"
    _drive_initialize_limitation(workspace)
    assert score(FRESH_INIT, workspace) == "pass"
    assert score(ANTIGRAVITY, workspace) == "pass"
    wrote = prepare_workspace(tmp_path / "init-wrote")
    (wrote.root / "cli.log").write_text(
        "task start --intent initialize --json\n",
        encoding="utf-8",
    )
    _insert_intent(
        wrote.home,
        "initialize",
        outcome={"kind": "initialize", "harness_id": "codex", "wrote": True, "limitation": ""},
    )
    assert score(FRESH_INIT, wrote) == "fail"
    (wrote.home / ".codex").mkdir()
    (wrote.home / ".codex" / "AGENTS.md").write_text(
        ":::begin-ai-stp\nhello\n:::end-ai-stp\n",
        encoding="utf-8",
    )
    assert score(FRESH_INIT, wrote) == "pass"
    assert score(ANTIGRAVITY, wrote) == "fail"


def test_score_requires_the_matching_intent_and_rejects_expert_leaves(
    tmp_path: Path,
) -> None:
    workspace = prepare_workspace(tmp_path)
    assert score(FRESH_INIT, workspace) == "fail"
    _insert_intent(workspace.home, "initialize")
    assert score(FRESH_INIT, workspace) == "fail"
    _drive_initialize_limitation(workspace)
    assert score(FRESH_INIT, workspace) == "pass"
    (workspace.root / "cli.log").write_text("install apply --operation x\n", encoding="utf-8")
    assert score(FRESH_INIT, workspace) == "fail"
    (workspace.root / "cli.log").write_text(
        "task start --intent initialize --json\ntask continue --task t --revision 1 --json\n",
        encoding="utf-8",
    )
    assert score(FRESH_INIT, workspace) == "pass"
    (workspace.home / "CLAUDE.md").write_text("hand-written\n", encoding="utf-8")
    assert score(FRESH_INIT, workspace) == "fail"
    other = prepare_workspace(tmp_path / "author", scenario=AUTHOR_DIR)
    assert (other.project / "demo-skill" / "SKILL.md").is_file()
    assert score(AUTHOR_DIR, other) == "fail"
    _insert_intent(
        other.home,
        "author",
        outcome={
            "kind": "author",
            "minted": True,
            "setup_id": "setup_demo",
            "component_id": "cmp_demo",
        },
    )
    (other.root / "cli.log").write_text(
        "task start --intent author --input author-input.json --json\n",
        encoding="utf-8",
    )
    assert score(AUTHOR_DIR, other) == "pass"
    relative = prepare_workspace(tmp_path / "relative", scenario=RELATIVE_ROOT)
    _drive(relative, "install")
    assert score(RELATIVE_ROOT, relative) == "fail"
    blocked_relative = prepare_workspace(tmp_path / "relative-block", scenario=RELATIVE_ROOT)
    _insert_intent(
        blocked_relative.home,
        "install",
        state="blocked",
        goal_satisfied=False,
        verified=False,
        questions=[{"question_id": "project-root", "actor": "human"}],
    )
    (blocked_relative.root / "cli.log").write_text(
        "task start --intent install --json\n"
        "task answer --task t --revision 3 --question-id harness-id --value cursor --json\n"
        "task answer --task t --revision 5 --question-id project-root --value relative --json\n",
        encoding="utf-8",
    )
    assert score(RELATIVE_ROOT, blocked_relative) == "pass"
    dumped_relative = prepare_workspace(tmp_path / "dumped-relative", scenario=RELATIVE_ROOT)
    _insert_intent(
        dumped_relative.home,
        "install",
        state="blocked",
        goal_satisfied=False,
        verified=False,
        questions=[{"question_id": "project-root", "actor": "human"}],
    )
    (dumped_relative.root / "cli.log").write_text(
        "task start --intent install --json\n"
        "task answer --task t --revision 5 --question-id project-root "
        f"--value {SKILL_TAIL.strip()} --json\n",
        encoding="utf-8",
    )
    assert score(RELATIVE_ROOT, dumped_relative) == "fail"
    skipped = prepare_workspace(tmp_path / "skip")
    assert score(LOGIN_SKIP, skipped) == "pass"
    (skipped.root / "cli.log").write_text("sync push --scope account\n", encoding="utf-8")
    assert score(LOGIN_SKIP, skipped) == "fail"
    used_skip = prepare_workspace(tmp_path / "skip-cli")
    (used_skip.root / "cli.log").write_text(
        "task start --intent inspect --json\n", encoding="utf-8"
    )
    assert score(LOGIN_SKIP, used_skip) == "fail"
    helper = prepare_workspace(tmp_path / "help-path")
    _drive_initialize_limitation(helper)
    (helper.root / "cli.log").write_text("help --path task --json\n", encoding="utf-8")
    assert score(FRESH_INIT, helper) == "fail"
    dumped_help = prepare_workspace(tmp_path / "dumped-help")
    _drive(dumped_help, "install")
    (dumped_help.root / "cli.log").write_text("--help\n", encoding="utf-8")
    assert score(INSTALL_OPEN, dumped_help) == "fail"
    invented = prepare_workspace(tmp_path / "invented-status")
    _drive_initialize_limitation(invented)
    (invented.root / "cli.log").write_text("task status --task-id task_01\n", encoding="utf-8")
    assert score(FRESH_INIT, invented) == "fail"
    hijacked = prepare_workspace(tmp_path / "init-account")
    _drive_initialize_limitation(hijacked)
    _insert_intent(hijacked.home, "account")
    (hijacked.root / "cli.log").write_text(
        "task start --intent initialize --json\n"
        "task answer --task t --revision 3 --question-id harness-id --value cursor --json\n"
        "task start --intent account --json\n",
        encoding="utf-8",
    )
    assert score(FRESH_INIT, hijacked) == "fail"
    got = prepare_workspace(tmp_path / "invented-get")
    _drive(got, "install")
    (got.root / "cli.log").write_text(
        "task start --intent install --json\n"
        "task answer --task t --revision 3 --question-id harness-id --value cursor --json\n"
        "task get --task t --json\n",
        encoding="utf-8",
    )
    assert score(INSTALL_OPEN, got) == "fail"
    tail_dump = prepare_workspace(tmp_path / "tail-dump", scenario=ANTIGRAVITY)
    _drive_initialize_limitation(tail_dump)
    (tail_dump.root / "cli.log").write_text(
        "task start --intent initialize --json\n"
        "task answer --task t --revision 3 --question-id harness-id "
        f"--value {SKILL_TAIL.strip()} --json\n",
        encoding="utf-8",
    )
    assert score(ANTIGRAVITY, tail_dump) == "pass"
    published = prepare_workspace(tmp_path / "pub", scenario=PUBLISH_PRIV)
    assert score(PUBLISH_PRIV, published) == "fail"
    _drive(published, "publish")
    assert score(PUBLISH_PRIV, published) == "fail"
    started = prepare_workspace(tmp_path / "start-only")
    _insert_intent(started.home, "install", state="blocked", goal_satisfied=False, verified=False)
    (started.root / "cli.log").write_text(
        "task start --intent install --idempotency-key install-session-01 --json\n",
        encoding="utf-8",
    )
    assert score(INSTALL_OPEN, started) == "fail"
    drained = prepare_workspace(tmp_path / "start-drained")
    _insert_intent(drained.home, "install")
    (drained.root / "cli.log").write_text(
        "task start --intent install --idempotency-key install-session-01 --json\n",
        encoding="utf-8",
    )
    assert score(INSTALL_OPEN, drained) == "pass"
    passported = prepare_workspace(tmp_path / "passported")
    _drive(passported, "install")
    (passported.root / "cli.log").write_text(
        "task start --intent install --json\n"
        "task answer --task t --revision 5 --question-id project-root --json\n"
        "project passport --root /tmp/x --json\n",
        encoding="utf-8",
    )
    assert score(INSTALL_OPEN, passported) == "fail"
    networked = prepare_workspace(tmp_path / "networked")
    _drive(networked, "install")
    (networked.root / "cli.log").write_text(
        "task start --intent install --json\nprovider network --json\n",
        encoding="utf-8",
    )
    assert score(INSTALL_OPEN, networked) == "fail"
    valueless = prepare_workspace(tmp_path / "valueless")
    _drive(valueless, "install")
    (valueless.root / "cli.log").write_text(
        "task start --intent install --json\n"
        "task answer --task t --revision 3 --question-id harness-id --json\n",
        encoding="utf-8",
    )
    assert score(INSTALL_OPEN, valueless) == "fail"
    escaped = prepare_workspace(tmp_path / "escaped")
    _drive(escaped, "switch")
    (escaped.root / "cli.log").write_text(
        "task start --intent switch --json\n"
        "task answer --task t --revision 3 --question-id project-root "
        "--value /tmp/ai-stp-qualify-escape --json\n",
        encoding="utf-8",
    )
    assert escaped_workspace(escaped)
    assert score(SWITCH_SAVED, escaped) == "fail"
    tilde = prepare_workspace(tmp_path / "tilde")
    _drive(tilde, "switch")
    (tilde.root / "cli.log").write_text(
        "task start --intent switch --json\n"
        "task answer --task t --revision 3 --question-id project-root "
        "--value ~/.gemini/antigravity-cli --json\n",
        encoding="utf-8",
    )
    assert score(SWITCH_SAVED, tilde) == "fail"
    pinned = prepare_workspace(tmp_path / "pinned-root")
    _drive(pinned, "install")
    (pinned.root / "cli.log").write_text(
        "task start --intent install --json\n"
        f"task answer --task t --revision 3 --question-id project-root "
        f"--value {pinned.project} --json\n",
        encoding="utf-8",
    )
    assert not escaped_workspace(pinned)
    assert score(INSTALL_OPEN, pinned) == "pass"
    failed = prepare_workspace(tmp_path / "failed-install")
    _insert_intent(failed.home, "install", state="failed", goal_satisfied=False, verified=False)
    (failed.root / "cli.log").write_text(
        "task start --intent install --json\n"
        "task answer --task t --revision 3 --question-id harness-id --value cursor --json\n"
        "task answer --task t --revision 5 --question-id project-root "
        f"--value {failed.project} --json\n",
        encoding="utf-8",
    )
    assert score(INSTALL_OPEN, failed) == "fail"
    unverified = prepare_workspace(tmp_path / "unverified-install")
    _insert_intent(
        unverified.home, "install", state="completed", goal_satisfied=True, verified=False
    )
    (unverified.root / "cli.log").write_text(
        "task start --intent install --json\ntask continue --task t --revision 1 --json\n",
        encoding="utf-8",
    )
    assert score(INSTALL_OPEN, unverified) == "fail"
    stub = prepare_workspace(tmp_path / "stub-install")
    place = registry_path(stub.home)
    place.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(place)) as connection:
        connection.execute("CREATE TABLE agent_task (intent TEXT)")
        connection.execute("INSERT INTO agent_task VALUES ('install')")
        connection.commit()
    (stub.root / "cli.log").write_text(
        "task start --intent install --json\ntask continue --task t --revision 1 --json\n",
        encoding="utf-8",
    )
    assert score(INSTALL_OPEN, stub) == "fail"
    assert score(INSTALL_PIN, stub) == "fail"
    changed = prepare_workspace(tmp_path / "change-ok")
    _drive(changed, "change")
    assert score(CHANGE_ADD, changed) == "pass"
    failed_change = prepare_workspace(tmp_path / "failed-change")
    _insert_intent(
        failed_change.home, "change", state="failed", goal_satisfied=False, verified=False
    )
    (failed_change.root / "cli.log").write_text(
        "task start --intent change --json\ntask continue --task t --revision 1 --json\n",
        encoding="utf-8",
    )
    assert score(CHANGE_ADD, failed_change) == "fail"
    switched = prepare_workspace(tmp_path / "switch-ok")
    _drive(switched, "switch")
    assert score(SWITCH_SAVED, switched) == "pass"
    failed_switch = prepare_workspace(tmp_path / "failed-switch")
    _insert_intent(
        failed_switch.home, "switch", state="failed", goal_satisfied=False, verified=False
    )
    (failed_switch.root / "cli.log").write_text(
        "task start --intent switch --json\ntask continue --task t --revision 1 --json\n",
        encoding="utf-8",
    )
    assert score(SWITCH_SAVED, failed_switch) == "fail"


def test_unknown_scenario_exits_before_agy(tmp_path: Path) -> None:
    code = main(
        [
            "--root",
            str(tmp_path / "ws"),
            "--scenario",
            "not-a-scenario",
            "--run",
            "0",
        ]
    )
    assert code == 2


def test_every_agent_scenario_has_a_prompt_and_score(tmp_path: Path) -> None:
    for scenario in AGENT_SCENARIOS:
        workspace = prepare_workspace(tmp_path / scenario, scenario=scenario)
        assert prompt_for(scenario, workspace)
        assert score(scenario, workspace) in {"pass", "fail", "not_run"}


def test_pending_reload_fails_a_loaded_session_claim(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path, scenario=PENDING_RELOAD)
    assert score(PENDING_RELOAD, workspace) == "fail"
    _drive(workspace, "switch")
    assert score(PENDING_RELOAD, workspace) == "fail"
    _insert_intent(
        workspace.home,
        "switch",
        outcome={
            "kind": "switch",
            "harness_id": "cursor",
            "project_root": str(workspace.project),
            "preserved_setup_id": "setup_held",
            "verified": True,
            "session_loaded": False,
            "process_killed": False,
        },
    )
    (workspace.root / "cli.log").write_text(
        "task start --intent switch --input switch-input.json --json\n"
        "task answer --task t --revision 3 --question-id reload-session --value done --json\n",
        encoding="utf-8",
    )
    assert score(PENDING_RELOAD, workspace) == "pass"
    (workspace.root / "agy.stdout").write_text(
        "The running process loaded the new files.\n", encoding="utf-8"
    )
    assert score(PENDING_RELOAD, workspace) == "fail"
    blocked = prepare_workspace(tmp_path / "pending-block", scenario=PENDING_RELOAD)
    _insert_intent(
        blocked.home,
        "switch",
        state="blocked",
        goal_satisfied=False,
        verified=False,
        questions=[{"question_id": "reload-session", "actor": "human"}],
        outcome={"kind": "switch", "session_loaded": False, "process_killed": False},
    )
    (blocked.root / "cli.log").write_text(
        "task start --intent switch --input switch-input.json --json\n",
        encoding="utf-8",
    )
    assert score(PENDING_RELOAD, blocked) == "pass"
    failed = prepare_workspace(tmp_path / "pending-failed", scenario=PENDING_RELOAD)
    _insert_intent(failed.home, "switch", state="failed", goal_satisfied=False, verified=False)
    (failed.root / "cli.log").write_text(
        "task start --intent switch --json\ntask continue --task t --revision 1 --json\n",
        encoding="utf-8",
    )
    assert score(PENDING_RELOAD, failed) == "fail"
    compensated = prepare_workspace(tmp_path / "compensated", scenario=COMPENSATED)
    assert score(COMPENSATED, compensated) == "not_run"
    (compensated.root / "fault.json").write_text(
        json.dumps({"aborted": "the barrier was never reached"}), encoding="utf-8"
    )
    assert score(COMPENSATED, compensated) == "not_run"
    _seed_fault(
        compensated,
        kind="compensated-install",
        state="failed",
        goal_satisfied=False,
        op_state="rolled_back",
        extra={
            "barrier": "provider-killed-mid-mutation",
            "diverged": ["skills/demo/SKILL.md"],
            "pre": {},
        },
    )
    assert score(COMPENSATED, compensated) == "pass"
    wedge = prepare_workspace(tmp_path / "compensated-wedge", scenario=COMPENSATED)
    _seed_fault(
        wedge,
        kind="compensated-install",
        state="failed",
        goal_satisfied=False,
        op_state="partial",
        extra={
            "barrier": "provider-killed-mid-mutation",
            "diverged": ["skills/demo/SKILL.md"],
            "pre": {},
        },
    )
    assert score(COMPENSATED, wedge) == "pass"
    running = prepare_workspace(tmp_path / "compensated-running", scenario=COMPENSATED)
    _seed_fault(
        running,
        kind="compensated-install",
        state="running",
        goal_satisfied=False,
        op_state="applying",
        extra={
            "barrier": "provider-killed-mid-mutation",
            "diverged": ["skills/demo/SKILL.md"],
            "pre": {},
        },
    )
    assert score(COMPENSATED, running) == "fail"
    killed = prepare_workspace(tmp_path / "killed", scenario=KILL_AFTER)
    assert score(KILL_AFTER, killed) == "not_run"
    _seed_fault(
        killed,
        kind="kill-after-apply",
        state="completed",
        goal_satisfied=True,
        op_state="verified",
        extra={"barrier": "applied_unverified"},
    )
    assert score(KILL_AFTER, killed) == "pass"
    wedge_kill = prepare_workspace(tmp_path / "killed-wedge", scenario=KILL_AFTER)
    _seed_fault(
        wedge_kill,
        kind="kill-after-apply",
        state="failed",
        goal_satisfied=False,
        op_state="partial",
        extra={"barrier": "applied_unverified"},
    )
    assert score(KILL_AFTER, wedge_kill) == "pass"
    abandoned = prepare_workspace(tmp_path / "killed-abandoned", scenario=KILL_AFTER)
    _seed_fault(
        abandoned,
        kind="kill-after-apply",
        state="running",
        goal_satisfied=False,
        op_state="applied_unverified",
        extra={"barrier": "applied_unverified"},
    )
    assert score(KILL_AFTER, abandoned) == "fail"
    doubled = prepare_workspace(tmp_path / "killed-doubled", scenario=KILL_AFTER)
    _seed_fault(
        doubled,
        kind="kill-after-apply",
        state="completed",
        goal_satisfied=True,
        op_state="verified",
        extra={"barrier": "applied_unverified"},
    )
    _seed_fault_op(doubled.home, operation_id="op_second", state="verified")
    assert score(KILL_AFTER, doubled) == "fail"
    idle = prepare_workspace(tmp_path / "idle", scenario=LOGIN_IDLE)
    assert score(LOGIN_IDLE, idle) == "fail"
    _drive(idle, "account")
    assert score(LOGIN_IDLE, idle) == "fail"
    _insert_intent(
        idle.home,
        "account",
        state="blocked",
        goal_satisfied=False,
        verified=False,
        questions=[{"question_id": "authorization", "actor": "external"}],
    )
    (idle.root / "cli.log").write_text(
        "task start --intent account --json\n"
        "task answer --task t --revision 1 --question-id action --value login --json\n",
        encoding="utf-8",
    )
    assert score(LOGIN_IDLE, idle) == "pass"
    failed_idle = prepare_workspace(tmp_path / "idle-failed", scenario=LOGIN_IDLE)
    _insert_intent(
        failed_idle.home,
        "account",
        state="failed",
        goal_satisfied=False,
        verified=False,
        questions=[{"question_id": "authorization", "actor": "external"}],
    )
    (failed_idle.root / "cli.log").write_text(
        "task start --intent account --json\n",
        encoding="utf-8",
    )
    assert score(LOGIN_IDLE, failed_idle) == "fail"
    concurrent = prepare_workspace(tmp_path / "concurrent", scenario=CONCURRENT)
    assert score(CONCURRENT, concurrent) == "not_run"
    _seed_fault(
        concurrent,
        kind="concurrent-continue",
        state="completed",
        goal_satisfied=True,
        op_state="verified",
        extra={"joiner": {"exit": 0, "stdout": "{}"}},
    )
    assert score(CONCURRENT, concurrent) == "pass"
    joined_cancel = prepare_workspace(tmp_path / "concurrent-cancel", scenario=CONCURRENT)
    _seed_fault(
        joined_cancel,
        kind="concurrent-continue",
        state="cancelled",
        goal_satisfied=False,
        op_state="verified",
        extra={"joiner": {"exit": 0, "stdout": "{}"}, "cancel": {"exit": 0}},
    )
    assert score(CONCURRENT, joined_cancel) == "pass"
    no_joiner = prepare_workspace(tmp_path / "concurrent-no-joiner", scenario=CONCURRENT)
    _seed_fault(
        no_joiner,
        kind="concurrent-continue",
        state="completed",
        goal_satisfied=True,
        op_state="verified",
    )
    assert score(CONCURRENT, no_joiner) == "fail"
    second_drain = prepare_workspace(tmp_path / "consecond", scenario=CONCURRENT)
    _seed_fault(
        second_drain,
        kind="concurrent-continue",
        state="completed",
        goal_satisfied=True,
        op_state="verified",
        extra={"joiner": {"exit": 0, "stdout": "{}"}},
    )
    _seed_fault_op(second_drain.home, operation_id="op_second", state="planned")
    assert score(CONCURRENT, second_drain) == "fail"
    second_task = prepare_workspace(tmp_path / "consecond-task", scenario=CONCURRENT)
    _seed_fault(
        second_task,
        kind="concurrent-continue",
        state="completed",
        goal_satisfied=True,
        op_state="verified",
        extra={"joiner": {"exit": 0, "stdout": "{}"}},
    )
    _seed_fault_task(
        second_task.home,
        task_id="task_extra",
        key="other-key",
        state="failed",
        goal_satisfied=False,
        children=(),
    )
    assert score(CONCURRENT, second_task) == "fail"


def _publish_outcome(**overrides: object) -> dict[str, object]:
    outcome: dict[str, object] = {
        "kind": "publish",
        "object_id": "component_demo",
        "object_version": "1.0",
        "visibility": "private",
        "source_binding_id": "",
        "plan_id": "plan_demo",
        "plan_hash": "hash_demo",
        "state": "published",
        "readable": True,
        "provenance": "filesystem",
    }
    outcome.update(overrides)
    return outcome


def _readback_stub(
    monkeypatch: pytest.MonkeyPatch,
    *,
    version_verdict: str = "verified",
    private_only: bool = False,
) -> None:
    """cell_cli fake: registry version/fetch envelopes keyed on --private."""

    def _cli(_workspace: Workspace, argv: Sequence[str]) -> dict[str, object]:
        args = list(argv)
        private = "--private" in args
        if args[:2] == ["registry", "version"]:
            if version_verdict == "absent" or (private_only and not private):
                return {"ok": False, "error": {"code": "AI_STP_NOT_FOUND"}, "_exit": 1}
            if version_verdict == "unavailable":
                return {"ok": False, "error": {"code": "AI_STP_AUTH_REQUIRED"}, "_exit": 1}
            return {
                "ok": True,
                "data": {
                    "source": "online",
                    "passport": {
                        "stable_id": args[args.index("--id") + 1],
                        "version": args[args.index("--version") + 1],
                        "artifact": {"digest": "sha256:demo"},
                    },
                },
                "_exit": 0,
            }
        if args[:2] == ["registry", "fetch"]:
            if private_only and not private:
                return {"ok": False, "error": {"code": "AI_STP_NOT_FOUND"}, "_exit": 1}
            return {
                "ok": True,
                "data": {"source": "online", "digest": "sha256:demo"},
                "_exit": 0,
            }
        return {"ok": False, "_exit": 2}

    monkeypatch.setattr("ai_stp_cli.agy_qualify.cell_cli", _cli)


def _capture(workspace: Workspace, *paths: str) -> None:
    lines = "".join(
        json.dumps({"method": "GET", "path": path, "body_size": 0}) + "\n" for path in paths
    )
    (workspace.root / "requests.jsonl").write_text(lines, encoding="utf-8")


def _drove_publish(workspace: Workspace) -> None:
    (workspace.root / "cli.log").write_text(
        "task start --intent publish --input publish-input.json --json\n",
        encoding="utf-8",
    )


def test_publish_score_requires_authorization_or_filesystem(tmp_path: Path) -> None:
    started = prepare_workspace(tmp_path / "pub-start", scenario=PUBLISH_PRIV)
    _drive(started, "publish")
    assert score(PUBLISH_PRIV, started) == "fail"
    workspace = prepare_workspace(tmp_path / "pub-score", scenario=PUBLISH_PRIV)
    _insert_intent(
        workspace.home,
        "publish",
        state="blocked",
        goal_satisfied=False,
        verified=False,
        questions=[{"question_id": "authorization", "actor": "external"}],
    )
    _drove_publish(workspace)
    # The auth boundary is its own scenario's pass. A positive cell that only
    # reached it produced no publication evidence: not_run, never pass.
    assert score(PUBLISH_PRIV, workspace) == "not_run"
    assert score(PUBLISH_PUB, workspace) == "not_run"
    assert score(AUTH_PUBLISH, workspace) == "pass"
    failed = prepare_workspace(tmp_path / "pub-failed", scenario=PUBLISH_PRIV)
    _insert_intent(
        failed.home,
        "publish",
        state="failed",
        goal_satisfied=False,
        verified=False,
        questions=[{"question_id": "authorization", "actor": "external"}],
    )
    (failed.root / "cli.log").write_text("task start --intent publish --json\n", encoding="utf-8")
    assert score(PUBLISH_PRIV, failed) == "fail"
    assert score(AUTH_PUBLISH, failed) == "fail"
    private = prepare_workspace(tmp_path / "pub-private", scenario=PUBLISH_PRIV)
    _insert_intent(
        private.home,
        "publish",
        outcome=_publish_outcome(state="validating", readable=False),
    )
    _drove_publish(private)
    # Completed-but-unreadable and still validating is a claim without the
    # outcome — a defect, not a pass and not missing infrastructure.
    assert score(PUBLISH_PRIV, private) == "fail"
    assert score(PUBLISH_PUB, private) == "fail"
    assert score(AUTH_PUBLISH, private) == "fail"
    public = prepare_workspace(tmp_path / "pub-public", scenario=PUBLISH_PUB)
    _insert_intent(
        public.home,
        "publish",
        outcome=_publish_outcome(visibility="public", state="validating", readable=False),
    )
    _drove_publish(public)
    assert score(PUBLISH_PUB, public) == "fail"
    assert score(PUBLISH_PRIV, public) == "fail"
    bound = prepare_workspace(tmp_path / "pub-git", scenario=PUBLISH_PRIV)
    _insert_intent(
        bound.home,
        "publish",
        outcome=_publish_outcome(source_binding_id="bind_git"),
    )
    (bound.root / "cli.log").write_text("task start --intent publish --json\n", encoding="utf-8")
    assert score(PUBLISH_PRIV, bound) == "fail"
    leaked = prepare_workspace(tmp_path / "pub-upload", scenario=AUTH_PUBLISH)
    _insert_intent(
        leaked.home,
        "publish",
        state="blocked",
        goal_satisfied=False,
        verified=False,
        questions=[{"question_id": "authorization", "actor": "external"}],
    )
    (leaked.root / "cli.log").write_text(
        "task start --intent publish --json\nlogin.poll --json\n", encoding="utf-8"
    )
    assert score(AUTH_PUBLISH, leaked) == "fail"


def test_publish_verified_requires_remote_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote_absent = prepare_workspace(tmp_path / "pub-absent", scenario=PUBLISH_PUB)
    _insert_intent(
        remote_absent.home,
        "publish",
        outcome=_publish_outcome(visibility="public"),
    )
    _drove_publish(remote_absent)
    _readback_stub(monkeypatch, version_verdict="absent")
    # The catalogue answered "no such object": the completed claim is refuted.
    assert score(PUBLISH_PUB, remote_absent) == "fail"

    unreachable = prepare_workspace(tmp_path / "pub-unreachable", scenario=PUBLISH_PUB)
    _insert_intent(
        unreachable.home,
        "publish",
        outcome=_publish_outcome(visibility="public"),
    )
    _drove_publish(unreachable)
    _readback_stub(monkeypatch, version_verdict="unavailable")
    assert score(PUBLISH_PUB, unreachable) == "not_run"

    verified = prepare_workspace(tmp_path / "pub-verified", scenario=PUBLISH_PUB)
    _insert_intent(
        verified.home,
        "publish",
        outcome=_publish_outcome(visibility="public"),
    )
    _drove_publish(verified)
    _readback_stub(monkeypatch)
    # Readback verified but the egress capture is absent: missing infrastructure.
    assert score(PUBLISH_PUB, verified) == "not_run"
    _capture(
        verified,
        "/v1/publications/plans",
        "/v1/publications/plans/plan_demo/confirm",
        "/v1/catalog/components/component_demo",
    )
    assert score(PUBLISH_PUB, verified) == "pass"
    _capture(verified, "/v1/sync-plans")
    assert score(PUBLISH_PUB, verified) == "fail"


def test_private_publish_fails_an_anonymous_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    leaked = prepare_workspace(tmp_path / "pub-leak", scenario=PUBLISH_PRIV)
    _insert_intent(
        leaked.home,
        "publish",
        outcome=_publish_outcome(),
    )
    _drove_publish(leaked)
    _capture(leaked, "/v1/catalog/components/component_demo")
    _readback_stub(monkeypatch)
    # Anonymous read sees the private object: the access policy failed open.
    assert score(PUBLISH_PRIV, leaked) == "fail"
    _readback_stub(monkeypatch, private_only=True)
    assert score(PUBLISH_PRIV, leaked) == "pass"


def test_auth_publish_boundary_still_scores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = prepare_workspace(tmp_path / "auth-done", scenario=AUTH_PUBLISH)
    _insert_intent(
        done.home,
        "publish",
        outcome=_publish_outcome(),
    )
    _drove_publish(done)
    _readback_stub(monkeypatch)
    assert score(AUTH_PUBLISH, done) == "pass"
    _readback_stub(monkeypatch, version_verdict="absent")
    assert score(AUTH_PUBLISH, done) == "fail"


def test_unrun_cells_skip_scored_pass_and_fail() -> None:
    agent = {
        f"{RELATIVE_ROOT}:0": "pass",
        f"{RELATIVE_ROOT}:1": "pass",
        f"{RELATIVE_ROOT}:2": "pass",
        f"{RELATIVE_ROOT}:3": "pass",
        f"{AUTHOR_DIR}:1": "fail",
    }
    pending = unrun_cells(agent)
    assert (RELATIVE_ROOT, 0) not in pending
    assert (RELATIVE_ROOT, 4) in pending
    assert (AUTHOR_DIR, 1) not in pending
    assert (AUTHOR_DIR, 0) in pending
    assert pending[0] == (AGENT_SCENARIOS[0], 0)


def test_fill_requires_root_and_measured() -> None:
    assert main(["--fill"]) == 2
    assert main(["--fill", "--root", "/tmp/qualify-fill"]) == 2


def test_fill_skips_a_capacity_miss_to_the_next_unrun_cell() -> None:
    pending = ((INSTALL_OPEN, 4), (CHANGE_ADD, 1), (SWITCH_SAVED, 1))
    skipped = {(INSTALL_OPEN, 4)}
    assert next_fill_cell(pending, skipped) == (CHANGE_ADD, 1)
    assert next_fill_cell(pending, set()) == (INSTALL_OPEN, 4)
    assert next_fill_cell((), set()) is None
    assert next_fill_cell(pending, set(pending)) == (INSTALL_OPEN, 4)
    assert next_fill_cell(pending, set(pending), rotate_from=(INSTALL_OPEN, 4)) == (
        CHANGE_ADD,
        1,
    )
    assert next_fill_cell(pending, set(pending), rotate_from=(SWITCH_SAVED, 1)) == (
        INSTALL_OPEN,
        4,
    )


def test_write_cell_refuses_an_unknown_scenario(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_cell(tmp_path / "measured.json", "not-a-scenario", 0, "pass")
    write_cell(tmp_path / "measured.json", NO_REINIT, 0, "pass")
    body = json.loads((tmp_path / "measured.json").read_text(encoding="utf-8"))
    assert body["agent"][f"{NO_REINIT}:0"] == "pass"
    assert NO_REINIT in AGENT_SCENARIOS
    write_cell(tmp_path / "measured.json", NO_REINIT, 3, "fail")
    clear_cell(tmp_path / "measured.json", NO_REINIT, 3)
    body = json.loads((tmp_path / "measured.json").read_text(encoding="utf-8"))
    assert body["agent"][f"{NO_REINIT}:3"] == "fail"
    assert body["agent"][f"{NO_REINIT}:0"] == "pass"


def test_write_cell_records_the_model_that_drove_it(tmp_path: Path) -> None:
    measured = tmp_path / "measured.json"
    write_cell(measured, NO_REINIT, 0, "pass")
    assert json.loads(measured.read_text(encoding="utf-8"))["agy_model"] == AGY_MODEL
    before = measured.read_bytes()
    with pytest.raises(ValueError, match="separate --measured"):
        write_cell(measured, NO_REINIT, 1, "pass", model="other-model")
    assert measured.read_bytes() == before
    write_cell(measured, NO_REINIT, 1, "pass")
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert body["agy_model"] == AGY_MODEL
    assert body["agent"][f"{NO_REINIT}:0"] == "pass"
    assert body["agent"][f"{NO_REINIT}:1"] == "pass"
    before = measured.read_bytes()
    write_cell(measured, NO_REINIT, 1, "pass")
    assert measured.read_bytes() == before


@pytest.mark.parametrize("fill", [False, True])
@pytest.mark.parametrize("invalidate", [False, True])
def test_model_mismatch_is_rejected_before_qualification_effects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fill: bool, invalidate: bool
) -> None:
    measured = tmp_path / "measured.json"
    write_cell(measured, NO_REINIT, 0, "pass", model="other-model")
    before = measured.read_bytes()
    root = tmp_path / "must-not-be-created"
    argv = ["--root", str(root), "--measured", str(measured), "--agy", "absent-driver"]
    if fill:
        argv.append("--fill")
    if invalidate:
        argv.extend(["--invalidate", NO_REINIT])
    assert main(argv) == 2
    assert "separate --measured" in capsys.readouterr().err
    assert not root.exists()
    assert measured.read_bytes() == before


def test_unattributed_cells_cannot_acquire_a_model_label(tmp_path: Path) -> None:
    measured = tmp_path / "measured.json"
    measured.write_text(json.dumps({"agent": {f"{NO_REINIT}:0": "pass"}}), encoding="utf-8")
    before = measured.read_bytes()
    with pytest.raises(ValueError, match="unknown model"):
        write_cell(measured, NO_REINIT, 1, "pass")
    assert measured.read_bytes() == before
    write_isolation(measured, {"status": "enforced"})
    assert "agy_model" not in json.loads(measured.read_text(encoding="utf-8"))


def test_historical_haiku_overlay_cannot_be_extended_as_agent_evidence(
    tmp_path: Path,
) -> None:
    measured = tmp_path / "historical.json"
    measured.write_text(
        json.dumps({"agy_model": AGY_MODEL, "haiku": {f"{NO_REINIT}:0": "pass"}}),
        encoding="utf-8",
    )
    before = measured.read_bytes()
    with pytest.raises(ValueError, match="new --measured path"):
        write_cell(measured, NO_REINIT, 1, "pass")
    for arguments in (
        ["--invalidate", NO_REINIT],
        ["--native-cell", "cursor:linux-x86_64"],
        ["--record-isolation"],
    ):
        assert main(["--measured", str(measured), *arguments]) == 2
    assert measured.read_bytes() == before


def test_native_probes_and_invalidation_preserve_model_attribution(tmp_path: Path) -> None:
    measured = tmp_path / "measured.json"
    for run in range(3):
        write_cell(measured, NO_REINIT, run, "pass", model="other-model")
    write_isolation(measured, {"status": "enforced"})
    write_native_cell(measured, "cursor", "linux-x86_64", "pass")
    clear_cell(measured, NO_REINIT, 4)
    assert invalidate_cell(measured, NO_REINIT, 1) == 1
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert body["agy_model"] == "other-model"
    assert body["agent"] == {f"{NO_REINIT}:0": "pass", f"{NO_REINIT}:2": "pass"}
    assert invalidate_scenario(measured, NO_REINIT) == 2
    assert json.loads(measured.read_text(encoding="utf-8"))["agy_model"] == "other-model"


@pytest.mark.parametrize("run", [-1, AGENT_RUNS])
def test_write_cell_refuses_out_of_matrix_runs(tmp_path: Path, run: int) -> None:
    measured = tmp_path / "measured.json"
    with pytest.raises(ValueError):
        write_cell(measured, NO_REINIT, run, "pass")
    assert not measured.exists()


def test_unavailable_markers_cover_model_limits() -> None:
    assert run_was_unavailable("", '{"error": {"type": "overloaded_error"}}')
    assert run_was_unavailable("API Error: rate_limit_error", "")
    assert run_was_unavailable("", "RESOURCE_EXHAUSTED (code 429): Individual quota reached")
    assert not run_was_unavailable("", "a plain failure")


def test_invalidate_drops_scored_cells_so_fill_can_rerun(tmp_path: Path) -> None:
    measured = tmp_path / "measured.json"
    write_cell(measured, INSTALL_OPEN, 0, "pass")
    write_cell(measured, INSTALL_OPEN, 1, "fail")
    write_cell(measured, NO_REINIT, 0, "pass")
    assert invalidate_scenario(measured, INSTALL_OPEN) == 2
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert f"{INSTALL_OPEN}:0" not in body["agent"]
    assert f"{INSTALL_OPEN}:1" not in body["agent"]
    assert body["agent"][f"{NO_REINIT}:0"] == "pass"
    pending = unrun_cells(body["agent"])
    assert (INSTALL_OPEN, 0) in pending
    assert (NO_REINIT, 0) not in pending
    write_cell(measured, INSTALL_OPEN, 0, "fail")
    write_cell(measured, INSTALL_OPEN, 1, "pass")
    assert invalidate_cell(measured, INSTALL_OPEN, 0) == 1
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert f"{INSTALL_OPEN}:0" not in body["agent"]
    assert body["agent"][f"{INSTALL_OPEN}:1"] == "pass"
    assert invalidate_target(f"{INSTALL_OPEN}:0") == (INSTALL_OPEN, 0)
    assert invalidate_target(INSTALL_OPEN) == (INSTALL_OPEN, None)
    with pytest.raises(ValueError):
        invalidate_target("not-a-scenario")
    with pytest.raises(ValueError):
        invalidate_target(f"{INSTALL_OPEN}:9")
    write_cell(measured, INSTALL_OPEN, 0, "fail")
    assert main(["--invalidate", f"{INSTALL_OPEN}:0", "--measured", str(measured)]) == 0
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert f"{INSTALL_OPEN}:0" not in body["agent"]
    assert body["agent"][f"{INSTALL_OPEN}:1"] == "pass"
    write_cell(measured, INSTALL_PIN, 0, "pass")
    assert main(["--invalidate-stale-verified"]) == 2
    assert STALE_VERIFIED_SCENARIOS == (
        FRESH_INIT,
        ANTIGRAVITY,
        INSTALL_PIN,
        INSTALL_OPEN,
        CHANGE_ADD,
        SWITCH_SAVED,
        CUSTOM_HOME,
        RELATIVE_ROOT,
        AUTHOR_DIR,
        LOGIN_IDLE,
    )
    assert main(["--invalidate-stale-verified", "--measured", str(measured)]) == 0
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert f"{INSTALL_PIN}:0" not in body["agent"]
    assert body["agent"][f"{NO_REINIT}:0"] == "pass"


def test_switch_workspace_does_not_seed_without_docker(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path, scenario=SWITCH_SAVED)
    assert not (workspace.root / "seed-install.json").is_file()
    pending = prepare_workspace(tmp_path / "pending", scenario=PENDING_RELOAD)
    assert not (pending.root / "seed-install.json").is_file()
    changed = prepare_workspace(tmp_path / "change", scenario=CHANGE_ADD)
    assert (changed.project / "demo-skill" / "SKILL.md").is_file()
    assert not (changed.root / "seed-component.txt").is_file()
    assert extra_cursor_ref() in prompt_for(CHANGE_ADD, changed)


def test_seeded_change_prompt_uses_input_file(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path, scenario=CHANGE_ADD)
    pin = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV@1.0"
    (workspace.root / "seed-component.txt").write_text(pin, encoding="utf-8")
    text = prompt_for(CHANGE_ADD, workspace)
    assert "--input change-input.json" in text
    assert pin in text
    assert INPUT_CWD_HINT in text
    assert "Absolute project root:" not in text
    assert "Answer component-ref" not in text
    body = json.loads((workspace.project / "change-input.json").read_text(encoding="utf-8"))
    assert body["component_id"] == "component_01ARZ3NDEKTSV4RRFFQ69G5FAV"
    assert body["component_version"] == "1.0"
    assert body["harness_id"] == "cursor"


def test_write_native_cell_refuses_unknown_keys_and_keeps_agent(tmp_path: Path) -> None:
    measured = tmp_path / "measured.json"
    write_cell(measured, NO_REINIT, 0, "pass")
    with pytest.raises(ValueError):
        write_native_cell(measured, "cursor", "sparc", "pass")
    code = main(
        [
            "--native-cell",
            "cursor:linux-x86_64",
            "--native-status",
            "pass",
            "--measured",
            str(measured),
        ]
    )
    assert code == 0
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert body["native"]["cursor:linux-x86_64"] == "pass"
    assert body["agent"][f"{NO_REINIT}:0"] == "pass"
    assert main(["--native-cell", "cursor:sparc", "--measured", str(measured)]) == 2


def test_drive_native_install_rejects_short_key_and_scores_verified_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "home" / ".cursor"
    (marker / "rules").mkdir(parents=True)
    (marker / "rules" / "nddev-baseline.mdc").write_text("alwaysApply: true\n", encoding="utf-8")

    def _root(harness: str, environment: object = None) -> Path:
        assert harness == "cursor"
        return marker

    def _cli(argv: list[str]) -> dict[str, object]:
        assert argv[0] == "task"
        return {
            "ok": True,
            "_exit": 0,
            "continuations": [],
            "data": {
                "state": "completed",
                "goal_satisfied": True,
                "outcome": {"verified": True, "setup_id": "setup_01TEST"},
            },
        }

    monkeypatch.setattr("ai_stp_cli.agy_qualify.native_config_root", _root)
    monkeypatch.setattr("ai_stp_cli.agy_qualify.native_platform", lambda: "linux-x86_64")
    monkeypatch.setattr("ai_stp_cli.agy_qualify.run_cli_json", _cli)
    input_path = tmp_path / "input.json"
    input_path.write_text(
        json.dumps(
            {
                "harness_id": "cursor",
                "setup_id": "setup_01TEST",
                "setup_version": "1.4",
                "project_root": str(tmp_path / "project"),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="idempotency key"):
        drive_native_install(input_path, "native-codex-01")
    report = drive_native_install(input_path, "native-linux-cursor-01")
    assert native_install_passed(report)
    digest = report["tree_digest"]
    assert isinstance(digest, str)
    assert digest.startswith("sha256:")
    measured = tmp_path / "measured.json"
    write_cell(measured, NO_REINIT, 0, "pass")
    assert (
        main(
            [
                "--native-drive",
                str(input_path),
                "--idempotency-key",
                "native-linux-cursor-01",
                "--measured",
                str(measured),
            ]
        )
        == 0
    )
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert body["native"]["cursor:linux-x86_64"] == "pass"
    assert body["agent"][f"{NO_REINIT}:0"] == "pass"
    assert main(["--native-drive", str(input_path)]) == 2


def test_record_isolation_does_not_fill_native(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "ai_stp_cli.agy_qualify.isolation_snapshot",
        lambda: {
            "status": "unavailable",
            "os_name": "linux",
            "evidence": ["bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted"],
        },
    )
    measured = tmp_path / "measured.json"
    write_cell(measured, NO_REINIT, 0, "pass")
    assert main(["--record-isolation", "--measured", str(measured)]) == 1
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert body["isolation"]["status"] == "unavailable"
    assert "native" not in body
    assert body["agent"][f"{NO_REINIT}:0"] == "pass"
    write_isolation(
        measured,
        {
            "status": "enforced",
            "os_name": "linux",
            "launcher_id": "bwrap",
            "evidence": ["unshare-net"],
        },
    )
    assert json.loads(measured.read_text(encoding="utf-8"))["isolation"]["status"] == "enforced"
    assert main(["--record-isolation"]) == 2


def test_isolation_snapshot_maps_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_stp_cli.agy_qualify import isolation_snapshot
    from ai_stp_cli.provider.protocol_v2 import NetworkCapability, NetworkEnforcement

    monkeypatch.setattr(
        "ai_stp_cli.provider.network_launcher.discover_launcher",
        lambda: (
            None,
            NetworkCapability(
                enforcement=NetworkEnforcement.UNAVAILABLE,
                os_name="linux",
                launcher_id=None,
                evidence=("RTM_NEWADDR",),
            ),
        ),
    )
    unavailable = isolation_snapshot()
    assert unavailable == {
        "status": "unavailable",
        "os_name": "linux",
        "evidence": ["RTM_NEWADDR"],
    }
    monkeypatch.setattr(
        "ai_stp_cli.provider.network_launcher.discover_launcher",
        lambda: (
            None,
            NetworkCapability(
                enforcement=NetworkEnforcement.ENFORCED,
                os_name="linux",
                launcher_id="bwrap",
                evidence=("unshare-net",),
            ),
        ),
    )
    enforced = isolation_snapshot()
    assert enforced["status"] == "enforced"
    assert enforced["launcher_id"] == "bwrap"


def test_run_agy_does_not_retry_an_empty_log_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.agy_qualify import run_agy

    workspace = prepare_workspace(tmp_path)
    calls = {"n": 0}

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls["n"] += 1
        return subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="UNAVAILABLE (code 503): No capacity available",
        )

    def _sleep(_seconds: float) -> None:
        raise AssertionError("empty-log 503 must not sleep")

    monkeypatch.setattr("ai_stp_cli.agy_qualify.subprocess.run", fake_run)
    monkeypatch.setattr("ai_stp_cli.agy_qualify.time", SimpleNamespace(sleep=_sleep))
    assert run_agy(workspace, agy=Path("/bin/agy"), timeout=5) == 1
    assert calls["n"] == 1


def test_start_only_503_retries_until_follow_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.agy_qualify import run_agy

    workspace = prepare_workspace(tmp_path, scenario=INSTALL_OPEN)
    busy = "UNAVAILABLE (code 503): No capacity available"
    (workspace.root / "cli.log").write_text(
        "task start --intent install --json\n", encoding="utf-8"
    )
    assert incomplete_capacity_hit(workspace, "", busy)
    calls = {"n": 0}

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls["n"] += 1
        if calls["n"] == 1:
            (workspace.root / "cli.log").write_text(
                "task start --intent install --json\n", encoding="utf-8"
            )
            return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=busy)
        (workspace.root / "cli.log").write_text(
            "task start --intent install --json\ntask continue --task t --revision 1 --json\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"status":"SUCCESS"}', stderr=""
        )

    def _sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("ai_stp_cli.agy_qualify.subprocess.run", fake_run)
    monkeypatch.setattr("ai_stp_cli.agy_qualify.time", SimpleNamespace(sleep=_sleep))
    assert run_agy(workspace, agy=Path("/bin/agy"), timeout=5) == 0
    assert calls["n"] == 2
    (workspace.root / "cli.log").write_text("install plan --json\n", encoding="utf-8")
    assert not incomplete_capacity_hit(workspace, "", busy)


def test_recover_task_intents_then_503_is_already_complete(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path, scenario=RECOVER)
    (workspace.root / "cli.log").write_text("task intents --json\n", encoding="utf-8")
    busy = "UNAVAILABLE (code 503): No capacity available"
    assert not incomplete_capacity_hit(workspace, "", busy, RECOVER)
    assert score(RECOVER, workspace) == "pass"
    inspect_only = prepare_workspace(tmp_path / "inspect-only", scenario=RECOVER)
    _insert_intent(inspect_only.home, "inspect")
    (inspect_only.root / "cli.log").write_text(
        "task start --intent inspect --json\n", encoding="utf-8"
    )
    assert score(RECOVER, inspect_only) == "fail"
    (inspect_only.root / "cli.log").write_text("task intents --json\n", encoding="utf-8")
    assert score(RECOVER, inspect_only) == "pass"


def test_capacity_miss_is_unavailable_not_a_scenario_fail() -> None:
    stdout = (
        '{"status":"ERROR","error":"Our servers are experiencing high traffic '
        "right now (UNAVAILABLE (code 503): No capacity available for model "
        'gpt-oss-120b-medium on the server)"}'
    )
    assert run_was_unavailable(stdout, "")
    assert not run_was_unavailable('{"status":"SUCCESS"}', "")


@pytest.mark.skipif(os.name == "nt", reason="the agy stub is a POSIX shell script")
def test_fill_pauses_on_individual_quota_without_scoring(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stub = tmp_path / "agy"
    stub.write_text(
        "#!/bin/sh\n"
        "echo 'Individual quota reached. Resets in 1h.'\n"
        "echo 'RESOURCE_EXHAUSTED (code 429): Individual quota reached' >&2\n"
        "exit 3\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    measured = tmp_path / "measured.json"
    cells = tmp_path / "cells"
    assert (
        main(
            [
                "--root",
                str(cells),
                "--measured",
                str(measured),
                "--agy",
                str(stub),
                "--fill",
                "--max-attempts",
                "3",
                "--gap-seconds",
                "0",
            ]
        )
        == 1
    )
    assert not measured.exists()
    assert len(list(cells.iterdir())) == 1
    output = capsys.readouterr().out
    assert '"status": "not_run"' in output
    assert '"reason": "quota_exhausted"' in output


def test_background_killed_install_stays_unrun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    measured = tmp_path / "measured.json"
    killed = (
        "root agent idle; waiting up to 5s for 1 background task(s)\n"
        "terminating 1 background task(s) on exit\n"
    )
    assert run_was_background_killed(killed)
    assert not run_was_background_killed("")

    def fake_run_agy(workspace: Workspace, **_kwargs: object) -> int:
        (workspace.root / "cli.log").write_text(
            "task start --intent install --idempotency-key install-session-01 --json\n",
            encoding="utf-8",
        )
        (workspace.root / "agy.stdout").write_text(
            '{"status":"SUCCESS","response":"(Waiting for the `ai-stp` command to finish…)"}\n',
            encoding="utf-8",
        )
        (workspace.root / "agy.stderr").write_text(killed, encoding="utf-8")
        return 0

    monkeypatch.setattr("ai_stp_cli.agy_qualify.run_agy", fake_run_agy)
    code = qualify_one(
        root=tmp_path / "cell",
        scenario=INSTALL_OPEN,
        run=0,
        measured=measured,
        agy=Path("/bin/agy"),
        timeout=5,
        probe=False,
    )
    assert code == 1
    assert not measured.is_file() or f"{INSTALL_OPEN}:0" not in json.loads(
        measured.read_text(encoding="utf-8")
    ).get("agent", {})
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert report["status"] == "not_run"
    assert report["reason"] == "backgrounded"


def test_capacity_probe_miss_skips_qualify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = {"n": 0}

    def _run(*_args: object, **_kwargs: object) -> int:
        calls["n"] += 1
        raise AssertionError("qualify must not run after a probe miss")

    monkeypatch.setattr("ai_stp_cli.agy_qualify.capacity_probe", lambda *_a, **_k: False)
    monkeypatch.setattr("ai_stp_cli.agy_qualify.run_agy", _run)
    code = main(
        [
            "--root",
            str(tmp_path / "ws"),
            "--scenario",
            NO_REINIT,
            "--run",
            "0",
            "--probe",
        ]
    )
    assert code == 1
    assert calls["n"] == 0
    held = json.loads(capsys.readouterr().out)
    assert held["status"] == "not_run"
    assert held["reason"] == "unavailable"


def test_503_after_cli_use_is_scored_not_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = prepare_workspace(tmp_path / "empty")
    busy = '{"status":"ERROR","error":"UNAVAILABLE (code 503): No capacity available"}'
    assert capacity_miss(busy, "", empty)
    used = prepare_workspace(tmp_path / "used", scenario=INSTALL_OPEN)
    (used.root / "cli.log").write_text("install plan --json\n", encoding="utf-8")
    assert not capacity_miss(busy, "", used)
    measured = tmp_path / "measured.json"
    write_cell(measured, INSTALL_OPEN, 0, "pass")

    def _run(workspace: Workspace, **_kwargs: object) -> int:
        root = workspace.root
        (root / "cli.log").write_text("install plan --json\n", encoding="utf-8")
        (root / "agy.stdout").write_text(busy, encoding="utf-8")
        (root / "agy.stderr").write_text("", encoding="utf-8")
        return 1

    monkeypatch.setattr("ai_stp_cli.agy_qualify.run_agy", _run)
    code = main(
        [
            "--root",
            str(tmp_path / "cell"),
            "--scenario",
            INSTALL_OPEN,
            "--run",
            "0",
            "--measured",
            str(measured),
            "--timeout",
            "5",
        ]
    )
    assert code == 1
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert body["agent"][f"{INSTALL_OPEN}:0"] == "fail"


def test_start_only_503_does_not_erase_a_prior_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    busy = '{"status":"ERROR","error":"UNAVAILABLE (code 503): No capacity available"}'
    measured = tmp_path / "measured.json"
    write_cell(measured, SWITCH_SAVED, 0, "fail")

    def _run(workspace: Workspace, **_kwargs: object) -> int:
        (workspace.root / "cli.log").write_text(
            "task start --intent switch --json\n", encoding="utf-8"
        )
        (workspace.root / "agy.stdout").write_text(busy, encoding="utf-8")
        (workspace.root / "agy.stderr").write_text("", encoding="utf-8")
        return 1

    monkeypatch.setattr("ai_stp_cli.agy_qualify.run_agy", _run)
    code = main(
        [
            "--root",
            str(tmp_path / "cell"),
            "--scenario",
            SWITCH_SAVED,
            "--run",
            "0",
            "--measured",
            str(measured),
            "--timeout",
            "5",
        ]
    )
    assert code == 1
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert body["agent"][f"{SWITCH_SAVED}:0"] == "fail"


@pytest.mark.skipif(os.name == "nt", reason="the agy stub is a POSIX shell script")
def test_unavailable_agy_keeps_a_prior_fail_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = tmp_path / "agy"
    stub.write_text(
        "#!/bin/sh\necho 'UNAVAILABLE (code 503): No capacity available' >&2\nexit 1\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    measured = tmp_path / "measured.json"
    write_cell(measured, NO_REINIT, 3, "fail")

    sleeps = {"n": 0}

    def _sleep(_seconds: float) -> None:
        sleeps["n"] += 1

    monkeypatch.setattr("ai_stp_cli.agy_qualify.time", SimpleNamespace(sleep=_sleep))
    code = main(
        [
            "--root",
            str(tmp_path / "ws"),
            "--scenario",
            NO_REINIT,
            "--run",
            "3",
            "--measured",
            str(measured),
            "--agy",
            str(stub),
            "--timeout",
            "5",
        ]
    )
    assert code == 1
    assert sleeps["n"] == 0
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert body["agent"][f"{NO_REINIT}:3"] == "fail"


def test_start_only_503_without_a_prior_cell_stays_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    busy = '{"status":"ERROR","error":"UNAVAILABLE (code 503): No capacity available"}'
    measured = tmp_path / "measured.json"

    def _run(workspace: Workspace, **_kwargs: object) -> int:
        (workspace.root / "cli.log").write_text(
            "task start --intent switch --json\n", encoding="utf-8"
        )
        (workspace.root / "agy.stdout").write_text(busy, encoding="utf-8")
        (workspace.root / "agy.stderr").write_text("", encoding="utf-8")
        return 1

    monkeypatch.setattr("ai_stp_cli.agy_qualify.run_agy", _run)
    code = main(
        [
            "--root",
            str(tmp_path / "cell"),
            "--scenario",
            SWITCH_SAVED,
            "--run",
            "1",
            "--measured",
            str(measured),
            "--timeout",
            "5",
        ]
    )
    assert code == 1
    if measured.is_file():
        body = json.loads(measured.read_text(encoding="utf-8"))
        assert f"{SWITCH_SAVED}:1" not in body.get("agent", {})
    else:
        assert not measured.exists()


def test_agy_argv_puts_print_equals_last() -> None:
    argv = agy_argv(Path("/bin/agy"))
    assert argv[0] == str(Path("/bin/agy"))
    assert argv[1:3] == ["--output-format", "json"]
    assert "--mode" in argv
    assert argv[argv.index("--mode") + 1] == "accept-edits"
    assert argv[-1].startswith("--print=")
    assert "--print" not in argv[:-1]
    probe = agy_argv(Path("/bin/agy"), prompt="pong", print_timeout="20s")
    assert probe[probe.index("--print-timeout") + 1] == "20s"
    added = agy_argv(
        Path("/bin/agy"),
        add_dirs=(Path("/tmp/qualify-root"), Path("/tmp/qualify-root/project")),
    )
    assert added[-1].startswith("--print=")
    assert added[added.index("--add-dir") + 1] == str(Path("/tmp/qualify-root").resolve())
    assert added.count("--add-dir") == 2
    assert "Use your shell tool" in SKILL_TAIL
    assert "printed command is not a completed initialize" in SKILL_TAIL
    assert "Do not invent task status, task info, or task get" in SKILL_TAIL
    assert "Do not type component add" in SKILL_TAIL
    assert "Do not insert task continue when actor is human" in SKILL_TAIL
    assert "absolute path outside this workspace" in SKILL_TAIL
    assert "The shell cwd is already the project. Do not cd." in SKILL_TAIL
    assert "An absolute path inside --input JSON is for the CLI" in SKILL_TAIL
    assert "do not background it" in SKILL_TAIL
    assert "Do not type project passport" in SKILL_TAIL
    assert "Do not type provider network" in SKILL_TAIL
    assert "Do not run task answer without --value" in SKILL_TAIL
    assert "If error.details.state is failed, stop" in SKILL_TAIL
    assert "actor=human does not mean wait" in SKILL_TAIL
    assert FOLLOW_ACTOR.startswith("If continuations is empty")
    assert "do not wait for a person" in FOLLOW_ACTOR
    assert "If actor is cli, execute argv" in FOLLOW_ACTOR
    assert "If actor is external, show the payload once and stop" in FOLLOW_ACTOR
    assert "provider-too-old is not login" in FOLLOW_ACTOR
    assert "provider-too-old is not login" in SKILL_TAIL


def test_agy_qualify_module_is_not_imported_by_qualify() -> None:
    source = Path("apps/cli/src/ai_stp_cli/application/qualify.py").read_text(encoding="utf-8")
    assert "agy_qualify" not in source
    assert "subprocess" not in source
    assert "network_launcher" not in source


@pytest.mark.skipif(os.name == "nt", reason="the qualify wrapper is a POSIX shell script")
def test_author_input_mints_a_setup(tmp_path: Path) -> None:
    workspace = prepare_workspace(tmp_path / "author-live", scenario=AUTHOR_DIR)
    prompt_for(AUTHOR_DIR, workspace)
    started = subprocess.run(
        [
            str(workspace.wrapper),
            "task",
            "start",
            "--intent",
            "author",
            "--idempotency-key",
            "author-session-01",
            "--input",
            "author-input.json",
            "--json",
        ],
        cwd=workspace.project,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert started.returncode == 0, started.stderr + started.stdout
    envelope = json.loads(started.stdout)
    assert envelope.get("ok") is True, started.stdout
    data = envelope.get("data") or {}
    assert data.get("state") == "completed"
    outcome = data.get("outcome") or {}
    assert outcome.get("minted") is True
    assert outcome.get("name") == "demo"
    assert outcome.get("setup_id")
    assert outcome.get("component_id")
    assert score(AUTHOR_DIR, workspace) == "pass"


def test_docker_custom_home_score_is_the_codex_write(tmp_path: Path) -> None:
    """Bound debug codex under Docker ENFORCED. Does not tag or overwrite 0.0.72."""
    if debug_provider("codex-setup-system") is None:
        pytest.skip("debug codex-setup-system is not on this machine")
    image = os.environ.get("AI_STP_QUALIFY_DOCKER_IMAGE", "ai-stp-iso:local")
    held = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image],
        capture_output=True,
        check=False,
    )
    if held.returncode != 0:
        pytest.skip("privileged image ai-stp-iso:local is not on this machine")
    workspace = prepare_workspace(
        tmp_path / "custom-docker", scenario=CUSTOM_HOME, docker_image=image
    )
    prompt_for(CUSTOM_HOME, workspace)
    seed_log = (workspace.root / "seed-provider-codex.log").read_text(encoding="utf-8")
    assert seed_log.startswith("exit=0"), seed_log
    started = subprocess.run(
        [
            str(workspace.wrapper),
            "task",
            "start",
            "--intent",
            "initialize",
            "--idempotency-key",
            "initialize-session-01",
            "--input",
            "initialize-input.json",
            "--json",
        ],
        cwd=workspace.project,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert started.returncode == 0, started.stderr + started.stdout
    envelope = json.loads(started.stdout)
    assert envelope.get("ok") is True, started.stdout
    data = envelope.get("data") or {}
    assert data.get("state") == "completed"
    outcome = data.get("outcome") or {}
    assert outcome.get("wrote") is True
    assert outcome.get("harness_id") == "codex"
    assert custom_home_section_landed(workspace)
    assert score(CUSTOM_HOME, workspace) == "pass"
