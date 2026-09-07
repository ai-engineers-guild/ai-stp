"""Exact prerequisites remain observable without implicit environment effects."""

import json
import os
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
from tests.unit.test_cli_install_commands import _confirmed  # pyright: ignore[reportPrivateUsage]

from ai_stp_cli.commands import environment
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import project_passport, selection
from ai_stp_cli.local.database import configured_path, open_registry


def _prepared(root: Path) -> dict[str, object]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        proposal = _confirmed(
            connection,
            root,
            "9",
            requires_authorization="user_account",
            required_env=("ENVIRONMENT_TEST_ACCESS",),
        )
        held = selection.held(connection, proposal)
        assert held is not None
        project = project_passport.stable_id_for(connection, root)
        assert project is not None
        return {
            "setup": f"{held.confirmed_stable_id}@{held.confirmed_version}",
            "project": project,
            "target": str(root),
        }


def test_preparation_exposes_access_and_concrete_program_action_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parameters = _prepared(tmp_path)
    prefix = tmp_path / "managed-harness"
    parameters["harness-prefix"] = [f"claude-code={prefix}"]
    monkeypatch.setenv("ENVIRONMENT_TEST_ACCESS", "private-value-never-printed")
    before = configured_path().read_bytes()
    observed = environment.inspect(parameters).payload
    assert not prefix.exists()
    assert configured_path().read_bytes() == before
    assert not observed.prerequisites_satisfied
    assert observed.configuration_state == "not_observed"
    variable = next(row for row in observed.requirements if row.kind == "environment_variable")
    assert variable.state == "satisfied"
    assert any(source.startswith("component_") for source in variable.sources)
    auth = next(row for row in observed.requirements if row.kind == "authorization")
    assert auth.state == "not_observed"
    program = next(row for row in observed.requirements if row.kind == "harness_program")
    assert program.state == "action_required"
    assert str(prefix) in program.actions[0]
    assert "private-value-never-printed" not in observed.model_dump_json()


def test_fresh_process_inspection_keeps_missing_prerequisites_visible(tmp_path: Path) -> None:
    parameters = _prepared(tmp_path)
    before = configured_path().read_bytes()
    argv = [sys.executable, "-m", "ai_stp_cli", "environment", "inspect"]
    for name, value in parameters.items():
        argv.extend([f"--{name}", str(value)])
    process_env = dict(os.environ)
    process_env.pop("ENVIRONMENT_TEST_ACCESS", None)
    result = subprocess.run(
        [*argv, "--json"], capture_output=True, text=True, check=False, env=process_env
    )
    assert result.returncode == 0, result.stderr + result.stdout
    answer = json.loads(result.stdout)["data"]
    assert answer["configuration_state"] == "not_observed"
    assert any(
        row["kind"] == "environment_variable" and row["state"] == "action_required"
        for row in answer["requirements"]
    )
    assert configured_path().read_bytes() == before


def test_inspection_refuses_a_changed_exact_component(tmp_path: Path) -> None:
    parameters = _prepared(tmp_path)
    with closing(open_registry(configured_path())) as connection:
        connection.execute(
            "UPDATE object_version SET passport_digest = ? WHERE stable_id LIKE 'component_%'",
            ("sha256:" + "a" * 64,),
        )
        connection.commit()
    with pytest.raises(CliFailure, match="changed identity"):
        environment.inspect(parameters)


def test_unpinned_tool_and_offline_missing_artifact_stay_blocked(tmp_path: Path) -> None:
    from ai_stp_cli import toolchain

    parameters = _prepared(tmp_path)
    manifest = toolchain.load()
    tool = next(item for item in manifest.tools if toolchain.current_platform() in item.artifacts)
    parameters.update({"tool": [tool.tool_id, "not-in-the-profile"], "offline": True})
    rows = [
        row
        for row in environment.inspect(parameters).payload.requirements
        if row.kind == "toolchain_tool"
    ]
    assert len(rows) == 2
    assert all(row.state == "blocked" and not row.actions for row in rows)
    assert next(row for row in rows if row.identity == tool.tool_id).version == tool.version
