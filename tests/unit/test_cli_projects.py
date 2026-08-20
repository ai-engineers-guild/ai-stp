"""Finding projects: named roots only, and a containment check that holds."""

from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import projects


def _repo(root: Path) -> Path:
    (root / ".git").mkdir(parents=True, exist_ok=True)
    return root


def test_an_empty_folder_an_empty_repository_and_docs_are_all_new_projects(tmp_path: Path) -> None:
    # `REQ-402`: one rule with three faces. None of them has anything to index,
    # and answering "not a project" would be wrong in all three.
    empty = tmp_path / "empty"
    empty.mkdir()
    assert projects.classify(empty).state == "new"

    fresh = _repo(tmp_path / "fresh")
    assert projects.classify(fresh).state == "new"
    assert "git" in projects.classify(fresh).markers

    documented = tmp_path / "documented"
    documented.mkdir()
    (documented / "README.md").write_text("# hello", encoding="utf-8")
    (documented / "notes.rst").write_text("notes", encoding="utf-8")
    found = projects.classify(documented)
    assert found.state == "new"
    assert "documentation" in found.reason


def test_a_manifest_makes_a_project_established(tmp_path: Path) -> None:
    for name in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pubspec.yaml"):
        place = tmp_path / name.replace(".", "-")
        place.mkdir()
        (place / name).write_text("", encoding="utf-8")
        found = projects.classify(place)
        assert found.state == "established", name
        assert name in found.markers


def test_a_monorepo_is_one_project_and_its_packages_are_not(tmp_path: Path) -> None:
    # `REQ-409`. A workspace package carrying its own manifest must not become a
    # project of its own, or one repository would register as a dozen.
    root = _repo(tmp_path / "monorepo")
    (root / "pyproject.toml").write_text("", encoding="utf-8")
    for package in ("apps/cli", "packages/core"):
        place = root / package
        place.mkdir(parents=True)
        (place / "pyproject.toml").write_text("", encoding="utf-8")

    found = projects.discover(root)
    assert [item.root for item in found] == [projects.resolved(root)]


def test_a_nested_repository_is_reported_but_not_folded_in(tmp_path: Path) -> None:
    # `REQ-410`: it is somebody's decision, and the CLI does not get to make it.
    root = _repo(tmp_path / "outer")
    (root / "pyproject.toml").write_text("", encoding="utf-8")
    inner = _repo(root / "third-party" / "inner")
    (inner / "package.json").write_text("", encoding="utf-8")

    found = projects.discover(root)
    kinds = {item.kind for item in found}
    assert kinds == {"project", "nested_repository"}
    nested = next(item for item in found if item.kind == "nested_repository")
    assert nested.root == projects.resolved(inner)
    assert "only on purpose" in nested.reason


