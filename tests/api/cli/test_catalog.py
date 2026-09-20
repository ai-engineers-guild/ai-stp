"""Catalog journeys: the real `/v1` catalog over the frozen seed corpus.

`load_fixture_seed` writes the same `#71` contract objects the corpus mock
serves, so the journeys that used to run against `build_transport()` now run
against the application itself. What stays in `tests/unit/test_cli_catalog.py`
is client-boundary behaviour — cursor opacity, a private lane, tampering, and
local cache validation — where a mock transport is the fault being injected,
not a fake server.
"""

from __future__ import annotations

import json

import httpx
import pytest
from tests.support.catalog_seed import FIXTURE_COMPONENT_ID, FIXTURE_SETUP_ID

from ai_stp_cli.cloud import catalog
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache


def _offline() -> Endpoint:
    """An endpoint whose transport is down — client-side fault injection."""

    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    return Endpoint("http://127.0.0.1", max_attempts=1, transport=httpx.MockTransport(down))


def test_anonymous_browse_returns_the_seeded_catalogue(
    cli_endpoint: Endpoint, seeded_catalog: None
) -> None:
    result = catalog.search(cli_endpoint, "component")
    assert result.source == "online"
    assert result.kind == "component"
    assert result.checked_at.endswith("Z")
    # The Sprint-1 seed is entirely experimental: without consent both lanes
    # are empty, because authoritative promotion is a decision, not a default.
    assert result.items == []
    assert result.experimental == []
    # Search is not cached: a page is a view over a moving collection.
    assert not cache.cache_dir().exists()


def test_the_experimental_lane_stays_in_its_own_section(
    cli_endpoint: Endpoint, seeded_catalog: None
) -> None:
    # `ADR-0016`: an experimental candidate appearing among authoritative ones
    # would have been silently promoted.
    result = catalog.search(cli_endpoint, "component", include_experimental=True)
    assert len(result.experimental) >= 1
    assert not {item.stable_id for item in result.items} & {
        item.stable_id for item in result.experimental
    }


def test_setups_and_components_are_separate_halves(
    cli_endpoint: Endpoint, seeded_catalog: None
) -> None:
    setups = catalog.search(cli_endpoint, "setup", include_experimental=True)
    assert setups.kind == "setup"
    assert len(setups.experimental) >= 1
    assert setups.next_cursor is None or isinstance(setups.next_cursor, str)


def test_showing_an_object_returns_it_and_caches_it(
    cli_endpoint: Endpoint, seeded_catalog: None
) -> None:
    view = catalog.show(cli_endpoint, "component", FIXTURE_COMPONENT_ID)
    assert view.source == "online"
    assert view.summary.stable_id == FIXTURE_COMPONENT_ID
    # The corpus pins two versions; hiding one does not free its number.
    assert {entry.version for entry in view.versions} == {"1.0", "1.2"}

    entry = cache.load(cache.key_for("component", FIXTURE_COMPONENT_ID))
    assert entry is not None
    assert entry.checked_at == view.checked_at


def test_an_unreachable_platform_falls_back_to_the_cache_and_says_so(
    cli_endpoint: Endpoint, seeded_catalog: None
) -> None:
    fresh = catalog.show(cli_endpoint, "component", FIXTURE_COMPONENT_ID)

    cached = catalog.show(_offline(), "component", FIXTURE_COMPONENT_ID)
    assert cached.source == "cache"
    assert cached.summary == fresh.summary
    # The moment the platform answered, not now: this is what stops a cached
    # view claiming to describe the current cloud state.
    assert cached.checked_at == fresh.checked_at


def test_an_unreachable_platform_with_nothing_cached_is_a_typed_failure(
    seeded_catalog: None,
) -> None:
    # `offline-capability.md` forbids turning absence of network into an empty
    # successful result.
    with pytest.raises(CliFailure) as raised:
        catalog.show(_offline(), "component", FIXTURE_COMPONENT_ID)
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


