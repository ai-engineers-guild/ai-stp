"""Dispatch SourceIntent to the matching adapter (SPEC-057 REQ-5701)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ai_stp_sources.coordinates import canonicalize_source
from ai_stp_sources.errors import FLOATING_FROZEN_SOURCE, INVALID_SOURCE, SourceError
from ai_stp_sources.git import FetchFn, reject_floating_commit, resolve_git
from ai_stp_sources.local import resolve_local
from ai_stp_sources.models import (
    CatalogIntent,
    GitIntent,
    PackageIntent,
    SourceIntent,
    SourceSnapshot,
)
from ai_stp_sources.package import resolve_package


def _catalog_snapshot(intent: CatalogIntent) -> SourceSnapshot:
    variant = "" if intent.variant_id is None else f"+{intent.variant_id}"
    return SourceSnapshot(
        kind="catalog",
        canonical_coordinate=(f"catalog:{intent.stable_id}@{intent.version}{variant}"),
        exact_identity=intent.version,
    )


async def resolve_source(
    intent: SourceIntent,
    *,
    fetch: FetchFn | None = None,
    local_root: Path | None = None,
    token: str | None = None,
    now: datetime | None = None,
) -> SourceSnapshot:
    """Return an exact snapshot. Verification axes stay false."""
    canonical = canonicalize_source(intent)
    if isinstance(canonical, CatalogIntent):
        return _catalog_snapshot(canonical)
    if isinstance(canonical, PackageIntent):
        if fetch is None:
            raise SourceError(INVALID_SOURCE, "package resolution requires a fetch transport")
        return await resolve_package(canonical, fetch=fetch, now=now)
    if isinstance(canonical, GitIntent):
        if fetch is None:
            raise SourceError(INVALID_SOURCE, "git resolution requires a fetch transport")
        snapshot = await resolve_git(canonical, fetch=fetch, token=token, now=now)
        reject_floating_commit(snapshot.exact_identity)
        return snapshot
    if local_root is None:
        raise SourceError(INVALID_SOURCE, "path resolution requires a confirmed root")
    return resolve_local(canonical, local_root=local_root, now=now)


def validate_frozen_snapshot(snapshot: SourceSnapshot) -> None:
    """Reject floating git identity after freeze (REQ-5702)."""
    if snapshot.kind == "git":
        reject_floating_commit(snapshot.exact_identity)
        return
    if snapshot.kind in {"catalog", "path", "package"}:
        if snapshot.kind == "package" and snapshot.package_evidence is None:
            raise SourceError(FLOATING_FROZEN_SOURCE, "frozen package provenance is incomplete")
        return
    raise SourceError(FLOATING_FROZEN_SOURCE, "frozen provenance is incomplete")
