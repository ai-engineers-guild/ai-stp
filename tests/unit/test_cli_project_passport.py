"""The project passport: identity that survives a re-scan."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import project_passport
from ai_stp_cli.local.database import configured_path, open_registry

SECRET = "AKIAIOSFODNN7EXAMPLE"


@pytest.fixture
def registry() -> Iterator[sqlite3.Connection]:
    with closing(open_registry(configured_path(), create=True)) as connection:
        yield connection


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    (root / "src").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "src" / "app.py").write_text("def main() -> None: ...\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname = "work"\n', encoding="utf-8")
    (root / "README.md").write_text("# work", encoding="utf-8")
    return root


def test_a_second_scan_keeps_the_project_identity(
    registry: sqlite3.Connection, project: Path
) -> None:
    # The acceptance criterion of `P3-07`, and the reason a stable id cannot be
    # derived from the path: it is a ULID, so it is minted once and found again.
    first = project_passport.scan(registry, project)
    second = project_passport.scan(registry, project)
    assert first.stable_id == second.stable_id

    # Including when the same root is named differently.
    through_dot = project_passport.scan(registry, project / "src" / "..")
    assert through_dot.stable_id == first.stable_id


def test_two_projects_are_two_passports(registry: sqlite3.Connection, tmp_path: Path) -> None:
    one = tmp_path / "one"
    two = tmp_path / "two"
    for place in (one, two):
        (place / ".git").mkdir(parents=True)
        (place / "a.py").write_text("x = 1\n", encoding="utf-8")

    assert project_passport.scan(registry, one).stable_id != (
        project_passport.scan(registry, two).stable_id
    )


def test_a_revision_pins_the_index_toolchain_and_configuration(
    registry: sqlite3.Connection, project: Path
) -> None:
    found = project_passport.scan(registry, project)
    stored = project_passport.record(registry, found, device_id="device_test")

    facts = stored.envelope.model_dump(mode="json")["facts"]
    for name in ("index_digest", "toolchain_digest", "configuration_digest"):
        assert facts[name]["value"].startswith("sha256:")

    # Three separate facts, and separate digest domains, so identical content in
    # two of them still produces two different values.
    values = {facts[name]["value"] for name in ("index_digest", "configuration_digest")}
    assert len(values) == 2


def test_the_three_digests_stay_apart_even_for_identical_content(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    (tmp_path / ".git").mkdir()
    found = project_passport.scan(registry, tmp_path)
    # An empty project: the index and the configuration list are both empty, so
    # without domain separation these would be the same digest and one could
    # satisfy a check meant for the other.
    assert found.index_digest != found.configuration_digest
    assert found.toolchain_digest != found.index_digest


def test_rescanning_an_unchanged_project_adds_no_revision(
    registry: sqlite3.Connection, project: Path
) -> None:
    first = project_passport.record(
        registry, project_passport.scan(registry, project), device_id="device_test"
    )
    second = project_passport.record(
        registry, project_passport.scan(registry, project), device_id="device_test"
    )
    # Same content, so the same content-addressed revision id, and the store
    # returns what is already there rather than adding a second row.
    assert first.revision_id == second.revision_id
    rows = registry.execute(
        "SELECT COUNT(*) AS held FROM revision WHERE stable_id = ?", (first.stable_id,)
    ).fetchone()
    assert rows["held"] == 1


def test_changing_a_file_changes_the_index_digest(
    registry: sqlite3.Connection, project: Path
) -> None:
    before = project_passport.scan(registry, project)
    (project / "src" / "app.py").write_text("def main() -> None:\n    pass\n", encoding="utf-8")
    after = project_passport.scan(registry, project)

    assert after.index_digest != before.index_digest
    # And the configuration did not move, because nothing in it did.
    assert after.configuration_digest == before.configuration_digest


def test_changing_configuration_changes_only_its_own_digest(
    registry: sqlite3.Connection, project: Path
) -> None:
    before = project_passport.scan(registry, project)
    (project / "pyproject.toml").write_text('[project]\nname = "renamed"\n', encoding="utf-8")
    after = project_passport.scan(registry, project)

    assert after.configuration_digest != before.configuration_digest
    # The index covers configuration files too, so it moves as well. Both facts
    # are true and the passport carries both rather than choosing one.
    assert after.index_digest != before.index_digest


def test_the_index_digest_ignores_when_the_scan_ran(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    one = tmp_path / "one"
    two = tmp_path / "two"
    for place in (one, two):
        (place / ".git").mkdir(parents=True)
        (place / "a.py").write_text("x = 1\n", encoding="utf-8")

    # Two identical trees created at different moments produce the same index
    # digest. A timestamp anywhere in it would make reproducibility impossible
    # to check, which is the whole point of pinning one.
    assert project_passport.scan(registry, one).index_digest == (
        project_passport.scan(registry, two).index_digest
    )


def test_the_local_passport_records_a_redacted_root(
    registry: sqlite3.Connection, project: Path
) -> None:
    found = project_passport.scan(registry, project)
    stored = project_passport.record(registry, found, device_id="device_test")
    root = stored.envelope.model_dump(mode="json")["facts"]["root"]["value"]

    # Local, but still read by agents and pasted into issues.
    assert "/home/" not in root
    assert root.endswith("work")


def test_a_scan_reads_the_toolchain_that_is_installed_not_the_one_pinned(
    registry: sqlite3.Connection, project: Path, tmp_path: Path
) -> None:
    from ai_stp_cli.toolchain import install, load

    before = project_passport.scan(registry, project).toolchain_digest

    pinned = load().tools[0]
    installed = install.installed_path(pinned.tool_id, pinned.version)
    installed.mkdir(parents=True)
    install.activate(installed, pinned.tool_id)

    # Two machines running the same manifest with different tools installed are
    # not reproducing each other, and a digest that could not tell them apart
    # would claim they were.
    assert project_passport.scan(registry, project).toolchain_digest != before


def test_the_command_records_a_revision_and_refuses_without_a_root(project: Path) -> None:
    from ai_stp_cli.commands import project as command

    view = command.passport({"root": str(project)}).payload
    assert view.kind == "project"
    assert view.stable_id.startswith("project_")
    assert view.revision_id.startswith("revision_")
    assert set(view.facts) >= {"index_digest", "toolchain_digest", "configuration_digest"}

    again = command.passport({"root": str(project)}).payload
    assert again.stable_id == view.stable_id
    assert again.revision_id == view.revision_id

    with pytest.raises(CliFailure, match="project root is required"):
        command.passport({})


def test_a_root_never_scanned_has_no_identity_yet(
    registry: sqlite3.Connection, tmp_path: Path
) -> None:
    assert project_passport.stable_id_for(registry, tmp_path) is None


def test_a_failed_record_settles_the_journal_rather_than_leaving_it_open(
    registry: sqlite3.Connection, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai_stp_cli.local import revisions

    def refuse(*_args: object, **_kwargs: object) -> revisions.StoredRevision:
        raise OSError("the disk went away mid-commit")

    found = project_passport.scan(registry, project)
    monkeypatch.setattr(revisions, "commit", refuse)

    with pytest.raises(OSError, match="mid-commit"):
        project_passport.record(registry, found, device_id="device_test")

    # An operation that started and neither finished nor failed is worse than
    # one that failed: a later reader cannot tell it apart from one still
    # running, and recovery has to guess.
    rows = registry.execute("SELECT state FROM operation ORDER BY started_at DESC").fetchall()
    assert rows and rows[0]["state"] == "failed"