def test_an_answer_is_never_served_from_the_cache(
    cli_endpoint: Endpoint, seeded_catalog: None
) -> None:
    # A 404 is a decision. Answering it from a stale cache would resurrect an
    # object the catalogue has stopped offering.
    catalog.show(cli_endpoint, "component", FIXTURE_COMPONENT_ID)

    def gone(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "AI_STP_NOT_FOUND", "message": "no"}})

    with pytest.raises(CliFailure) as raised:
        catalog.show(
            Endpoint("http://127.0.0.1", max_attempts=1, transport=httpx.MockTransport(gone)),
            "component",
            FIXTURE_COMPONENT_ID,
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_an_exact_version_is_verified_against_its_published_digest(
    cli_endpoint: Endpoint, seeded_catalog: None
) -> None:
    view = catalog.version(cli_endpoint, "component", FIXTURE_COMPONENT_ID, "1.2")
    assert view.source == "online"
    assert view.passport_digest.startswith("sha256:")
    assert view.passport
    # The check is the point of fetching a version at all.
    assert cache.digest_of(view.passport) == view.passport_digest


def test_a_setup_version_takes_the_same_path(cli_endpoint: Endpoint, seeded_catalog: None) -> None:
    view = catalog.version(cli_endpoint, "setup", FIXTURE_SETUP_ID, "1.0")
    assert view.kind == "setup"
    assert cache.digest_of(view.passport) == view.passport_digest


def test_a_cached_version_is_verified_again_on_the_way_out(
    cli_endpoint: Endpoint, seeded_catalog: None
) -> None:
    # A check performed only on arrival protects only the arrival; a cache
    # entry can be edited on disk afterwards.
    catalog.version(cli_endpoint, "component", FIXTURE_COMPONENT_ID, "1.2")

    key = cache.key_for("component-version", f"{FIXTURE_COMPONENT_ID}@1.2")
    entry = cache.load(key)
    assert entry is not None
    document = json.loads(json.dumps(entry.document))
    assert document["passport"]["name"] != "edited on disk"
    document["passport"]["name"] = "edited on disk"
    cache.store(key, document, checked_at=entry.checked_at)

    with pytest.raises(CliFailure, match="does not match the digest"):
        catalog.version(_offline(), "component", FIXTURE_COMPONENT_ID, "1.2")


def test_a_version_falls_back_to_a_sound_cache_when_the_platform_is_away(
    cli_endpoint: Endpoint, seeded_catalog: None
) -> None:
    fresh = catalog.version(cli_endpoint, "component", FIXTURE_COMPONENT_ID, "1.2")

    cached = catalog.version(_offline(), "component", FIXTURE_COMPONENT_ID, "1.2")
    assert cached.source == "cache"
    assert cached.checked_at == fresh.checked_at
    assert cached.passport == fresh.passport


def test_a_version_the_catalogue_refuses_is_not_served_from_the_cache(
    cli_endpoint: Endpoint, seeded_catalog: None
) -> None:
    catalog.version(cli_endpoint, "component", FIXTURE_COMPONENT_ID, "1.2")

    def gone(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "AI_STP_NOT_FOUND", "message": "no"}})

    with pytest.raises(CliFailure) as raised:
        catalog.version(
            Endpoint("http://127.0.0.1", max_attempts=1, transport=httpx.MockTransport(gone)),
            "component",
            FIXTURE_COMPONENT_ID,
            "1.2",
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_the_commands_read_and_write_nothing_local(
    cli_endpoint: Endpoint,
    seeded_catalog: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `#76`: a read command must not create a setup version or touch a harness
    # target. The registry file is the durable local state, and it stays absent.
    from ai_stp_cli.application import catalog as registry_commands
    from ai_stp_cli.local.database import configured_path

    monkeypatch.setattr(registry_commands, "endpoint", lambda: cli_endpoint)
    registry_commands.search({"kind": "component", "query": "fixture"})
    registry_commands.show({"kind": "component", "id": FIXTURE_COMPONENT_ID})
    assert not configured_path().exists()
