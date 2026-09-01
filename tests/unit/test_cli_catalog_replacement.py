"""Catalog replacement is suggestion-only (SPEC-057 REQ-5715)."""

from __future__ import annotations

from ai_stp_cli.local.catalog_replacement import (
    CatalogMatchInput,
    artifact_digest_for_snapshot,
    suggest_embedded_catalog_replacement,
)
from ai_stp_sources.catalog_match import suggest_catalog_replacement
from ai_stp_sources.models import SourceSnapshot

COMMIT = "a" * 40
STABLE = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV"
COORDINATE = f"git:https://github.com/acme/tool@{COMMIT}:skills/demo"


def _snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        kind="git",
        canonical_coordinate=COORDINATE,
        exact_identity=COMMIT,
        files={"SKILL.md": b"# Demo\n"},
    )


def test_coordinate_and_digest_yield_dismissible_suggestion() -> None:
    snapshot = _snapshot()
    digest = artifact_digest_for_snapshot(snapshot)
    catalog = (
        CatalogMatchInput(
            stable_id=STABLE,
            version="1.0",
            canonical_coordinate=COORDINATE,
            artifact_digest=digest,
        ),
    )
    suggestion = suggest_embedded_catalog_replacement(snapshot, catalog)
    assert suggestion is not None
    assert suggestion.dismissible is True
    assert suggestion.catalog_stable_id == STABLE
    assert suggestion.catalog_version == "1.0"


def test_coordinate_only_or_digest_only_does_not_suggest() -> None:
    snapshot = _snapshot()
    digest = artifact_digest_for_snapshot(snapshot)
    catalog = (
        CatalogMatchInput(
            stable_id=STABLE,
            version="1.0",
            canonical_coordinate=COORDINATE,
            artifact_digest=digest,
        ),
    )
    assert (
        suggest_catalog_replacement(
            canonical_coordinate=COORDINATE,
            artifact_digest="sha256:" + "c" * 64,
            catalog=catalog,
        )
        is None
    )
    assert (
        suggest_catalog_replacement(
            canonical_coordinate=f"git:https://github.com/acme/other@{COMMIT}:skills/demo",
            artifact_digest=digest,
            catalog=catalog,
        )
        is None
    )
    assert (
        suggest_catalog_replacement(
            canonical_coordinate=COORDINATE,
            artifact_digest=digest,
            catalog=(
                *catalog,
                CatalogMatchInput(
                    stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAW",
                    version="1.0",
                    canonical_coordinate=COORDINATE,
                    artifact_digest=digest,
                ),
            ),
        )
        is None
    )
    assert (
        suggest_embedded_catalog_replacement(
            SourceSnapshot(
                kind="git",
                canonical_coordinate=COORDINATE,
                exact_identity=COMMIT,
                files={"SKILL.md": b"# Different\n"},
            ),
            catalog,
        )
        is None
    )