def test_every_deep_repository_and_worktree_marker_is_reported_once(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    deep = workspace / "groups" / "one" / "two" / "three" / "repository"
    deep.mkdir(parents=True)
    (deep / ".git").write_text("gitdir: /tmp/example.git/worktrees/repository\n", encoding="utf-8")
    (deep / "go.mod").write_text("module example.test/deep\n", encoding="utf-8")

    found = projects.discover(workspace)

    matches = [item for item in found if item.root == projects.resolved(deep)]
    assert len(matches) == 1
    assert matches[0].kind == "project"
    assert matches[0].markers == ("git", "go.mod")
    assert found.complete


def test_a_repository_inside_a_deep_repository_is_explicitly_nested(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outer = _repo(workspace / "groups" / "outer")
    inner = _repo(outer / "vendor-src" / "inner")

    found = projects.discover(workspace)

    by_root = {item.root: item for item in found}
    assert by_root[projects.resolved(outer)].kind == "project"
    assert by_root[projects.resolved(inner)].kind == "nested_repository"


def test_discovery_order_does_not_follow_filesystem_creation_order(tmp_path: Path) -> None:
    def build(root: Path, names: tuple[str, ...]) -> list[tuple[str, str]]:
        root.mkdir()
        for name in names:
            _repo(root / name)
        return [(item.root.name, item.kind) for item in projects.discover(root)]

    first = build(tmp_path / "first", ("zeta", "alpha", "middle"))
    second = build(tmp_path / "second", ("middle", "alpha", "zeta"))

    assert (
        first
        == second
        == [
            ("alpha", "project"),
            ("middle", "project"),
            ("zeta", "project"),
        ]
    )


def test_the_home_directory_is_refused_as_a_discovery_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Not a size limit dressed up as a rule: the home directory is where
    # everything else lives.
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(CliFailure, match="home directory is not a discovery root"):
        projects.discover(tmp_path)


def test_containment_resolves_both_sides_before_comparing(tmp_path: Path) -> None:
    """`is_relative_to` is documented as string-based, so it is not a check.

    It "neither accesses the filesystem nor treats `..` segments specially" —
    both of which are exactly what an escape uses.
    """
    root = tmp_path / "root"
    (root / "inside").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("theirs", encoding="utf-8")

    assert projects.contains(root, root / "inside")

    # Textually inside, actually not.
    assert not projects.contains(root, root / ".." / "outside" / "secret.txt")

    # A symlink pointing out of the tree.
    escape = root / "escape"
    escape.symlink_to(outside, target_is_directory=True)
    assert not projects.contains(root, escape / "secret.txt")

    # And the rule holds for a path that does not exist yet: containment has to
    # be decidable for something a caller only proposes.
    assert projects.contains(root, root / "inside" / "not-created-yet.txt")
    assert not projects.contains(root, escape / "not-created-yet.txt")


def test_discovery_does_not_follow_a_symlinked_directory(tmp_path: Path) -> None:
    # `Path.walk` puts a symlinked directory in the file list rather than
    # descending, and treating one as a directory here would be the one place
    # the containment rule leaked.
    root = _repo(tmp_path / "root")
    (root / "pyproject.toml").write_text("", encoding="utf-8")
    elsewhere = _repo(tmp_path / "elsewhere")
    (root / "link").symlink_to(elsewhere, target_is_directory=True)

    found = projects.discover(root)
    assert all(projects.resolved(elsewhere) != item.root for item in found)
    assert any(item.code == "symlink" and item.path.name == "link" for item in found.diagnostics)


def test_discovery_lists_the_projects_inside_a_named_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    for name in ("alpha", "beta"):
        place = _repo(workspace / name)
        (place / "pyproject.toml").write_text("", encoding="utf-8")
    (workspace / "scratch").mkdir()

    found = projects.discover(workspace)
    by_name = {item.root.name: item for item in found}
    assert by_name["alpha"].state == "established"
    assert by_name["beta"].state == "established"
    assert by_name["scratch"].state == "new"


def test_a_path_that_is_not_a_directory_is_named_rather_than_guessed(tmp_path: Path) -> None:
    file = tmp_path / "a-file.txt"
    file.write_text("", encoding="utf-8")
    for call in (lambda: projects.classify(file), lambda: projects.discover(file)):
        with pytest.raises(CliFailure, match="not a directory"):
            call()


def test_the_command_reports_candidates_without_the_home_path(tmp_path: Path) -> None:
    from ai_stp_cli.commands import project

    place = _repo(tmp_path / "work" / "alpha")
    (place / "go.mod").write_text("", encoding="utf-8")

    answer = project.discover({"root": str(tmp_path / "work")}).payload
    assert [Path(item.root).name for item in answer.candidates] == ["alpha"]
    assert str(Path.home()) not in answer.discovery_root
    assert answer.complete
    assert answer.diagnostics == []
    assert answer.candidates[0].markers == ["git", "go.mod"]

    with pytest.raises(CliFailure, match="directory to look inside is required"):
        project.discover({})


def test_a_folder_of_files_with_no_manifest_is_established(tmp_path: Path) -> None:
    # Not every project declares itself. A folder of scripts has something to
    # index, so calling it "new" would be wrong in the other direction.
    place = tmp_path / "scripts"
    place.mkdir()
    (place / "deploy.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    found = projects.classify(place)
    assert found.state == "established"
    assert "no manifest" in found.reason


@pytest.mark.unprivileged
def test_a_directory_that_cannot_be_read_is_skipped_rather_than_fatal(tmp_path: Path) -> None:
    # Discovery runs over directories nobody promised are readable. One of them
    # refusing is not a reason to answer nothing about the rest.
    place = tmp_path / "work"
    (place / "open").mkdir(parents=True)
    (place / "open" / "go.mod").write_text("", encoding="utf-8")
    shut = place / "shut"
    shut.mkdir()
    shut.chmod(0o000)
    try:
        discovery = projects.discover(place)
        names = {item.root.name for item in discovery}
        assert "open" in names
        assert not discovery.complete
        assert any(item.code == "unreadable" for item in discovery.diagnostics)
    finally:
        shut.chmod(0o700)


def test_a_directory_with_too_many_entries_stops_rather_than_reading_it_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A directory with a hundred thousand children is not a place to look for
    # projects, and reading it all to find that out is the cost being avoided.
    monkeypatch.setattr(projects, "DISCOVERY_ENTRIES", 3)
    place = tmp_path / "crowded"
    place.mkdir()
    for index in range(10):
        (place / f"file-{index}.bin").write_text("", encoding="utf-8")
    # A filesystem listing is unordered. An arbitrary three-entry prefix would
    # make partial candidates vary by filesystem, so an over-limit directory
    # contributes none and carries an explicit incomplete diagnostic.
    assert list(projects._entries(place)) == []  # pyright: ignore[reportPrivateUsage]

    found = projects.discover(place)
    assert not found.complete
    assert any(item.code == "entry_limit" for item in found.diagnostics)


def test_a_discovery_root_holding_nothing_reports_itself(tmp_path: Path) -> None:
    # Answering with an empty list would look like "no projects here" when the
    # truth is "here is a new project".
    place = tmp_path / "brand-new"
    place.mkdir()
    found = projects.discover(place)
    assert [item.root for item in found] == [projects.resolved(place)]
    assert found[0].state == "new"


def test_a_skipped_directory_is_never_a_candidate(tmp_path: Path) -> None:
    place = tmp_path / "work"
    vendored = place / "node_modules" / "left-pad"
    vendored.mkdir(parents=True)
    (vendored / "package.json").write_text("", encoding="utf-8")
    real = place / "app"
    real.mkdir()
    (real / "package.json").write_text("", encoding="utf-8")

    found = projects.discover(place)
    names = {item.root.name for item in found}
    assert names == {"app"}
    assert any(
        item.code == "excluded" and item.path.name == "node_modules" for item in found.diagnostics
    )
