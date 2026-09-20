"""Client-boundary catalogue behaviour: injected transports, corpus wire bodies.

The browse/show/version journeys moved to `tests/api/cli/test_catalog.py`,
which serves the frozen corpus from the real `/v1` application. What remains
here exercises the client against conditions a server cannot be asked to
produce — dropped connections, tampered bodies, cursor opacity — plus the
local cache's own rules.
"""

import json
from collections.abc import Iterator

import httpx
import pytest

from ai_stp_cli.cloud import catalog
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache
from ai_stp_contracts.fixtures import load_cases
from ai_stp_contracts.mock import MOCK_BASE_URL
from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentVersionPassport


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
    from ai_stp_cli.application import catalog as registry_commands

    path = config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("catalog:\n  enabled: false\n", encoding="utf-8")

    with pytest.raises(CliFailure, match="switched off") as raised:
        registry_commands.endpoint()
    # Offline is a supported configuration, not a fault the user must repair.
    assert raised.value.details["field"] == "catalog.enabled"


@pytest.mark.parametrize("given", [None, "widget"])
def test_an_unusable_kind_is_refused(given: object) -> None:
    from ai_stp_cli.application import catalog as registry_commands

    with pytest.raises(CliFailure, match="kind"):
        registry_commands.search({"kind": given})


def test_showing_without_an_identifier_is_refused() -> None:
    from ai_stp_cli.application import catalog as registry_commands

    with pytest.raises(CliFailure, match="identifier is required"):
        registry_commands.show({"kind": "component"})


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


def test_an_authorized_private_version_never_populates_the_anonymous_cache() -> None:
    served = next(
        case
        for case in load_cases()
        if case.operation_id == "readComponentVersion" and case.kind == "positive"
    )
    body = json.loads(json.dumps(served.body))
    passport = body["passport"]
    passport["visibility"] = "private"
    passport["revision_id"] = derive_revision_id(passport)
    body["passport_digest"] = cache.digest_of(passport)
    body["trust"]["trust_lane"] = "local_owner_or_pinned"
    body["visibility"] = "private"
    asked: list[tuple[str, str | None]] = []

    def private_only(request: httpx.Request) -> httpx.Response:
        asked.append((request.url.path, request.headers.get("authorization")))
        if request.url.path.endswith("/private"):
            return httpx.Response(200, json=body)
        return httpx.Response(
            404, json={"error": {"code": "AI_STP_NOT_FOUND", "message": "not public"}}
        )

    params = served.request.path_params
    where = Endpoint(
        MOCK_BASE_URL,
        max_attempts=1,
        transport=httpx.MockTransport(private_only),
    )
    view = catalog.version(
        where,
        "component",
        str(params["stable_id"]),
        str(params["version"]),
        access_token="private-token",
    )

    assert view.passport["visibility"] == "private"
    assert asked == [
        (
            f"/v1/catalog/components/{params['stable_id']}/versions/{params['version']}",
            None,
        ),
        (
            f"/v1/catalog/components/{params['stable_id']}/versions/{params['version']}/private",
            "Bearer private-token",
        ),
    ]

    def offline(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(CliFailure) as unavailable:
        catalog.version(
            Endpoint(MOCK_BASE_URL, max_attempts=1, transport=httpx.MockTransport(offline)),
            "component",
            str(params["stable_id"]),
            str(params["version"]),
        )
    assert unavailable.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    with pytest.raises(CliFailure) as missing:
        catalog.cached_version("component", str(params["stable_id"]), str(params["version"]))

    assert missing.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"


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


def test_a_version_needs_both_an_identifier_and_a_number() -> None:
    from ai_stp_cli.application import catalog as registry_commands

    with pytest.raises(CliFailure, match="both required"):
        registry_commands.version({"kind": "component", "id": "x"})


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


def test_an_out_of_range_limit_names_the_flag_a_person_typed() -> None:
    """A refusal that names a wire field sends somebody looking for it.

    `--limit 200` travelled to the platform unchecked and came back as
    `a supplied value is not valid for this command: page_size` — a field that
    appears in no help text and on no command line. The bound is a published
    contract constant, so the CLI can refuse locally and say which flag and
    which maximum, without a round trip that only fails.
    """
    from ai_stp_cli.application import catalog as registry_commands

    with pytest.raises(CliFailure) as caught:
        registry_commands.search({"kind": "component", "limit": 200})
    assert caught.value.code == "AI_STP_VALIDATION_ERROR"
    assert "--limit" in caught.value.message
    assert caught.value.details["maximum"] == "100"
    with pytest.raises(CliFailure) as zero:
        registry_commands.search({"kind": "component", "limit": 0})
    assert "--limit" in zero.value.message
    assert zero.value.details["maximum"] == "100"
