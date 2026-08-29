"""Corpus drift is counted in content, not in the provider's commit.

The manifest records each provider repository's `commit`, and that value moves
on every provider release whether or not `setups/nddev-builder/` moved with it.
Reading staleness off it made all seven harnesses look stale after any release
and deferred the catalogue reseed twice; measured against content on
2026-08-29, three provider releases had moved two of thirty-three components
and none of the seven setups.

These tests hold the distinction: a repository that released without touching
the payload reports no drift, and the one component that did move is named.
"""

from __future__ import annotations

from typing import Any

import pytest
from release_scripts import build_first_party_corpus as builder

HOME = builder.HOME_PREFIX
SETUP = builder.SETUP_PATH


def _manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "harnesses": [
            {
                "harness_id": "cursor",
                "commit": "0" * 40,
                "setup_blob": "setupsha",
                "components": [
                    {
                        "slug": "cli-config.json",
                        "source_path": "nddev-builder/home/cli-config.json",
                        "source_tree": "configsha",
                    },
                    {
                        "slug": "nddev-builder",
                        "source_path": "nddev-builder/home/plugins/nddev-builder",
                        "source_tree": "pluginsha",
                    },
                ],
            }
        ],
    }


def _tree_returning(paths: dict[str, str]) -> Any:
    def _tree(_repository: str) -> tuple[str, list[dict[str, Any]]]:
        # The live commit deliberately differs from the recorded one in every
        # case here: that is the point. A released provider always has a new
        # commit, and it must not by itself count as drift.
        return "f" * 40, [{"path": path, "sha": sha, "type": "blob"} for path, sha in paths.items()]

    return _tree


def test_a_release_that_did_not_touch_the_payload_reports_no_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        builder,
        "_tree",
        _tree_returning(
            {
                SETUP: "setupsha",
                f"{HOME}cli-config.json": "configsha",
                f"{HOME}plugins/nddev-builder": "pluginsha",
            }
        ),
    )
    moved = builder.drift(_manifest(), ["cursor"])
    assert moved["changed"] == 0
    assert moved["unchanged"] == 2
    assert moved["setups"] == []
    assert moved["components"] == {}


def test_the_component_whose_bytes_moved_is_the_one_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        builder,
        "_tree",
        _tree_returning(
            {
                SETUP: "setupsha",
                f"{HOME}cli-config.json": "configsha",
                f"{HOME}plugins/nddev-builder": "a-different-tree",
            }
        ),
    )
    moved = builder.drift(_manifest(), ["cursor"])
    assert moved["changed"] == 1
    assert moved["unchanged"] == 1
    assert moved["components"] == {"cursor": ["nddev-builder"]}
    # The setup did not move, and a moved component must not imply that it did.
    assert moved["setups"] == []


def test_a_changed_setup_is_reported_separately_from_its_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        builder,
        "_tree",
        _tree_returning(
            {
                SETUP: "a-different-setup",
                f"{HOME}cli-config.json": "configsha",
                f"{HOME}plugins/nddev-builder": "pluginsha",
            }
        ),
    )
    moved = builder.drift(_manifest(), ["cursor"])
    assert moved["setups"] == ["cursor"]
    assert moved["changed"] == 0


def test_drift_reports_and_never_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lagging the provider by a component is publishable, not a failure.

    A corpus two components behind is a normal state — the next version carries
    them. Exiting non-zero on it would reinstate the block this measurement was
    written to remove, so `drift` returns a report and the caller decides.
    """
    monkeypatch.setattr(
        builder,
        "_tree",
        _tree_returning({SETUP: "gone", f"{HOME}cli-config.json": "gone"}),
    )
    moved = builder.drift(_manifest(), ["cursor"])
    assert moved["changed"] == 2
    assert isinstance(moved, dict)


def test_a_rebuild_keeps_the_identifiers_a_previous_build_gave(tmp_path: Any) -> None:
    """Rebuilding must produce new *versions*, not forty new objects.

    `new_id` mints a fresh ULID per call, so before identity continuity every
    rebuild replaced all forty ids. Published `X.Y` is immutable, which means a
    seeded corpus with fresh ids on every rebuild has no path from `1.0` to
    `1.1`: the next provider change could only ever be published as new
    objects, orphaning the seeded set.
    """
    (tmp_path / "corpus-sources.json").write_text(
        '{"schema_version":1,"harnesses":[{"harness_id":"cursor","setup_id":"setup_HELD",'
        '"components":[{"component_type":"setting","slug":"cli-config.json",'
        '"stable_id":"component_HELD"}]}]}',
        encoding="utf-8",
    )
    components, setups = builder.held_identities(tmp_path)
    assert components[("cursor", "setting", "cli-config.json")] == "component_HELD"
    assert setups["cursor"] == "setup_HELD"


def test_an_empty_directory_holds_no_identities(tmp_path: Any) -> None:
    """A first build has nothing to continue, and must not pretend otherwise."""
    assert builder.held_identities(tmp_path) == ({}, {})


def test_provenance_asks_for_the_path_history_not_the_repository_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`source.commit` must name a commit that touched the captured bytes.

    It asked `commits/main` until 2026-08-29. HEAD moves on every provider
    release and `source.commit` sits inside a content-addressed passport, so all
    seven setup passports changed their digest whenever any provider released —
    even the five whose payload had not moved at all. A published `X.Y` is
    immutable, so that made a seeded corpus look outdated forever.
    """
    asked: list[str] = []

    def _gh(path: str, _jq: str) -> str:
        asked.append(path)
        return "abc"

    monkeypatch.setattr(builder, "_gh", _gh)
    assert builder.source_commit("cursor-setup-system") == "abc"
    assert f"path={builder.SOURCE_PATH}" in asked[0]
    assert "commits/main" not in asked[0]


def test_a_path_no_commit_ever_touched_is_refused_rather_than_guessed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty history has no honest commit, and inventing one is the defect."""

    def _empty(_path: str, _jq: str) -> str:
        return ""

    monkeypatch.setattr(builder, "_gh", _empty)
    with pytest.raises(RuntimeError, match="no commit has touched"):
        builder.source_commit("cursor-setup-system")
