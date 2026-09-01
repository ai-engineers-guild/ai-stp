# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
"""Name-only discovery over catalog and, with a flag, package/GitHub (REQ-5713).

The resolver never chooses. Equal names stay distinct identities (REQ-5716).
After freeze, names are not used to resolve a component: that path is the
exact `ComponentRef` on the setup definition.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from typing import Final

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import content, revisions, versions
from ai_stp_contracts.machine_help import (
    CatalogSearchResult,
    SourceSearchCandidate,
    SourceSearchResult,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_sources.definition import try_parse_setup_definition

MAX_QUERY: Final[int] = 512
CatalogSearchFn = Callable[[str], CatalogSearchResult]
ExtraCandidatesFn = Callable[[str], tuple[SourceSearchCandidate, ...]]


def discover(
    query: str,
    *,
    registry_discovery: bool,
    catalog_search: CatalogSearchFn,
    extra_candidates: ExtraCandidatesFn | None = None,
    connection: sqlite3.Connection | None = None,
) -> SourceSearchResult:
    """Search by name. Package and known GitHub hits require the opt-in flag."""
    needle = query.strip()
    if not needle or len(needle) > MAX_QUERY:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a name-only query is required",
            next_actions=["component source search --query <name> --json"],
        )

    catalog_hits = _catalog_candidates(catalog_search(needle), needle)
    extras: list[SourceSearchCandidate] = []
    if registry_discovery:
        extras.extend(_known_github_candidates(connection, needle))
        extras.extend(_known_package_candidates(connection, needle))
        if extra_candidates is not None:
            extras.extend(extra_candidates(needle))

    candidates = _dedupe((*catalog_hits, *extras))
    resolution: str
    selected: SourceSearchCandidate | None = None
    if not candidates:
        resolution = "unresolved"
    elif len(candidates) == 1:
        resolution = "resolved"
    else:
        resolution = "needs_selection"
    # Equal names, or more than one hit, are never silently chosen.
    if resolution != "resolved":
        selected = None
    return SourceSearchResult(
        query=needle,
        registry_discovery=registry_discovery,
        resolution=resolution,  # pyright: ignore[reportArgumentType]
        selected=selected,
        candidates=list(candidates),
    )


def _catalog_candidates(
    page: CatalogSearchResult, needle: str
) -> tuple[SourceSearchCandidate, ...]:
    found: list[SourceSearchCandidate] = []
    for item in [*page.items, *page.experimental]:
        name = str(getattr(item, "latest_name", "") or "")
        if not _name_matches(needle, name):
            continue
        trust = getattr(item, "latest_trust", None)
        found.append(
            SourceSearchCandidate(
                name=name,
                source="catalog",
                exact_coordinate=f"catalog:{item.stable_id}@{item.latest_version}",
                catalog_status="catalog",
                trust_lane=trust.trust_lane if trust is not None else "experimental",
                author_verified=bool(trust.author_verified) if trust is not None else False,
                component_verified=bool(trust.component_verified) if trust is not None else False,
                stable_id=item.stable_id,
            )
        )
    return tuple(found)


def _known_github_candidates(
    connection: sqlite3.Connection | None, needle: str
) -> tuple[SourceSearchCandidate, ...]:
    if connection is None:
        return ()
    found: list[SourceSearchCandidate] = []
    rows = connection.execute(
        "SELECT repository_full_name, source_repository, passport_digest "
        "FROM github_repository_observation"
    ).fetchall()
    for row in rows:
        full_name = str(row["repository_full_name"])
        if not _name_matches(needle, full_name) and not _name_matches(
            needle, full_name.rsplit("/", 1)[-1]
        ):
            continue
        found.append(
            SourceSearchCandidate(
                name=full_name.rsplit("/", 1)[-1],
                source="git",
                exact_coordinate=f"git:{row['source_repository']}",
                catalog_status="not_in_catalog",
                trust_lane="experimental",
                author_verified=False,
                component_verified=False,
            )
        )
    found.extend(_embedded_source_candidates(connection, needle, kind="git"))
    return tuple(found)


def _known_package_candidates(
    connection: sqlite3.Connection | None, needle: str
) -> tuple[SourceSearchCandidate, ...]:
    if connection is None:
        return ()
    return _embedded_source_candidates(connection, needle, kind="package")


def _embedded_source_candidates(
    connection: sqlite3.Connection, needle: str, *, kind: str
) -> tuple[SourceSearchCandidate, ...]:
    found: list[SourceSearchCandidate] = []
    for setup_id, version in _setup_versions(connection):
        document = _setup_definition(connection, setup_id, version)
        if document is None:
            continue
        raw = document.get("embedded")
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            snapshot = item.get("snapshot")
            passport = item.get("passport")
            if not isinstance(snapshot, dict) or not isinstance(passport, dict):
                continue
            if str(snapshot.get("kind") or "") != kind:
                continue
            name = str(passport.get("name") or "")
            coordinate = str(snapshot.get("canonical_coordinate") or "")
            if not _name_matches(needle, name) and not _name_matches(needle, coordinate):
                continue
            ref = item.get("ref")
            ref_id = ""
            if isinstance(ref, dict):
                ref_id = str(ref.get("stable_id") or "")
            found.append(
                SourceSearchCandidate(
                    name=name or coordinate,
                    source=kind,  # pyright: ignore[reportArgumentType]
                    exact_coordinate=coordinate,
                    catalog_status="not_in_catalog",
                    trust_lane="experimental",
                    author_verified=False,
                    component_verified=False,
                    stable_id=ref_id or None,
                )
            )
    return tuple(found)


def _setup_versions(connection: sqlite3.Connection) -> tuple[tuple[str, str], ...]:
    rows = connection.execute(
        "SELECT e.stable_id, v.version FROM entity e "
        "JOIN object_version v ON v.stable_id = e.stable_id WHERE e.kind = 'setup'"
    ).fetchall()
    return tuple((str(row["stable_id"]), str(row["version"])) for row in rows)


def _setup_definition(
    connection: sqlite3.Connection, stable_id: str, version: str
) -> dict[str, JsonValue] | None:
    recorded = versions.held(connection, stable_id, version)
    if recorded is None:
        return None
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None:
        return None
    document = stored.envelope.model_dump(mode="json")
    artifact = document.get("artifact")
    if not isinstance(artifact, dict):
        return None
    digest = artifact.get("digest")
    if not isinstance(digest, str):
        return None
    try:
        payload = content.get(connection, digest)
    except CliFailure:
        return None
    parsed = try_parse_setup_definition(payload)
    return parsed


def _name_matches(query: str, value: str) -> bool:
    if not value:
        return False
    return query.casefold() == value.casefold() or query.casefold() in value.casefold()


def _dedupe(candidates: Sequence[SourceSearchCandidate]) -> tuple[SourceSearchCandidate, ...]:
    seen: set[str] = set()
    ordered: list[SourceSearchCandidate] = []
    for item in candidates:
        key = f"{item.source}:{item.exact_coordinate}:{item.stable_id or ''}"
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return tuple(sorted(ordered, key=lambda item: (item.source, item.exact_coordinate, item.name)))
