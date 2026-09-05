"""A standalone executable CLI is not a native slash command (A13)."""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import authoring
from ai_stp_cli.local.evaluation import reference_profile
from ai_stp_cli.registry import DECLARATIONS
from ai_stp_contracts.authoring import (
    AUTHORING_TYPE_LANGUAGE_MATRIX,
    DECLARATIVE_COMPONENT_TYPES,
)
from ai_stp_passports.versions import ComponentType


def test_closed_vocabulary_includes_cli_as_a_ninth_kind() -> None:
    kinds = get_args(ComponentType.__value__)
    assert "cli" in kinds
    assert "command" in kinds
    assert "marketplace" not in kinds
    assert kinds.count("cli") == 1
    assert len(kinds) == 9


def test_cli_is_executable_and_command_stays_declarative() -> None:
    assert "command" in DECLARATIVE_COMPONENT_TYPES
    assert "cli" not in DECLARATIVE_COMPONENT_TYPES
    assert AUTHORING_TYPE_LANGUAGE_MATRIX["command"] == ("none",)
    assert "none" not in AUTHORING_TYPE_LANGUAGE_MATRIX["cli"]
    assert "python" in AUTHORING_TYPE_LANGUAGE_MATRIX["cli"]


def test_portable_cli_scaffold_is_a_process_entry_point_not_a_slash_command(
    tmp_path: Path,
) -> None:
    plan, files = authoring.scaffold_plan(
        component_type="cli",
        name="review-kit",
        language="python",
        harness_variant="portable",
        output=tmp_path / "review-kit",
    )

    assert plan.descriptor.component_type == "cli"
    assert plan.descriptor.executable is True
    assert plan.descriptor.language == "python"
    assert plan.descriptor.harness_variant == "portable"
    assert any(path.startswith("source/") and path.endswith(".py") for path in files)
    assert not any("commands/" in path for path in files)
    assert not any(path.endswith(".md") and "command" in path.lower() for path in files)
    program = next(payload for path, payload in files.items() if path.startswith("source/"))
    assert b"def main" in program or b"fn main" in program


def test_cli_refuses_declarative_none_and_a_concrete_harness_copy(tmp_path: Path) -> None:
    with pytest.raises(CliFailure, match="language"):
        authoring.scaffold_plan(
            component_type="cli",
            name="review-kit",
            language="none",
            harness_variant="portable",
            output=tmp_path / "none-cli",
        )
    with pytest.raises(CliFailure, match="shared executable"):
        authoring.scaffold_plan(
            component_type="cli",
            name="review-kit",
            language="python",
            harness_variant="claude-code",
            output=tmp_path / "copied-cli",
        )


def test_command_scaffold_is_still_a_named_slash_invocation(tmp_path: Path) -> None:
    plan, files = authoring.scaffold_plan(
        component_type="command",
        name="review-kit",
        language="none",
        harness_variant="portable",
        output=tmp_path / "review-cmd",
    )

    assert plan.descriptor.component_type == "command"
    assert plan.descriptor.executable is False
    assert any(path.endswith("review-kit.md") for path in files)
    assert not any(path.endswith(".py") for path in files)


def test_scaffold_type_choices_include_cli() -> None:
    found: list[tuple[str, ...]] = []
    for declaration in DECLARATIONS:
        if tuple(declaration.path) in {
            ("component", "scaffold", "plan"),
            ("component", "scaffold", "apply"),
        }:
            for parameter in declaration.parameters:
                if parameter.name == "type":
                    found.append(tuple(parameter.choices))
    assert found, "scaffold type option is missing"
    assert all("cli" in choices and "command" in choices for choices in found)


def test_evaluation_profile_covers_cli() -> None:
    profile = reference_profile(("cli",))
    assert profile.component_types == ["cli"]
    assert any(check.check_id.startswith("cli.") for check in profile.checks)
