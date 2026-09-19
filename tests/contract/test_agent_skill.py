"""The canonical Agent Skill and its projections (issue #77).

The acceptance criterion with teeth: the Skill must name only commands the CLI
actually exposes. A Skill that mentions a command the registry does not declare
teaches an agent to plan a step that cannot run — the same failure `#72` avoided
by refusing to declare unimplemented commands in the first place.
"""

import re
import shlex
import shutil
from pathlib import Path

import pytest
from docs_scripts import skill_projections

from ai_stp_cli.registry import COMMANDS, GLOBAL_OPTIONS, Command

ROOT = Path(__file__).parents[2]
CANONICAL = ROOT / "skills" / "canonical" / "ai-stp" / "SKILL.md"
PACKAGE = CANONICAL.parent

#: Every `ai-stp ...` invocation written in a document.
INVOCATION = re.compile(r"`(ai-stp [^`\n]+)`")
BOOTSTRAP_FLAGS = frozenset({"--json"})


def _package_markdown() -> list[Path]:
    return sorted(
        path for path in PACKAGE.rglob("*.md") if path.is_file() and "evals" not in path.parts
    )


@pytest.mark.parametrize("projection", skill_projections.TARGETS, ids=lambda item: item.harness_id)
def test_repository_projection_is_a_self_contained_skill_package(
    projection: skill_projections.Projection, tmp_path: Path
) -> None:
    delivered = tmp_path / "ai-stp"
    shutil.copytree(skill_projections.PROJECTIONS / projection.directory, delivered)
    for document in delivered.rglob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            destination = (document.parent / target.split("#", 1)[0]).resolve()
            assert destination.is_relative_to(delivered), (document, target)
            assert destination.is_file(), (document, target)


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


def test_bootstrap_asks_which_project_directories_to_index() -> None:
    text = (PACKAGE / "references" / "bootstrap.md").read_text(encoding="utf-8")
    assert "project discover" in text
    assert "project index" in text
    assert "component inventory" in text
    assert "component adopt" in text
    assert "home directory" in text
    assert "already named" in text
    assert "Do not ask again" in text


def test_the_canonical_skill_starts_from_task_intents() -> None:
    # Durable journeys start at compact discovery, not a 203-command dump.
    text = CANONICAL.read_text(encoding="utf-8")
    beginning = text.split("## Start here", 1)[1].split("##", 1)[0]
    assert "ai-stp task intents --json" in beginning
    assert "yourself" in beginning
    assert "JSON field" in beginning
    assert "printed command is not a completed operation" in beginning
    assert "Start already advanced the task" in beginning
    assert "Do not invent `task status`" in beginning
    assert "do not background it" in beginning
    assert "already signed in" in beginning
    assert "ai-stp doctor --json" not in beginning
    assert "help --agent" not in beginning
    assert len(text.splitlines()) <= 500
    assert "203" not in text


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
            if command.descriptor.path == ["task", "intents"]:
                assert set(flags) <= BOOTSTRAP_FLAGS | allowed
                continue
            assert flags == [], " ".join(invocation)


FLAG_TOKEN = re.compile(r"(?<![\w`])--[a-z][a-z0-9-]*")


def test_skill_text_names_no_flags_except_the_bootstrap_pair() -> None:
    for path in _package_markdown():
        text = path.read_text(encoding="utf-8")
        flags = FLAG_TOKEN.findall(text)
        extra = [flag for flag in flags if flag not in BOOTSTRAP_FLAGS]
        assert extra == [], f"{path}: {extra}"
        if "--json" in flags:
            assert "task intents --json" in text, path


def test_install_playbook_does_not_type_the_install_group() -> None:
    text = (PACKAGE / "references" / "install.md").read_text(encoding="utf-8")
    assert "Do not type the install group with no leaf" in text


def test_onboard_does_not_prelude_doctor() -> None:
    text = (PACKAGE / "references" / "onboard.md").read_text(encoding="utf-8")
    assert "before mutating" not in text
    assert "as a prelude" in text
    assert "initialize" in text
    assert "provider-too-old" in text
    assert "start `account`" in text


