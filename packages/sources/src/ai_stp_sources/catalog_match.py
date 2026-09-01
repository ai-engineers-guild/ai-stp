"""Coordinate-plus-digest catalog replacement is suggestion-only (REQ-5715)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast


@dataclass(frozen=True)
class CatalogMatchInput:
    """One catalog version that may match an embedded snapshot."""

    stable_id: str
    version: str
    canonical_coordinate: str
    artifact_digest: str


@dataclass(frozen=True)
class CatalogReplacementSuggestion:
    """Dismissible catalog identity. Never applied automatically."""

    catalog_stable_id: str
    catalog_version: str
    canonical_coordinate: str
    artifact_digest: str
    dismissible: Literal[True] = True


def suggest_catalog_replacement(
    *,
    canonical_coordinate: str,
    artifact_digest: str,
    catalog: Sequence[CatalogMatchInput],
) -> CatalogReplacementSuggestion | None:
    """Return one suggestion when coordinate and digest both match exactly one row."""
    coordinate = canonical_coordinate.strip()
    digest = artifact_digest.strip()
    if not coordinate or not digest:
        return None
    matches = [
        item
        for item in catalog
        if item.canonical_coordinate == coordinate and item.artifact_digest == digest
    ]
    if len(matches) != 1:
        return None
    match = matches[0]
    return CatalogReplacementSuggestion(
        catalog_stable_id=match.stable_id,
        catalog_version=match.version,
        canonical_coordinate=match.canonical_coordinate,
        artifact_digest=match.artifact_digest,
    )


def catalog_coordinate_from_passport(passport: dict[str, object]) -> str:
    """Prefer observed upstream coordinate; otherwise reconstruct a git coordinate."""
    facts = passport.get("facts")
    if isinstance(facts, dict):
        facts_map = cast(dict[str, object], facts)
        upstream = facts_map.get("upstream_source")
        if isinstance(upstream, dict):
            upstream_map = cast(dict[str, object], upstream)
            value = upstream_map.get("value")
            if isinstance(value, str) and value.strip():
                return value.strip()
    source = passport.get("source")
    if isinstance(source, dict):
        source_map = cast(dict[str, object], source)
        repository = source_map.get("repository")
        commit = source_map.get("commit")
        path = source_map.get("path")
        if (
            isinstance(repository, str)
            and isinstance(commit, str)
            and isinstance(path, str)
            and repository
            and commit
            and path
        ):
            return f"git:{repository}@{commit}:{path}"
    return ""
