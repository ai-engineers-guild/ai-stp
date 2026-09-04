"""Physical setup authoring trees (SPEC-041 REQ-4112 / REQ-4113)."""

from pathlib import Path

import pytest

from ai_stp_cli.commands import setup_scaffold as setup_scaffold_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import setup_scaffold


def test_setup_scaffold_requires_a_concrete_harness(tmp_path: Path) -> None:
    with pytest.raises(CliFailure, match="concrete harness"):
        setup_scaffold.setup_scaffold_plan(
            name="review-pack",
            harness="portable",
            output=tmp_path / "review-pack",
        )


def test_setup_scaffold_rejects_a_member_the_harness_cannot_route(tmp_path: Path) -> None:
    with pytest.raises(CliFailure, match="without losing semantics"):
        setup_scaffold.setup_scaffold_plan(
            name="review-pack",
            harness="grok-build",
            output=tmp_path / "review-pack",
            components="command:run-tests",
        )


def test_setup_scaffold_nests_members_without_a_nested_git(tmp_path: Path) -> None:
    parameters = {
        "name": "review-pack",
        "harness": "codex",
        "output": str(tmp_path / "review-pack"),
        "components": "skill:review-kit,instruction:conventions",
    }
    plan = setup_scaffold_commands.plan(parameters).payload
    assert plan.descriptor.template_version == "setup-scaffold/2"
    assert plan.descriptor.harness_id == "codex"
    assert {member.name for member in plan.descriptor.members} == {"review-kit", "conventions"}
    assert any(item.path == "setup.json" for item in plan.files)
    assert any(item.path.startswith("components/review-kit/source/") for item in plan.files)
    assert any(
        item.path.startswith("components/conventions/projections/codex/") for item in plan.files
    )
    assert not any(item.path.startswith(".git/") for item in plan.files)

    result = setup_scaffold_commands.apply(
        {**parameters, "expected-plan-digest": plan.plan_digest}
    ).payload
    output = Path(result.output)
    assert result.files_written == len(plan.files)
    assert (output / "setup.json").is_file()
    assert (output / "components" / "review-kit" / "source" / "SKILL.md").is_file()
    assert not (output / "components" / "review-kit" / ".git").exists()
    assert (output / "projections" / "README.md").is_file()
    if result.git_initialized:
        assert (output / ".git").is_dir()
        if result.git_commit is None:
            assert result.git_reason in {"missing_identity", "git_unavailable"}
        else:
            assert result.git_reason is None
    else:
        assert result.git_reason in {"existing_worktree", "git_unavailable"}
        assert not (output / ".git").exists()
