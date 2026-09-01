"""Dismissible catalog replacement for an embedded snapshot (REQ-5715)."""

from __future__ import annotations

from collections.abc import Sequence

from ai_stp_foundation.digests import digest_bytes
from ai_stp_sources.catalog_match import (
    CatalogMatchInput,
    CatalogReplacementSuggestion,
    suggest_catalog_replacement,
)
from ai_stp_sources.definition import pack_component_tree
from ai_stp_sources.files import ARTIFACT_DIGEST_DOMAIN
from ai_stp_sources.models import SourceSnapshot

__all__ = [
    "CatalogMatchInput",
    "CatalogReplacementSuggestion",
    "artifact_digest_for_snapshot",
    "suggest_embedded_catalog_replacement",
]


def artifact_digest_for_snapshot(snapshot: SourceSnapshot) -> str:
    """Packed component-tree digest used for catalog comparison."""
    return digest_bytes(ARTIFACT_DIGEST_DOMAIN, pack_component_tree(snapshot.files))


def suggest_embedded_catalog_replacement(
    snapshot: SourceSnapshot,
    catalog: Sequence[CatalogMatchInput],
) -> CatalogReplacementSuggestion | None:
    """Suggest a catalog pin only when coordinate and artifact digest both match.

    The embedded snapshot is not rewritten. A match is dismissible and never
    substitutes catalog identity.
    """
    return suggest_catalog_replacement(
        canonical_coordinate=snapshot.canonical_coordinate,
        artifact_digest=artifact_digest_for_snapshot(snapshot),
        catalog=catalog,
    )
