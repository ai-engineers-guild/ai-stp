"""The bounded index: what it leaves out matters more than what it keeps."""

from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import project_index


def _tree(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("rules\n", encoding="utf-8")
    (root / "README.md").write_text("# hello\n", encoding="utf-8")
    source = root / "src"
    source.mkdir()
    (source / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    (source / "app.ts").write_text("export const a = 1;\n", encoding="utf-8")
    return root


def test_files_are_classified_and_described_without_keeping_content(tmp_path: Path) -> None:
    built = project_index.build(_tree(tmp_path / "project"))
    by_path = {item.path: item for item in built.entries}

    assert built.state == "complete"
    assert by_path["pyproject.toml"].kind == "manifest"
    assert by_path["uv.lock"].kind == "lock"
    assert by_path["AGENTS.md"].kind == "agent_surface"
    assert by_path["README.md"].kind == "document"
    assert by_path["src/app.py"].language == "python"
    assert by_path["src/app.ts"].language == "typescript"

    # Described, not stored: a digest and a size, never the bytes.
    entry = by_path["src/app.py"]
    assert entry.digest is not None and entry.digest.startswith("sha256:")
    assert entry.lines == 2
    assert not hasattr(entry, "content")


def test_the_index_is_deterministic(tmp_path: Path) -> None:
    root = _tree(tmp_path / "project")
    first = project_index.build(root)
    second = project_index.build(root)
    assert [item.path for item in first.entries] == [item.path for item in second.entries]
    assert [item.digest for item in first.entries] == [item.digest for item in second.entries]


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.production",
        ".netrc",
        ".npmrc",
        "id_rsa",
        "server.pem",
        "private.key",
        "secrets.yaml",
        "store.p12",
        "SECRET.PEM",
    ],
)
def test_a_file_whose_name_says_credential_is_excluded_by_name_alone(
    name: str, tmp_path: Path
) -> None:
    # By name only. Opening a file to find out whether it holds a secret is the
    # one inspection that cannot be justified, because doing it is the harm.
    root = _tree(tmp_path / "project")
    (root / name).write_text("TOKEN=leak-me\n", encoding="utf-8")

    built = project_index.build(root)
    assert name not in {item.path for item in built.entries}
    excluded = {item.path: item.reason for item in built.excluded}
    assert excluded[name] == "looks like a credential"


def test_binary_content_is_excluded_by_the_rule_git_uses(tmp_path: Path) -> None:
    root = _tree(tmp_path / "project")
    (root / "image.dat").write_bytes(b"PNG\x00\x01\x02binary")
    # A NUL beyond the probe window is not seen, which is the same bargain git
    # makes: bounded reading in exchange for a bounded answer.
    (root / "late.dat").write_bytes(b"a" * project_index.BINARY_PROBE_BYTES + b"\x00")

    built = project_index.build(root)
    excluded = {item.path: item.reason for item in built.excluded}
    assert excluded["image.dat"] == "binary content"
    assert "late.dat" in {item.path for item in built.entries}


def test_excluded_directories_never_reach_the_index(tmp_path: Path) -> None:
    root = _tree(tmp_path / "project")
    for name in ("node_modules", ".git", "__pycache__", "dist", ".venv"):
        place = root / name
        place.mkdir()
        (place / "thing.py").write_text("x = 1\n", encoding="utf-8")

    built = project_index.build(root)
    paths = {item.path for item in built.entries}
    assert not any(
        path.split("/")[0] in {"node_modules", ".git", "dist", ".venv"} for path in paths
    )
    reasons = {item.path: item.reason for item in built.excluded}
    assert reasons["node_modules"] == "excluded directory"


def test_a_symlink_pointing_out_of_the_root_is_excluded(tmp_path: Path) -> None:
    root = _tree(tmp_path / "project")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "theirs.txt").write_text("not ours\n", encoding="utf-8")
    (root / "escape").symlink_to(outside, target_is_directory=True)
    (root / "escape-file").symlink_to(outside / "theirs.txt")

    built = project_index.build(root)
    reasons = {item.path: item.reason for item in built.excluded}
    assert reasons["escape"] == "outside the root"
    assert reasons["escape-file"] == "outside the root"
    assert not any("theirs" in item.path for item in built.entries)


def test_a_symlink_pointing_back_inside_is_kept(tmp_path: Path) -> None:
    # It is part of this tree. Containment decides, not "is it a symlink".
    root = _tree(tmp_path / "project")
    (root / "alias.md").symlink_to(root / "README.md")
    built = project_index.build(root)
    assert "alias.md" in {item.path for item in built.entries}


def test_a_file_too_large_to_read_is_inventoried_not_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_index, "MAX_FILE_BYTES", 16)
    root = _tree(tmp_path / "project")
    (root / "big.txt").write_text("x" * 100, encoding="utf-8")

    built = project_index.build(root)
    entry = next(item for item in built.entries if item.path == "big.txt")
    # Its existence and size are facts worth having; its content is not worth
    # the budget.
    assert entry.size_bytes == 100
    assert entry.digest is None
    assert entry.lines is None


def test_reaching_the_entry_budget_produces_a_partial_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_index, "MAX_ENTRIES", 2)
    built = project_index.build(_tree(tmp_path / "project"))
    assert built.state == "partial"
    assert built.stopped_by == "entry budget"
    assert len(built.entries) == 2


