"""The public catalogue and its cache, driven by the `#71` corpus."""

import json
from collections.abc import Iterator

import httpx
import pytest

from ai_stp_cli.cloud import catalog
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache
from ai_stp_contracts.fixtures import load_cases
from ai_stp_contracts.mock import MOCK_BASE_URL, build_transport
from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports.versions import ComponentVersionPassport


def mock() -> Endpoint:
    return Endpoint(MOCK_BASE_URL, transport=build_transport())


def _component_id() -> str:
    """The identifier the corpus actually serves a detail for."""
    for case in load_cases():
        if case.operation_id == "readComponent" and case.kind == "positive":
            return str(case.request.path_params["stable_id"])
    raise AssertionError("the corpus has no readComponent case")


#: The corpus serves component search only for this query; a bare search has
#: only `invalid_response` cases, which the mock refuses to answer by design.
SERVED_QUERY = "pytest"


def test_an_anonymous_search_returns_the_seeded_catalogue() -> None:
    result = catalog.search(mock(), "component", query=SERVED_QUERY)
    assert result.source == "online"
    assert result.kind == "component"
    assert result.checked_at.endswith("Z")
    # Search is not cached: a page is a view over a moving collection.
    assert not cache.cache_dir().exists()


def test_setups_and_components_are_separate_halves() -> None:
    setups = catalog.search(mock(), "setup")
    assert setups.kind == "setup"
    # `#71` gave each half its own route and its own cursor, so a page is about
    # one of them and never spans both.
    assert setups.next_cursor is None or isinstance(setups.next_cursor, str)


def test_the_experimental_lane_stays_in_its_own_section() -> None:
    # `ADR-0016`: an experimental candidate appearing among authoritative ones
    # would have been silently promoted.
    result = catalog.search(mock(), "component", query=SERVED_QUERY, include_experimental=True)
    assert not {item.stable_id for item in result.items} & {
        item.stable_id for item in result.experimental
    }


def test_showing_an_object_returns_it_and_caches_it() -> None:
    stable_id = _component_id()
    view = catalog.show(mock(), "component", stable_id)
    assert view.source == "online"
    assert view.summary.stable_id == stable_id
    assert view.versions
    # Versions are not contiguous by design: hiding one does not free its number.
    assert len({entry.version for entry in view.versions}) == len(view.versions)

    entry = cache.load(cache.key_for("component", stable_id))
    assert entry is not None
    assert entry.checked_at == view.checked_at


