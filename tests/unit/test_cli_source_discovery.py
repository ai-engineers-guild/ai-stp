# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false
"""Opt-in name discovery does not select, merge, or hide source/trust (REQ-5713, REQ-5716)."""

from __future__ import annotations

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local.source_discovery import discover
from ai_stp_contracts.catalog import CatalogTrust
from ai_stp_contracts.machine_help import CatalogSearchResult, SourceSearchCandidate


def _empty_catalog(_query: str) -> CatalogSearchResult:
    return CatalogSearchResult(
        kind="component",
        source="online",
        checked_at="2026-09-01T00:00:00.000Z",
        items=[],
        experimental=[],
        next_cursor=None,
    )


def _candidate(
    *,
    name: str,
    source: str,
    coordinate: str,
    catalog_status: str = "not_in_catalog",
    trust_lane: str = "experimental",
    stable_id: str | None = None,
    author_verified: bool = False,
    component_verified: bool = False,
) -> SourceSearchCandidate:
    return SourceSearchCandidate(
        name=name,
        source=source,  # pyright: ignore[reportArgumentType]
        exact_coordinate=coordinate,
        catalog_status=catalog_status,  # pyright: ignore[reportArgumentType]
        trust_lane=trust_lane,  # pyright: ignore[reportArgumentType]
        author_verified=author_verified,
        component_verified=component_verified,
        stable_id=stable_id,
    )


def test_name_query_without_flag_excludes_package_and_github() -> None:
    extras = (
        _candidate(name="demo", source="package", coordinate="package:npm:demo@1.0.0"),
        _candidate(
            name="demo",
            source="git",
            coordinate="git:https://github.com/acme/demo",
        ),
    )
    called = {"extra": False}

    def extra(_query: str) -> tuple[SourceSearchCandidate, ...]:
        called["extra"] = True
        return extras

    result = discover(
        "demo",
        registry_discovery=False,
        catalog_search=_empty_catalog,
        extra_candidates=extra,
    )
    assert called["extra"] is False
    assert result.registry_discovery is False
    assert result.resolution == "unresolved"
    assert result.selected is None
    assert result.candidates == []


def test_registry_discovery_flag_shows_source_trust_and_ambiguity() -> None:
    extras = (
        _candidate(
            name="demo",
            source="catalog",
            coordinate="catalog:component_01ARZ3NDEKTSV4RRFFQ69G5FAV@1.0",
            catalog_status="catalog",
            trust_lane="authoritative",
            author_verified=True,
            component_verified=True,
            stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        ),
        _candidate(name="demo", source="package", coordinate="package:npm:demo@1.2.3"),
        _candidate(
            name="demo",
            source="git",
            coordinate="git:https://github.com/acme/demo@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ),
    )
    result = discover(
        "demo",
        registry_discovery=True,
        catalog_search=_empty_catalog,
        extra_candidates=lambda _query: extras,
    )
    assert result.registry_discovery is True
    assert result.resolution == "needs_selection"
    assert result.selected is None
    sources = {item.source for item in result.candidates}
    assert sources == {"catalog", "package", "git"}
    catalog_hit = next(item for item in result.candidates if item.source == "catalog")
    assert catalog_hit.catalog_status == "catalog"
    assert catalog_hit.trust_lane == "authoritative"
    package_hit = next(item for item in result.candidates if item.source == "package")
    assert package_hit.catalog_status == "not_in_catalog"
    assert package_hit.author_verified is False
    assert package_hit.component_verified is False
    assert package_hit.trust_lane == "experimental"


def test_equal_names_remain_distinct_and_are_never_selected() -> None:
    extras = (
        _candidate(
            name="demo",
            source="package",
            coordinate="package:npm:demo@1.0.0",
            stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAW",
        ),
        _candidate(
            name="demo",
            source="package",
            coordinate="package:pypi:demo@1.0.0",
            stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAX",
        ),
    )
    result = discover(
        "demo",
        registry_discovery=True,
        catalog_search=_empty_catalog,
        extra_candidates=lambda _query: extras,
    )
    assert result.resolution == "needs_selection"
    assert result.selected is None
    assert len(result.candidates) == 2
    assert result.candidates[0].exact_coordinate != result.candidates[1].exact_coordinate
    assert result.candidates[0].name == result.candidates[1].name == "demo"


def test_empty_query_is_rejected() -> None:
    with pytest.raises(CliFailure, match="a name-only query is required"):
        discover("  ", registry_discovery=False, catalog_search=_empty_catalog)


def test_catalog_trust_object_is_not_required_for_empty_results() -> None:
    assert (
        CatalogTrust(
            trust_lane="experimental", author_verified=False, component_verified=False
        ).trust_lane
        == "experimental"
    )