def test_account_playbook_is_not_every_external_block() -> None:
    text = (PACKAGE / "references" / "account.md").read_text(encoding="utf-8")
    assert "provider-too-old" in text
    assert "Do not open this playbook for" in text
    assert "device-code" in text or "user_code" in text
    assert "Do not type `sync push`" in text
    assert "Do not type `project passport`" in text
    assert "Do not type `project revision push`" in text
    assert "already signed in" in text
    assert "do not type `ai-stp`" in text
    assert "Do not call `task continue` in that turn" in text


def test_traps_do_not_teach_adopt_as_the_id_path() -> None:
    text = (PACKAGE / "references" / "traps.md").read_text(encoding="utf-8")
    assert "author" in text
    assert "Do not type `component adopt`" in text
    assert "provider-too-old" in text


def test_catalog_playbook_does_not_type_registry_show() -> None:
    text = (PACKAGE / "references" / "catalog.md").read_text(encoding="utf-8")
    assert "Do not type `registry show`" in text
    assert "`registry fetch`" in text
    assert "install" in text


def test_author_playbook_does_not_type_setup_publish() -> None:
    text = (PACKAGE / "references" / "author.md").read_text(encoding="utf-8")
    assert "`setup publish plan`" in text
    assert "`setup publish confirm`" in text
    assert "`component materialize plan`" in text
    assert "publish" in text
    assert "github" in text and ".com" in text
    assert "do not invent git" in text.lower()


def test_environment_playbook_does_not_type_environment_plan() -> None:
    text = (PACKAGE / "references" / "environment.md").read_text(encoding="utf-8")
    assert "Do not type" in text
    assert "`environment plan`" in text
    assert "`environment inspect`" in text
    assert "install" in text


def test_compose_playbook_does_not_type_recast_plan() -> None:
    text = (PACKAGE / "references" / "compose.md").read_text(encoding="utf-8")
    assert "Do not type `setup recast plan`" in text
    assert "change" in text


def test_self_update_playbook_does_not_type_update_plan() -> None:
    text = (PACKAGE / "references" / "self-update.md").read_text(encoding="utf-8")
    assert "Do not type `update plan` or `update apply`" in text
    assert "`ai-stp update check`" in text


def test_provider_playbook_does_not_type_provider_update_plan() -> None:
    text = (PACKAGE / "references" / "provider.md").read_text(encoding="utf-8")
    assert "do not type `ai-stp provider update plan`" in text.lower()
    assert "do not type `ai-stp harness install`" in text.lower()
    assert "`ai-stp harness update`" in text


def test_bootstrap_does_not_send_install_through_adopt() -> None:
    text = (PACKAGE / "references" / "bootstrap.md").read_text(encoding="utf-8")
    assert "Do not type `ai-stp component adopt`" in text
    assert "Do not type `ai-stp capabilities`" in text
    assert "author" in text


def test_inspect_playbook_does_not_type_version() -> None:
    text = (PACKAGE / "references" / "inspect.md").read_text(encoding="utf-8")
    assert "Do not type `ai-stp capabilities` or `ai-stp version`" in text


def test_recover_continues_the_open_task_before_expert_leaves() -> None:
    text = (PACKAGE / "references" / "recover.md").read_text(encoding="utf-8")
    assert "Do not start a second `install` intent" in text
    assert "install recover" in text
    assert "Do not type `setup preserve recover`" in text
    assert "Do not dump the full registry" in text
    assert "Do not type `ai-stp help`" in text
    assert "Do not type `ai-stp capabilities`" in text


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
    assert "Do not type `provider network`" in rules
    assert "Do not type `sync push`" in rules or "`sync push`" in rules
    assert "`setup publish plan`" in rules


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
    assert "run the named plan command" not in text
    assert "do not type `install plan`" in text.lower()


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
        assert "ai-stp task intents --json" in text
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