def test_an_unreachable_platform_falls_back_to_the_cache_and_says_so() -> None:
    stable_id = _component_id()
    fresh = catalog.show(mock(), "component", stable_id)

    def offline(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    cached = catalog.show(
        Endpoint(MOCK_BASE_URL, max_attempts=1, transport=httpx.MockTransport(offline)),
        "component",
        stable_id,
    )
    assert cached.source == "cache"
    assert cached.summary == fresh.summary
    # The moment the platform answered, not now: this is what stops a cached
    # view claiming to describe the current cloud state.
    assert cached.checked_at == fresh.checked_at


def test_an_unreachable_platform_with_nothing_cached_is_a_typed_failure() -> None:
    # `offline-capability.md` forbids turning absence of network into an empty
    # successful result.
    def offline(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(CliFailure) as raised:
        catalog.show(
            Endpoint(MOCK_BASE_URL, max_attempts=1, transport=httpx.MockTransport(offline)),
            "component",
            _component_id(),
        )
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


def test_an_answer_is_never_served_from_the_cache() -> None:
    # A 404 is a decision. Answering it from a stale cache would resurrect an
    # object the catalogue has stopped offering.
    stable_id = _component_id()
    catalog.show(mock(), "component", stable_id)

    def gone(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "AI_STP_NOT_FOUND", "message": "no"}})

    with pytest.raises(CliFailure) as raised:
        catalog.show(
            Endpoint(MOCK_BASE_URL, max_attempts=1, transport=httpx.MockTransport(gone)),
            "component",
            stable_id,
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_a_cache_key_is_safe_to_use_as_a_file_name() -> None:
    # An object name is not guaranteed to be a safe path segment, and a cache
    # whose file names are attacker-influenced is a traversal waiting to happen.
    hostile = cache.key_for("component", "../../etc/passwd")
    assert "/" not in hostile and ".." not in hostile
    assert cache.key_for("component", "a") != cache.key_for("setup", "a")


def test_a_cached_entry_round_trips_and_is_owner_only() -> None:
    from ai_stp_cli import paths

    key = cache.key_for("component", "example")
    assert cache.load(key) is None
    stored = cache.store(key, {"a": 1})
    assert cache.load(key) == stored
    written = next(cache.cache_dir().glob("*.json"))
    assert paths.is_private(written)
    from ai_stp_cli.paths import write_private

    write_private(cache.cache_dir() / f"{key}.json", '{"key": "x", "checked_at": "z"}')
    with pytest.raises(CliFailure):
        cache.load(key)


@pytest.mark.parametrize("damaged", ["{not json", '["a list"]', '{"key": "x"}'])
def test_a_damaged_cache_entry_is_refused_not_guessed(damaged: str) -> None:
    from ai_stp_cli import paths

    key = cache.key_for("component", "example")
    cache.store(key, {"a": 1})
    paths.write_private(cache.cache_dir() / f"{key}.json", damaged)
    with pytest.raises(CliFailure, match="cache entry is unreadable"):
        cache.load(key)


def test_a_digest_mismatch_is_rejected() -> None:
    # Independent of the transport: a truncated download and a substituted body
    # are the same thing to this check.
    document: JsonValue = {"passport": {"a": 1}}
    cache.verify(document, cache.digest_of(document))
    with pytest.raises(CliFailure, match="does not match the digest") as raised:
        cache.verify(document, "sha256:" + "0" * 64)
    assert raised.value.details["expected"] == "sha256:" + "0" * 64


def test_the_digest_is_domain_separated_as_the_catalogue_computes_it() -> None:
    # A bare hash of the canonical bytes would never match a conforming server,
    # and the failure would look like a corrupted download.
    import hashlib

    from ai_stp_foundation.canonical import canonize

    passport: JsonValue = {"schema_version": 1, "kind": "component"}
    computed = cache.digest_of(passport)
    assert computed.startswith("sha256:")
    assert computed != hashlib.sha256(canonize(passport)).hexdigest()


def test_a_truncated_document_does_not_verify() -> None:
    whole: JsonValue = {"items": [1, 2, 3]}
    truncated: JsonValue = {"items": [1, 2]}
    with pytest.raises(CliFailure, match="does not match the digest"):
        cache.verify(truncated, cache.digest_of(whole))


def test_the_catalogue_can_be_switched_off_and_says_so() -> None:
    from ai_stp_cli import config
    from ai_stp_cli.commands import registry as registry_commands

    path = config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("catalog:\n  enabled: false\n", encoding="utf-8")

    with pytest.raises(CliFailure, match="switched off") as raised:
        registry_commands.endpoint()
    # Offline is a supported configuration, not a fault the user must repair.
    assert raised.value.details["field"] == "catalog.enabled"


@pytest.mark.parametrize("given", [None, "widget"])
def test_an_unusable_kind_is_refused(given: object) -> None:
    from ai_stp_cli.commands import registry as registry_commands

    with pytest.raises(CliFailure, match="kind"):
        registry_commands.search({"kind": given})


def test_showing_without_an_identifier_is_refused() -> None:
    from ai_stp_cli.commands import registry as registry_commands

    with pytest.raises(CliFailure, match="identifier is required"):
        registry_commands.show({"kind": "component"})


def test_the_commands_read_and_write_nothing_local(monkeypatch: pytest.MonkeyPatch) -> None:
    # `#76`: a read command must not create a setup version or touch a harness
    # target. The registry file is the durable local state, and it stays absent.
    from ai_stp_cli.commands import registry as registry_commands
    from ai_stp_cli.local.database import configured_path

    monkeypatch.setattr(registry_commands, "endpoint", mock)
    registry_commands.search({"kind": "component", "query": SERVED_QUERY})
    registry_commands.show({"kind": "component", "id": _component_id()})
    assert not configured_path().exists()


def test_a_page_walk_visits_each_object_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # Two fixed pages, so the property under test is the walk itself rather than
    # the corpus: a cursor that repeated an object would be visible here.
    def page(next_cursor: str | None) -> dict[str, JsonValue]:
        return {
            "schema_version": 1,
            "items": [],
            "experimental": [],
            "page": {"schema_version": 1, "next_cursor": next_cursor, "page_size": 20},
        }

    pages: Iterator[dict[str, JsonValue]] = iter(
        [page("cursor000000000000000000000002"), page(None)]
    )
    seen: list[str | None] = []

    def paged(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get("cursor"))
        return httpx.Response(200, json=next(pages))

    endpoint = Endpoint(MOCK_BASE_URL, transport=httpx.MockTransport(paged))
    first = catalog.search(endpoint, "component")
    assert first.next_cursor is not None
    second = catalog.search(endpoint, "component", cursor=first.next_cursor)
    assert second.next_cursor is None
    # The cursor is echoed back opaquely and never constructed by the client.
    assert seen == [None, first.next_cursor]


def _version_case() -> tuple[str, str]:
    """The object and version the corpus serves a passport for."""
    for case in load_cases():
        if case.operation_id == "readComponentVersion" and case.kind == "positive":
            params = case.request.path_params
            return str(params["stable_id"]), str(params["version"])
    raise AssertionError("the corpus has no readComponentVersion case")


def test_an_exact_version_is_verified_against_its_published_digest() -> None:
    stable_id, number = _version_case()
    view = catalog.version(mock(), "component", stable_id, number)
    assert view.source == "online"
    assert view.passport_digest.startswith("sha256:")
    assert view.passport
    # The check is the point of fetching a version at all.
    assert cache.digest_of(view.passport) == view.passport_digest


def test_a_version_digest_is_over_the_wire_passport_not_a_model_dump() -> None:
    """A historical passport omitting later defaults must still verify.

    Dumping the validated model injects an omitted optional provenance field,
    which is a different document from the one the catalogue hashed.
    """
    served = next(
        case
        for case in load_cases()
        if case.operation_id == "readComponentVersion" and case.kind == "positive"
    )
    body = json.loads(json.dumps(served.body))
    body["passport"].pop("origin_harness_id", None)
    body["passport_digest"] = cache.digest_of(body["passport"])
    dumped = ComponentVersionPassport.model_validate(body["passport"]).model_dump(mode="json")
    assert cache.digest_of(dumped) != body["passport_digest"]

    def historical(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    view = catalog.version(
        Endpoint(MOCK_BASE_URL, max_attempts=1, transport=httpx.MockTransport(historical)),
        "component",
        str(served.request.path_params["stable_id"]),
        str(served.request.path_params["version"]),
    )
    assert "origin_harness_id" not in view.passport
    assert cache.digest_of(view.passport) == view.passport_digest
    cached = cache.load(
        cache.key_for(
            "component-version",
            f"{served.request.path_params['stable_id']}@{served.request.path_params['version']}",
        )
    )
    assert cached is not None
    assert cached.document["passport"] == view.passport


def test_a_substituted_passport_is_refused_and_not_cached() -> None:
    stable_id, number = _version_case()
    served = next(
        case
        for case in load_cases()
        if case.operation_id == "readComponentVersion" and case.kind == "positive"
    )
    tampered = json.loads(json.dumps(served.body))
    # A change the passport really did not have. Picking a field that already
    # held this value would have made the test pass while proving nothing.
    assert tampered["passport"]["name"] != "substituted"
    tampered["passport"]["name"] = "substituted"

    def substituted(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=tampered)

    with pytest.raises(CliFailure, match="does not match the digest"):
        catalog.version(
            Endpoint(MOCK_BASE_URL, max_attempts=1, transport=httpx.MockTransport(substituted)),
            "component",
            stable_id,
            number,
        )
    key = cache.key_for("component-version", f"{stable_id}@{number}")
    assert cache.load(key) is None


def test_a_cached_version_is_verified_again_on_the_way_out() -> None:
    # A check performed only on arrival protects only the arrival; a cache entry
    # can be edited on disk afterwards.
    stable_id, number = _version_case()
    catalog.version(mock(), "component", stable_id, number)

    key = cache.key_for("component-version", f"{stable_id}@{number}")
    entry = cache.load(key)
    assert entry is not None
    document = json.loads(json.dumps(entry.document))
    assert document["passport"]["name"] != "edited on disk"
    document["passport"]["name"] = "edited on disk"
    cache.store(key, document, checked_at=entry.checked_at)

    def offline(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(CliFailure, match="does not match the digest"):
        catalog.version(
            Endpoint(MOCK_BASE_URL, max_attempts=1, transport=httpx.MockTransport(offline)),
            "component",
            stable_id,
            number,
        )


def test_a_version_falls_back_to_a_sound_cache_when_the_platform_is_away() -> None:
    stable_id, number = _version_case()
    fresh = catalog.version(mock(), "component", stable_id, number)

    def offline(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    cached = catalog.version(
        Endpoint(MOCK_BASE_URL, max_attempts=1, transport=httpx.MockTransport(offline)),
        "component",
        stable_id,
        number,
    )
    assert cached.source == "cache"
    assert cached.checked_at == fresh.checked_at
    assert cached.passport == fresh.passport


def test_a_version_needs_both_an_identifier_and_a_number() -> None:
    from ai_stp_cli.commands import registry as registry_commands

    with pytest.raises(CliFailure, match="both required"):
        registry_commands.version({"kind": "component", "id": "x"})


def test_a_version_the_catalogue_refuses_is_not_served_from_the_cache() -> None:
    stable_id, number = _version_case()
    catalog.version(mock(), "component", stable_id, number)

    def gone(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "AI_STP_NOT_FOUND", "message": "no"}})

    with pytest.raises(CliFailure) as raised:
        catalog.version(
            Endpoint(MOCK_BASE_URL, max_attempts=1, transport=httpx.MockTransport(gone)),
            "component",
            stable_id,
            number,
        )
    assert raised.value.code == "AI_STP_NOT_FOUND"


def test_a_version_with_nothing_cached_and_no_platform_is_a_typed_failure() -> None:
    def offline(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    stable_id, number = _version_case()
    with pytest.raises(CliFailure) as raised:
        catalog.version(
            Endpoint(MOCK_BASE_URL, max_attempts=1, transport=httpx.MockTransport(offline)),
            "component",
            stable_id,
            number,
        )
    assert raised.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


def test_a_setup_version_takes_the_same_path() -> None:
    from ai_stp_contracts.fixtures import load_cases as cases

    served = next(
        c for c in cases() if c.operation_id == "readSetupVersion" and c.kind == "positive"
    )
    params = served.request.path_params
    view = catalog.version(mock(), "setup", str(params["stable_id"]), str(params["version"]))
    assert view.kind == "setup"
    assert cache.digest_of(view.passport) == view.passport_digest


def test_an_out_of_range_limit_names_the_flag_a_person_typed() -> None:
    """A refusal that names a wire field sends somebody looking for it.

    `--limit 200` travelled to the platform unchecked and came back as
    `a supplied value is not valid for this command: page_size` — a field that
    appears in no help text and on no command line. The bound is a published
    contract constant, so the CLI can refuse locally and say which flag and
    which maximum, without a round trip that only fails.
    """
    from ai_stp_cli.commands import registry as registry_commands

    with pytest.raises(CliFailure) as caught:
        registry_commands.search({"kind": "component", "limit": 200})
    assert caught.value.code == "AI_STP_VALIDATION_ERROR"
    assert "--limit" in caught.value.message
    assert caught.value.details["maximum"] == "100"
    with pytest.raises(CliFailure) as zero:
        registry_commands.search({"kind": "component", "limit": 0})
    assert "--limit" in zero.value.message
    assert zero.value.details["maximum"] == "100"
