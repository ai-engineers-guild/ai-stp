"""Delivering the Agent Skill: shipped, owned, and never taking over a file."""

from pathlib import Path

import pytest

from ai_stp_cli import skill
from ai_stp_cli.commands import skill as skill_commands
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local.skill_package import validate


def test_every_declared_harness_has_a_projection_in_the_package() -> None:
    canonical = skill.available(None)
    assert "ai-stp doctor --json" in canonical
    assert "skills/canonical/" not in canonical
    for harness in skill.HARNESSES:
        text = skill.available(harness)
        assert harness in text
        assert "ai-stp doctor --json" in text
        assert "skills/canonical/" not in text
        assert text != canonical
        files = skill.package_files(harness)
        assert "references/bootstrap.md" in files
        assert b"ai-stp help --agent --json" in files["references/bootstrap.md"]


def test_a_harness_with_no_projection_is_named_rather_than_guessed() -> None:
    with pytest.raises(CliFailure, match="no projection is shipped") as raised:
        skill.available("emacs")
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_installing_is_idempotent_and_owned(tmp_path: Path) -> None:
    assert skill.inspect(tmp_path).state == "absent"

    first = skill.install(tmp_path, "claude-code")
    assert first.state == "owned"
    assert first.harness == "claude-code"
    assert first.locale == "en"
    assert "references/install.md" in first.files
    written = (tmp_path / skill.SKILL_FILENAME).read_bytes()
    assert (tmp_path / "references" / "bootstrap.md").is_file()

    again = skill.install(tmp_path, "claude-code")
    assert again.digest == first.digest
    assert (tmp_path / skill.SKILL_FILENAME).read_bytes() == written


def test_a_skill_this_installation_did_not_write_is_never_replaced(tmp_path: Path) -> None:
    # A harness configuration someone wrote by hand is theirs.
    (tmp_path / skill.SKILL_FILENAME).write_text("hand written", encoding="utf-8")
    assert skill.inspect(tmp_path).state == "foreign"

    with pytest.raises(CliFailure, match="does not own") as raised:
        skill.install(tmp_path, None)
    assert raised.value.code == "AI_STP_CONFLICT"
    assert (tmp_path / skill.SKILL_FILENAME).read_text(encoding="utf-8") == "hand written"

    with pytest.raises(CliFailure, match="not installed by this installation"):
        skill.remove(tmp_path)
    assert (tmp_path / skill.SKILL_FILENAME).exists()


def test_an_edited_installation_is_reported_rather_than_overwritten(tmp_path: Path) -> None:
    skill.install(tmp_path, None)
    (tmp_path / skill.SKILL_FILENAME).write_text("edited since", encoding="utf-8")

    assert skill.inspect(tmp_path).state == "stale"
    with pytest.raises(CliFailure, match="edited after this installation wrote it"):
        skill.install(tmp_path, None)


def test_removing_takes_back_only_what_was_installed(tmp_path: Path) -> None:
    keepsake = tmp_path / "settings.json"
    keepsake.write_text('{"theirs": true}', encoding="utf-8")
    skill.install(tmp_path, "codex")

    assert skill.remove(tmp_path).state == "absent"
    assert not (tmp_path / skill.SKILL_FILENAME).exists()
    assert not (tmp_path / skill.MANIFEST).exists()
    assert not (tmp_path / "references").exists()
    # Their file is a different thing and was never ours.
    assert keepsake.read_text(encoding="utf-8") == '{"theirs": true}'

    # Removing what is not there is the state the caller asked for.
    assert skill.remove(tmp_path).state == "absent"


@pytest.mark.parametrize("damaged", ["{not json", '["a list"]'])
def test_a_damaged_ownership_record_is_treated_as_someone_elses_file(
    damaged: str, tmp_path: Path
) -> None:
    skill.install(tmp_path, None)
    (tmp_path / skill.MANIFEST).write_text(damaged, encoding="utf-8")
    # Failing closed: without a readable claim there is no evidence it is ours,
    # and taking over a file on a guess is the thing this refuses to do.
    assert skill.inspect(tmp_path).state == "foreign"


def test_the_commands_report_the_destination_without_the_home_path(tmp_path: Path) -> None:
    asked = {"target": str(tmp_path)}
    assert skill_commands.status(asked).payload.state == "absent"

    installed = skill_commands.install({**asked, "harness": "pi"}).payload
    assert installed.state == "owned"
    assert installed.harness == "pi"
    assert installed.available_harnesses == list(skill.HARNESSES)
    assert str(Path.home()) not in installed.target

    assert skill_commands.remove(asked).payload.state == "absent"

    with pytest.raises(CliFailure, match="destination directory is required"):
        skill_commands.status({})


def test_status_creates_nothing_at_all(tmp_path: Path) -> None:
    absent = tmp_path / "never-made"
    assert skill_commands.status({"target": str(absent)}).payload.state == "absent"
    assert not absent.exists()


def test_an_installed_package_conforms_to_the_agent_skills_specification(tmp_path: Path) -> None:
    destination = tmp_path / "ai-stp"
    skill.install(destination, None)
    report = validate(destination)
    assert report.packaged_as == "skill"
    assert report.conforms is True, report.findings
    russian = tmp_path / "ai-stp-ru"
    held = skill.install(russian, "codex", "ru")
    assert held.locale == "ru"
    assert "Hard rules" in (russian / "SKILL.md").read_text(encoding="utf-8")
    assert "skills/canonical/" not in (russian / "SKILL.md").read_text(encoding="utf-8")


def test_the_skill_destination_is_declared_as_mandatory_as_it_behaves() -> None:
    """Machine help said optional; the handler had always refused without it.

    Measured in the functional sweep of 2026-09-02: `skill install`,
    `skill status` and `skill remove` declared `--target` optional with an empty
    `parameter_rules`, and `_target` answers `AI_STP_VALIDATION_ERROR — a
    destination directory is required` the moment it is absent, with no
    configured fallback. An agent that builds argv from the declaration — which
    is the whole point of the declaration — met a stop the declaration had told
    it could not happen. The hidden-`confirm` shape, one field over.
    """
    from ai_stp_cli import registry

    for path in (["skill", "install"], ["skill", "status"], ["skill", "remove"]):
        declared = next(item for item in registry.DECLARATIONS if item.path == path)
        target = next(item for item in declared.parameters if item.name == "target")
        assert target.required, f"{' '.join(path)} refuses without --target"
