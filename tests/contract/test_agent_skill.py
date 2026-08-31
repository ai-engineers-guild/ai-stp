"""The canonical Agent Skill and its projections (issue #77).

The acceptance criterion with teeth: the Skill must name only commands the CLI
actually exposes. A Skill that mentions a command the registry does not declare
teaches an agent to plan a step that cannot run — the same failure `#72` avoided
by refusing to declare unimplemented commands in the first place.
"""

import re
import shlex
from pathlib import Path

import pytest
from docs_scripts import skill_projections

from ai_stp_cli.registry import COMMANDS, GLOBAL_OPTIONS, Command

ROOT = Path(__file__).parents[2]
CANONICAL = ROOT / "skills" / "canonical" / "ai-stp" / "SKILL.md"

#: Every `ai-stp ...` invocation written in a document.
INVOCATION = re.compile(r"`(ai-stp [^`\n]+)`")


def _known_paths() -> set[str]:
    return {command.name for command in COMMANDS}


def _invocations(text: str) -> list[list[str]]:
    return [shlex.split(raw) for raw in INVOCATION.findall(text)]


def _command_for(tokens: list[str]) -> Command:
    command_tokens = tokens[1:]
    matches = [
        command
        for command in COMMANDS
        if command_tokens[: len(command.descriptor.path)] == command.descriptor.path
    ]
    assert matches, " ".join(tokens)
    return max(matches, key=lambda command: len(command.descriptor.path))


def test_the_canonical_skill_names_only_commands_that_exist() -> None:
    for invocation in _invocations(CANONICAL.read_text(encoding="utf-8")):
        _command_for(invocation)


def test_the_canonical_skill_starts_from_doctor_and_machine_help() -> None:
    # `#77` fixes the opening move: look at the installation, then read the
    # registry. Anything else would be the Skill guessing.
    text = CANONICAL.read_text(encoding="utf-8")
    beginning = text.split("## Start here", 1)[1].split("##", 1)[0]
    assert "ai-stp doctor --json" in beginning
    assert "ai-stp help --agent --json" in beginning
    assert beginning.index("doctor") < beginning.index("help --agent")


def test_every_example_uses_only_flags_declared_for_its_command() -> None:
    # Examples are valuable only while mechanically tied to the registry. The
    # Skill may teach a workflow, but a renamed or removed flag must fail this
    # test in the same patch rather than reaching an installed agent as drift.
    text = CANONICAL.read_text(encoding="utf-8")
    global_flags = {f"--{option.name}" for option in GLOBAL_OPTIONS}
    for invocation in _invocations(text):
        command = _command_for(invocation)
        allowed = global_flags | {
            f"--{parameter.name}" for parameter in command.descriptor.parameters
        }
        for token in invocation:
            if token.startswith("--"):
                assert token.split("=", 1)[0] in allowed, " ".join(invocation)


def test_the_skill_carries_no_stale_capability_snapshot() -> None:
    # Capability availability belongs to machine help. A negative list is just
    # as capable of drifting as a copied command list: once the implementation
    # lands it teaches every installed agent that a real command is absent.
    text = CANONICAL.read_text(encoding="utf-8")
    assert "## Missing capabilities" not in text
    assert "not implemented yet" not in text
    boundary = text.split("## Availability boundary", 1)[1]
    assert "machine help" in boundary
    assert "target directly" in boundary


def test_the_skill_uses_machine_error_dispositions_instead_of_exit_class_guesses() -> None:
    text = CANONICAL.read_text(encoding="utf-8")
    response = text.split("## Reading responses", 1)[1].split("##", 1)[0]
    assert "error_codes" in response
    assert "handling" in response
    assert "retryable: true" in response
    assert "unconfirmed timeout" in response
    assert "`2` —" not in response
    assert "Class `4`" not in response


def test_the_skill_distinguishes_effect_from_machine_confirmation() -> None:
    text = CANONICAL.read_text(encoding="utf-8")
    policy = text.split("## Making decisions", 1)[1].split("##", 1)[0]

    for value in ("read", "plan", "apply", "destructive"):
        assert f"`{value}`" in policy
    for value in ("confirmation: none", "explicit_flag", "plan_digest"):
        assert f"`{value}`" in policy
    assert "imply user consent" in policy
    assert "not calculate the digest yourself" in policy
    assert "without a new question" in policy
    assert "A separate user decision is required only" in policy
    assert "hint" in policy and "permission" in policy


@pytest.mark.parametrize(
    "projection", skill_projections.TARGETS, ids=lambda item: str(item.harness_id)
)
def test_every_projection_is_generated_and_current(
    projection: skill_projections.Projection,
) -> None:
    target = skill_projections.PROJECTIONS / projection.directory / projection.filename
    assert target.exists()
    assert target.read_text(encoding="utf-8") == skill_projections.render(projection)


def test_every_supported_harness_has_one_projection() -> None:
    # `SPEC-011` REQ-1105: one canonical Skill produces verifiable native
    # projections for every supported harness.
    from ai_stp_foundation.harnesses import HARNESS_IDS

    assert {projection.harness_id for projection in skill_projections.TARGETS} == set(HARNESS_IDS)


def test_a_projection_copies_no_command_and_no_procedure() -> None:
    # One canonical procedure is not copied by hand
    # (`docs/agent/harness-projections.md`). A projection that carried the
    # command list would be the stale copy the criterion forbids.
    known = _known_paths()
    for projection in skill_projections.TARGETS:
        text = (
            skill_projections.PROJECTIONS / projection.directory / projection.filename
        ).read_text(encoding="utf-8")
        for invocation in _invocations(text):
            command = _command_for(invocation)
            assert command.name in known, (projection.harness_id, invocation)
        assert "## Rules" not in text


def test_the_generator_reports_no_drift_and_no_orphan() -> None:
    assert skill_projections.check() == []


def test_the_generator_is_idempotent() -> None:
    before = {
        path: path.read_text(encoding="utf-8")
        for path in skill_projections.PROJECTIONS.rglob("SKILL.md")
    }
    skill_projections.write()
    after = {
        path: path.read_text(encoding="utf-8")
        for path in skill_projections.PROJECTIONS.rglob("SKILL.md")
    }
    assert before == after
    assert skill_projections.main([]) == 0
    assert skill_projections.main(["--check"]) == 0