def test_reaching_the_time_budget_produces_a_partial_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_index, "MAX_SECONDS", -1.0)
    built = project_index.build(_tree(tmp_path / "project"))
    assert built.state == "partial"
    assert built.stopped_by == "time budget"


def test_reaching_the_depth_budget_stops_descending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(project_index, "MAX_DEPTH", 2)
    root = _tree(tmp_path / "project")
    deep = root / "one" / "two" / "three"
    deep.mkdir(parents=True)
    (deep / "buried.py").write_text("x = 1\n", encoding="utf-8")

    built = project_index.build(root)
    assert "one/two/three/buried.py" not in {item.path for item in built.entries}
    assert any(item.reason == "depth budget" for item in built.excluded)


def test_a_root_that_is_not_a_directory_is_named(tmp_path: Path) -> None:
    file = tmp_path / "a-file.txt"
    file.write_text("", encoding="utf-8")
    with pytest.raises(CliFailure, match="not a directory"):
        project_index.build(file)


@pytest.mark.unprivileged
def test_an_unreadable_file_says_so_rather_than_calling_itself_binary(tmp_path: Path) -> None:
    """Two different answers a caller acts on differently.

    Deciding both from one read is what stops them being confused: an earlier
    version probed for a NUL byte and treated any failure as "binary", so a file
    whose permissions were wrong was reported as content it was not.
    """
    root = _tree(tmp_path / "project")
    shut = root / "shut.txt"
    shut.write_text("hidden\n", encoding="utf-8")
    shut.chmod(0o000)
    try:
        built = project_index.build(root)
        reasons = {item.path: item.reason for item in built.excluded}
        assert reasons["shut.txt"] == "cannot be read"
    finally:
        shut.chmod(0o600)


def test_a_file_that_disappears_between_listing_and_reading_is_not_fatal(
    tmp_path: Path,
) -> None:
    # A tree being indexed is a tree somebody may be editing.
    root = _tree(tmp_path / "project")
    vanishing = root / "gone.txt"
    vanishing.write_text("here for now\n", encoding="utf-8")
    vanishing.unlink()
    built = project_index.build(root)
    assert "gone.txt" not in {item.path for item in built.entries}


def test_a_configuration_file_is_classified_as_one(tmp_path: Path) -> None:
    root = _tree(tmp_path / "project")
    for name in ("ruff.toml", "compose.yaml", "tsconfig.json", "setup.ini"):
        (root / name).write_text("", encoding="utf-8")
    kinds = {item.path: item.kind for item in project_index.build(root).entries}
    assert kinds["ruff.toml"] == "config"
    assert kinds["compose.yaml"] == "config"
    assert kinds["tsconfig.json"] == "config"
    assert kinds["setup.ini"] == "config"


def test_the_binary_rule_reads_only_the_first_bytes() -> None:
    assert project_index.is_binary(b"text\x00more")
    assert not project_index.is_binary(b"plain text")
    # Beyond the probe window is not seen. That is the bargain git makes too:
    # bounded reading in exchange for a bounded answer.
    assert not project_index.is_binary(b"a" * project_index.BINARY_PROBE_BYTES + b"\x00")


def test_the_command_reports_the_index_without_the_home_path(tmp_path: Path) -> None:
    from ai_stp_cli.commands import project

    root = _tree(tmp_path / "project")
    (root / ".env").write_text("TOKEN=x\n", encoding="utf-8")

    answer = project.index({"root": str(root)}).payload
    assert answer.state == "complete"
    assert str(Path.home()) not in answer.root
    assert ".env" not in {item.path for item in answer.files}
    assert ".env" in {item.path for item in answer.excluded}

    with pytest.raises(CliFailure, match="project root is required"):
        project.index({})


def test_a_symlink_inside_the_tree_is_named_by_itself_not_its_target(tmp_path: Path) -> None:
    """The bug this pins: containment resolves, naming must not.

    Naming an entry by its resolved path filed a symlink under its target's
    name, so the entry appeared twice and the link itself vanished. An index
    that quietly reports one file as two is worse than one that omits it.
    """
    root = _tree(tmp_path / "project")
    (root / "alias.md").symlink_to(root / "README.md")

    built = project_index.build(root)
    paths = [item.path for item in built.entries]

    assert "alias.md" in paths
    assert "README.md" in paths
    assert len(paths) == len(set(paths)), f"an entry was reported twice: {paths}"


def test_a_link_to_a_directory_inside_the_tree_is_not_indexed_as_a_file(tmp_path: Path) -> None:
    # It arrives among the file names because `Path.walk` does not follow it,
    # and the directory it points at is walked on its own. Indexing the link
    # would report a directory as a file and count its contents twice.
    root = _tree(tmp_path / "project")
    (root / "src-alias").symlink_to(root / "src", target_is_directory=True)

    built = project_index.build(root)
    reasons = {item.path: item.reason for item in built.excluded}
    assert reasons["src-alias"] == "a directory link is not indexed"
    assert "src/app.py" in {item.path for item in built.entries}


def test_a_broken_symlink_is_excluded_rather_than_raising(tmp_path: Path) -> None:
    # Common in a real checkout: a link whose target was moved or never cloned.
    root = _tree(tmp_path / "project")
    (root / "dangling.txt").symlink_to(root / "never-existed.txt")

    built = project_index.build(root)
    reasons = {item.path: item.reason for item in built.excluded}
    assert reasons["dangling.txt"] == "cannot be read"
