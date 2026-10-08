"""Real filesystem evidence and bounded traversal against the existing reader."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_stp_cli.local import project_index, projects
from ai_stp_contracts.cli.project import ProjectCandidates, ProjectIndex

Runner = Callable[[Path, Path, list[str], int], dict[str, Any]]


def prove(binary: Path, home: Path, temporary: Path, run: Runner) -> None:
    root = temporary / "project"
    root.mkdir()
    (root / "src").mkdir()
    (root / "Cargo.toml").write_text('[package]\nname = "example"\n', encoding="utf-8")
    (root / "src" / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("Public project instructions.\n", encoding="utf-8")
    (root / ".env").write_text("DO_NOT_READ=must-not-be-echoed", encoding="utf-8")
    (root / "binary.dat").write_bytes(b"a\x00b")
    (root / "target").mkdir()
    (root / "target" / "ignored.rs").write_text("excluded", encoding="utf-8")
    (root / "nested").mkdir()
    (root / "nested" / ".git").mkdir()
    (root / "nested" / "readme.md").write_text("Documentation only.", encoding="utf-8")
    with (root / "large.txt").open("wb") as stream:
        stream.truncate(1024 * 1024 + 1)
    before = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
    answer = run(binary, home, ["project", "index", "--root", str(root)], 0)["data"]
    observed = ProjectIndex.model_validate(answer)
    expected = project_index.build(root)
    assert observed.state == expected.state == "complete"
    assert [item.path for item in observed.files] == [item.path for item in expected.entries]
    for actual, reference in zip(observed.files, expected.entries, strict=True):
        assert (actual.kind, actual.language, actual.size_bytes, actual.digest, actual.lines) == (
            reference.kind,
            reference.language,
            reference.size_bytes,
            reference.digest,
            reference.lines,
        )
    assert {item.path: item.reason for item in observed.excluded} == {
        item.path: item.reason for item in expected.excluded
    }
    discovery = ProjectCandidates.model_validate(
        run(binary, home, ["project", "discover", "--root", str(root)], 0)["data"]
    )
    assert discovery.complete
    assert [
        (Path(item.root).name, item.kind, item.state, item.markers) for item in discovery.candidates
    ] == [
        (item.root.name, item.kind, item.state, list(item.markers))
        for item in projects.discover(root)
    ]
    after = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert before == after
    assert "must-not-be-echoed" not in str(answer)
    false_markers = temporary / "false-markers"
    false_markers.mkdir()
    (false_markers / "Cargo.toml").mkdir()
    if os.name != "nt":
        (false_markers / "package.json").symlink_to(root / ".env")
        (root / "src" / ".git").symlink_to(temporary)
        discovery = run(binary, home, ["project", "discover", "--root", str(root)], 0)["data"]
        assert {Path(item["root"]).name for item in discovery["candidates"]} == {
            "project",
            "nested",
        }
        (root / "escape").symlink_to(temporary)
        (root / "alias.txt").symlink_to(".env")
        os.mkfifo(root / "pipe")
        answer = run(binary, home, ["project", "index", "--root", str(root)], 0)["data"]
        excluded = {item["path"]: item["reason"] for item in answer["excluded"]}
        assert excluded["escape"] == excluded["alias.txt"] == "symlink is not followed"
        assert excluded["pipe"] == "not a regular file"
        run(binary, home, ["config", "show", "--config", str(root / "pipe")], 2)
        run(binary, home, ["config", "show", "--config", str(root / "alias.txt")], 2)
    result = run(binary, home, ["project", "discover", "--root", str(false_markers)], 0)["data"]
    assert all(not item["markers"] for item in result["candidates"])
    deep = root
    for _ in range(13):
        deep = deep / "deeper"
        deep.mkdir()
    result = run(binary, home, ["project", "index", "--root", str(root)], 0)["data"]
    assert result["state"] == "partial" and result["stopped_by"] == "depth budget"
    crowded = temporary / "crowded"
    crowded.mkdir()
    for number in range(2001):
        (crowded / str(number)).touch()
    result = run(binary, home, ["project", "discover", "--root", str(crowded)], 0)["data"]
    assert result["complete"] is False and result["candidates"] == []
    result = run(binary, home, ["project", "index", "--root", str(crowded)], 0)["data"]
    assert result["state"] == "partial" and result["files"] == []
    run(binary, home, ["project", "discover", "--root", str(home)], 2)
    run(binary, home, ["project", "index", "--root", str(home)], 2)
