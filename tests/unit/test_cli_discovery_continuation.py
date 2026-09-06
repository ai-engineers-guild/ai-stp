"""Bounded discovery reports when it did not finish, and the cursor resumes (`REQ-535`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_stp_cli.local import authoring, components, path_inventory
from ai_stp_contracts.machine_help import PathInventory


def _portable_tree(tmp_path: Path) -> Path:
    repository = tmp_path / "portable"
    for name in ("a", "b", "c"):
        place = repository / "skills" / name / "nested"
        place.mkdir(parents=True)
        (place / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    return repository


def _portable(report: components.Discovery) -> set[Path]:
    return {
        item.absolute
        for item in report.components
        if item.layout_source == components.PORTABLE_SKILL_SOURCE
    }


def test_a_bounded_portable_walk_is_incomplete_and_resumable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _portable_tree(tmp_path)
    monkeypatch.setattr(components, "MAX_PORTABLE_SKILL_DIRECTORIES", 1)

    first = components.discover_report(project=repository)
    assert first.complete is False
    assert first.continuation
    first_page = _portable(first)
    assert len(first_page) < 3

    seen = set(first_page)
    cursor = first.continuation
    pages = 1
    while cursor:
        nxt = components.discover_report(project=repository, continuation=cursor)
        page = _portable(nxt)
        assert page.isdisjoint(seen)
        seen |= page
        cursor = nxt.continuation
        pages += 1
        assert pages < 10
        if nxt.complete:
            assert cursor is None
            break

    monkeypatch.setattr(components, "MAX_PORTABLE_SKILL_DIRECTORIES", 1000)
    full = _portable(components.discover_report(project=repository))
    assert seen == full
    assert full == {
        repository / "skills" / "a" / "nested",
        repository / "skills" / "b" / "nested",
        repository / "skills" / "c" / "nested",
    }


def test_an_unreadable_skill_directory_is_not_an_empty_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "portable"
    hidden = repository / "skills" / "hidden"
    hidden.mkdir(parents=True)
    (hidden / "SKILL.md").write_text("# hidden\n", encoding="utf-8")
    visible = repository / "skills" / "open"
    visible.mkdir(parents=True)
    (visible / "SKILL.md").write_text("# open\n", encoding="utf-8")
    real_iterdir = Path.iterdir

    def iterdir(self: Path):
        if self.name == "hidden" and self.parent.name == "skills":
            raise PermissionError("denied")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    report = components.discover_report(project=repository)

    assert any(item.code == "unreadable" and "hidden" in item.reason for item in report.diagnostics)
    assert report.complete is False
    assert visible in _portable(report)


def test_an_absent_skills_collection_is_not_an_unreadable_one(tmp_path: Path) -> None:
    """A named root with no `skills/` finished; it is not a listing we could not read."""
    repository = tmp_path / "project"
    repository.mkdir()
    report = components.discover_report(project=repository)
    assert not any(item.code == "unreadable" for item in report.diagnostics)
    assert report.complete is True
    assert report.continuation is None


def test_a_bounded_inventory_walk_is_incomplete_and_resumable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in ("alpha-kit", "beta-kit", "gamma-kit"):
        root = workspace / name
        _plan, files = authoring.scaffold_plan(
            component_type="skill",
            name=name,
            language="none",
            harness_variant="portable",
            output=root,
        )
        authoring.write_new_tree(root, files)
    monkeypatch.setattr(path_inventory, "MAX_INVENTORY_DIRECTORIES", 1)

    first = path_inventory.inventory_root(workspace)
    assert first.complete is False
    assert first.continuation
    first_ids = {item.object_id for item in first.objects if item.relation == "independent"}

    seen = set(first_ids)
    cursor = first.continuation
    pages = 1
    while cursor:
        nxt = path_inventory.inventory_root(workspace, cursor=cursor)
        page = {item.object_id for item in nxt.objects if item.relation == "independent"}
        assert page.isdisjoint(seen)
        seen |= page
        cursor = nxt.continuation
        pages += 1
        assert pages < 20
        if nxt.complete:
            assert cursor is None
            break

    monkeypatch.setattr(path_inventory, "MAX_INVENTORY_DIRECTORIES", 1000)
    full = path_inventory.inventory_root(workspace)
    assert {item.relative_path for item in full.objects if item.relation == "independent"} >= {
        "alpha-kit",
        "beta-kit",
        "gamma-kit",
    }
    assert seen == {item.object_id for item in full.objects if item.relation == "independent"}


def test_inventory_keeps_authoring_coverage_across_portable_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    owned = workspace / "skills" / "owned"
    owned.mkdir(parents=True)
    (owned / "SKILL.md").write_text("# owned\n", encoding="utf-8")
    (owned / "component-passport.json").write_text(
        '{"name":"owned","component_type":"skill"}\n', encoding="utf-8"
    )
    for name in ("alpha", "beta", "gamma"):
        place = workspace / "skills" / name
        place.mkdir()
        (place / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")

    monkeypatch.setattr(components, "MAX_PORTABLE_SKILL_DIRECTORIES", 1)
    pages: list[PathInventory] = []
    cursor: str | None = None
    while True:
        page = path_inventory.inventory_root(workspace, cursor=cursor)
        pages.append(page)
        cursor = page.continuation
        if page.complete or cursor is None:
            break
        assert len(pages) < 20

    monkeypatch.setattr(components, "MAX_PORTABLE_SKILL_DIRECTORIES", 2000)
    full = path_inventory.inventory_root(workspace)
    paged = [item for page in pages for item in page.objects]
    paged_ids = [(item.object_id, item.origin, item.relation, item.relative_path) for item in paged]
    full_ids = [
        (item.object_id, item.origin, item.relation, item.relative_path) for item in full.objects
    ]
    assert sorted(paged_ids) == sorted(full_ids)
    owned_rows = [item for item in paged if item.relative_path.endswith("skills/owned")]
    assert owned_rows
    assert all(item.origin == "passport" for item in owned_rows)
    assert not any(
        item.origin == "native" and item.relative_path.endswith("skills/owned") for item in paged
    )


def test_inventory_does_not_materialize_a_whole_wide_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "wide"
    workspace.mkdir()
    for index in range(6):
        child = workspace / f"child-{index:02d}"
        child.mkdir()
        (child / "SKILL.md").write_text("# child\n", encoding="utf-8")
    monkeypatch.setattr(path_inventory, "MAX_INVENTORY_ENTRIES", 2)
    report = path_inventory.inventory_root(workspace)
    assert report.complete is False
    assert any(item.code == "bounded_limit" for item in report.diagnostics)
