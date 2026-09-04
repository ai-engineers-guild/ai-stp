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
PACKAGE = CANONICAL.parent

#: Every `ai-stp ...` invocation written in a document.
INVOCATION = re.compile(r"`(ai-stp [^`\n]+)`")
BOOTSTRAP_FLAGS = frozenset({"--json", "--agent"})


def _package_markdown() -> list[Path]:
    return sorted(
        path for path in PACKAGE.rglob("*.md") if path.is_file() and "evals" not in path.parts
    )


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
    for path in _package_markdown():
        for invocation in _invocations(path.read_text(encoding="utf-8")):
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
    # Only the bootstrap pair may name flags; every other invocation is a path.
    global_flags = {f"--{option.name}" for option in GLOBAL_OPTIONS}
    for path in _package_markdown():
        for invocation in _invocations(path.read_text(encoding="utf-8")):
            command = _command_for(invocation)
            allowed = global_flags | {
                f"--{parameter.name}" for parameter in command.descriptor.parameters
            }
            flags = [token.split("=", 1)[0] for token in invocation if token.startswith("--")]
            if command.descriptor.path == ["doctor"] or command.descriptor.path == ["help"]:
                assert set(flags) <= BOOTSTRAP_FLAGS | allowed
                continue
            assert flags == [], " ".join(invocation)


def test_the_skill_carries_no_stale_capability_snapshot() -> None:
    # Capability availability belongs to machine help. A negative list is just
    # as capable of drifting as a copied command list: once the implementation
    # lands it teaches every installed agent that a real command is absent.
    for path in _package_markdown():
        text = path.read_text(encoding="utf-8")
        assert "## Missing capabilities" not in text
        assert "not implemented yet" not in text
    rules = CANONICAL.read_text(encoding="utf-8").split("## Hard rules", 1)[1]
    assert "machine help" in rules.lower() or "Machine help" in rules
    assert "harness target" in rules


def test_the_skill_uses_machine_error_dispositions_instead_of_exit_class_guesses() -> None:
    response = (PACKAGE / "references" / "envelope.md").read_text(encoding="utf-8")
    assert "error_codes" in response
    assert "handling" in response
    assert "retryable: true" in response
    assert "unconfirmed timeout" in response
    assert "`2` —" not in response
    assert "Class `4`" not in response


def test_the_skill_distinguishes_effect_from_machine_confirmation() -> None:
    text = (PACKAGE / "references" / "decisions.md").read_text(encoding="utf-8")
    policy = text.split("# Decisions", 1)[1]

    for value in ("read", "plan", "apply", "destructive"):
        assert f"`{value}`" in policy
    for value in ("confirmation: none", "explicit_flag", "plan_digest"):
        assert f"`{value}`" in policy
    assert "is not consent" in policy
    assert "Do not compute" in policy
    assert "mechanical, not questions" in policy
    assert "separate user decision" in policy


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


def test_a_projection_carries_the_procedure_without_a_repository_pointer() -> None:
    known = _known_paths()
    for projection in skill_projections.TARGETS:
        text = (
            skill_projections.PROJECTIONS / projection.directory / projection.filename
        ).read_text(encoding="utf-8")
        for invocation in _invocations(text):
            command = _command_for(invocation)
            assert command.name in known, (projection.harness_id, invocation)
        assert "## Hard rules" in text
        assert "ai-stp doctor --json" in text
        assert "skills/canonical/" not in text


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


def test_the_skill_description_names_use_when_and_not_when() -> None:
    description = CANONICAL.read_text(encoding="utf-8").split("---", 2)[1]
    assert "prepare a harness" in description
    assert "Do NOT use" in description
    assert "1." not in description


def test_the_router_names_every_playbook_file() -> None:
    text = CANONICAL.read_text(encoding="utf-8")
    router = text.split("## Router", 1)[1].split("## Hard rules", 1)[0]
    for name in skill_projections.REFERENCE_NAMES:
        stem = name.removesuffix(".md")
        if stem in {"envelope", "decisions", "traps"}:
            continue
        assert stem in router, stem
        assert (PACKAGE / "references" / name).is_file()


def test_russian_locale_keeps_english_command_invocations() -> None:
    english: set[str] = set()
    russian: set[str] = set()
    for path in (PACKAGE / "references").glob("*.md"):
        english.update(INVOCATION.findall(path.read_text(encoding="utf-8")))
        russian.update(
            INVOCATION.findall(
                (PACKAGE / "locale" / "ru" / "references" / path.name).read_text(encoding="utf-8")
            )
        )
    assert english <= russian
