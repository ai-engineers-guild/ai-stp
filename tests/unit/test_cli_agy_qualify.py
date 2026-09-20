# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false
"""Isolated agy qualify workspace and scoring. Live model runs stay in agy_qualify.main."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
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
    UNMET_SETUP_ID,
    UNMET_SETUP_VERSION,
    VERIFIED_DRAIN,
    Workspace,
    agy_argv,
    bundled_cli,
    capacity_miss,
    choreographed,
    clear_cell,
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
    unrun_cells,
    write_cell,
    write_isolation,
    write_native_cell,
)
from ai_stp_cli.application.qualify import HAIKU_SCENARIOS
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
    assert frozenset(HAIKU_SCENARIOS) == SUPPORTED_SCENARIOS
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
    assert "--input install-input.json" in prompt_for(COMPENSATED, workspace)
    assert INPUT_CWD_HINT in prompt_for(COMPENSATED, workspace)
    assert "Absolute project root:" not in prompt_for(COMPENSATED, workspace)
    assert "Never type task get" in prompt_for(COMPENSATED, workspace)
    assert "absent from the catalog" in prompt_for(COMPENSATED, workspace)
    compensated_input = json.loads((workspace.project / "install-input.json").read_text())
    assert compensated_input["setup_id"] == UNMET_SETUP_ID
    assert compensated_input["setup_version"] == UNMET_SETUP_VERSION
    assert "Never type task get" in prompt_for(KILL_AFTER, workspace)
    assert "--input install-input.json" in prompt_for(KILL_AFTER, workspace)
    assert "absent from the catalog" in prompt_for(KILL_AFTER, workspace)
    kill_input = json.loads((workspace.project / "install-input.json").read_text())
    assert kill_input["setup_id"] == UNMET_SETUP_ID
    assert "Never type task get" in prompt_for(RECOVER, workspace)
    assert "task intents --json" in prompt_for(RECOVER, workspace)
    assert "Harness: cursor" in prompt_for(CONCURRENT, workspace)
    assert "--input install-input.json" in prompt_for(CONCURRENT, workspace)
    assert "Absolute project root:" not in prompt_for(CONCURRENT, workspace)
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


def test_every_haiku_scenario_has_a_prompt_and_score(tmp_path: Path) -> None:
    for scenario in HAIKU_SCENARIOS:
        workspace = prepare_workspace(tmp_path / scenario, scenario=scenario)
        assert prompt_for(scenario, workspace)
        assert score(scenario, workspace) in {"pass", "fail"}


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
    assert score(COMPENSATED, compensated) == "fail"
    _insert_intent(compensated.home, "install")
    assert score(COMPENSATED, compensated) == "fail"
    _drive(compensated, "install")
    assert score(COMPENSATED, compensated) == "fail"
    unmet = prepare_workspace(tmp_path / "compensated-unmet", scenario=COMPENSATED)
    _insert_intent(unmet.home, "install", state="failed", goal_satisfied=False, verified=False)
    (unmet.root / "cli.log").write_text(
        "task start --intent install --input install-input.json --json\n",
        encoding="utf-8",
    )
    assert score(COMPENSATED, unmet) == "pass"
    killed = prepare_workspace(tmp_path / "killed", scenario=KILL_AFTER)
    (killed.root / "cli.log").write_text("task continue --task t --json\n", encoding="utf-8")
    assert score(KILL_AFTER, killed) == "fail"
    _insert_intent(killed.home, "install", state="running", goal_satisfied=False, verified=False)
    assert score(KILL_AFTER, killed) == "pass"
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
    _insert_intent(concurrent.home, "install")
    (concurrent.root / "cli.log").write_text(
        "task start --intent install --json\n", encoding="utf-8"
    )
    assert score(CONCURRENT, concurrent) == "fail"
    (concurrent.root / "cli.log").write_text(
        "task start --intent install --json\ntask continue --task t --revision 1 --json\n",
        encoding="utf-8",
    )
    assert score(CONCURRENT, concurrent) == "fail"
    _insert_intent(concurrent.home, "install", state="failed", goal_satisfied=False, verified=False)
    assert score(CONCURRENT, concurrent) == "fail"
    only_failed = prepare_workspace(tmp_path / "concurrent-failed", scenario=CONCURRENT)
    _insert_intent(
        only_failed.home, "install", state="failed", goal_satisfied=False, verified=False
    )
    (only_failed.root / "cli.log").write_text(
        "task start --intent install --input install-input.json --json\n",
        encoding="utf-8",
    )
    assert score(CONCURRENT, only_failed) == "pass"


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
    (workspace.root / "cli.log").write_text(
        "task start --intent publish --input publish-input.json --json\n",
        encoding="utf-8",
    )
    assert score(PUBLISH_PRIV, workspace) == "pass"
    assert score(PUBLISH_PUB, workspace) == "pass"
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
    private = prepare_workspace(tmp_path / "pub-private", scenario=PUBLISH_PRIV)
    _insert_intent(
        private.home,
        "publish",
        outcome={
            "kind": "publish",
            "object_id": "component_demo",
            "object_version": "1.0",
            "visibility": "private",
            "source_binding_id": "",
            "plan_id": "plan_demo",
            "plan_hash": "hash_demo",
            "state": "validating",
            "readable": False,
            "provenance": "filesystem",
        },
    )
    (private.root / "cli.log").write_text(
        "task start --intent publish --input publish-input.json --json\n",
        encoding="utf-8",
    )
    assert score(PUBLISH_PRIV, private) == "pass"
    assert score(PUBLISH_PUB, private) == "fail"
    assert score(AUTH_PUBLISH, private) == "pass"
    public = prepare_workspace(tmp_path / "pub-public", scenario=PUBLISH_PUB)
    _insert_intent(
        public.home,
        "publish",
        outcome={
            "kind": "publish",
            "object_id": "component_demo",
            "object_version": "1.0",
            "visibility": "public",
            "source_binding_id": "",
            "plan_id": "plan_demo",
            "plan_hash": "hash_demo",
            "state": "validating",
            "readable": False,
            "provenance": "filesystem",
        },
    )
    (public.root / "cli.log").write_text(
        "task start --intent publish --input publish-input.json --json\n",
        encoding="utf-8",
    )
    assert score(PUBLISH_PUB, public) == "pass"
    assert score(PUBLISH_PRIV, public) == "fail"
    bound = prepare_workspace(tmp_path / "pub-git", scenario=PUBLISH_PRIV)
    _insert_intent(
        bound.home,
        "publish",
        outcome={
            "kind": "publish",
            "object_id": "component_demo",
            "object_version": "1.0",
            "visibility": "private",
            "source_binding_id": "bind_git",
            "plan_id": "plan_demo",
            "plan_hash": "hash_demo",
            "state": "validating",
            "readable": False,
            "provenance": "filesystem",
        },
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


def test_unrun_cells_skip_scored_pass_and_fail() -> None:
    haiku = {
        f"{RELATIVE_ROOT}:0": "pass",
        f"{RELATIVE_ROOT}:1": "pass",
        f"{RELATIVE_ROOT}:2": "pass",
        f"{RELATIVE_ROOT}:3": "pass",
        f"{AUTHOR_DIR}:1": "fail",
    }
    pending = unrun_cells(haiku)
    assert (RELATIVE_ROOT, 0) not in pending
    assert (RELATIVE_ROOT, 4) in pending
    assert (AUTHOR_DIR, 1) not in pending
    assert (AUTHOR_DIR, 0) in pending
    assert pending[0] == (HAIKU_SCENARIOS[0], 0)


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
    assert body["haiku"][f"{NO_REINIT}:0"] == "pass"
    assert NO_REINIT in HAIKU_SCENARIOS
    write_cell(tmp_path / "measured.json", NO_REINIT, 3, "fail")
    clear_cell(tmp_path / "measured.json", NO_REINIT, 3)
    body = json.loads((tmp_path / "measured.json").read_text(encoding="utf-8"))
    assert body["haiku"][f"{NO_REINIT}:3"] == "fail"
    assert body["haiku"][f"{NO_REINIT}:0"] == "pass"


def test_invalidate_drops_scored_cells_so_fill_can_rerun(tmp_path: Path) -> None:
    measured = tmp_path / "measured.json"
    write_cell(measured, INSTALL_OPEN, 0, "pass")
    write_cell(measured, INSTALL_OPEN, 1, "fail")
    write_cell(measured, NO_REINIT, 0, "pass")
    assert invalidate_scenario(measured, INSTALL_OPEN) == 2
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert f"{INSTALL_OPEN}:0" not in body["haiku"]
    assert f"{INSTALL_OPEN}:1" not in body["haiku"]
    assert body["haiku"][f"{NO_REINIT}:0"] == "pass"
    pending = unrun_cells(body["haiku"])
    assert (INSTALL_OPEN, 0) in pending
    assert (NO_REINIT, 0) not in pending
    write_cell(measured, INSTALL_OPEN, 0, "fail")
    write_cell(measured, INSTALL_OPEN, 1, "pass")
    assert invalidate_cell(measured, INSTALL_OPEN, 0) == 1
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert f"{INSTALL_OPEN}:0" not in body["haiku"]
    assert body["haiku"][f"{INSTALL_OPEN}:1"] == "pass"
    assert invalidate_target(f"{INSTALL_OPEN}:0") == (INSTALL_OPEN, 0)
    assert invalidate_target(INSTALL_OPEN) == (INSTALL_OPEN, None)
    with pytest.raises(ValueError):
        invalidate_target("not-a-scenario")
    with pytest.raises(ValueError):
        invalidate_target(f"{INSTALL_OPEN}:9")
    write_cell(measured, INSTALL_OPEN, 0, "fail")
    assert main(["--invalidate", f"{INSTALL_OPEN}:0", "--measured", str(measured)]) == 0
    body = json.loads(measured.read_text(encoding="utf-8"))
    assert f"{INSTALL_OPEN}:0" not in body["haiku"]
    assert body["haiku"][f"{INSTALL_OPEN}:1"] == "pass"
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
    assert f"{INSTALL_PIN}:0" not in body["haiku"]
    assert body["haiku"][f"{NO_REINIT}:0"] == "pass"


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


def test_write_native_cell_refuses_unknown_keys_and_keeps_haiku(tmp_path: Path) -> None:
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
    assert body["haiku"][f"{NO_REINIT}:0"] == "pass"
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
    assert body["haiku"][f"{NO_REINIT}:0"] == "pass"
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
    assert body["haiku"][f"{NO_REINIT}:0"] == "pass"
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
    ).get("haiku", {})
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
    assert body["haiku"][f"{INSTALL_OPEN}:0"] == "fail"


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
    assert body["haiku"][f"{SWITCH_SAVED}:0"] == "fail"


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
    assert body["haiku"][f"{NO_REINIT}:3"] == "fail"


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
        assert f"{SWITCH_SAVED}:1" not in body.get("haiku", {})
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
    seed_log = (workspace.root / "seed-provider.log").read_text(encoding="utf-8")
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
