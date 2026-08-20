"""Anonymous public catalogue reads (issue #76).

No account and no device key: these are the endpoints `#71` froze as public, and
the first useful cloud feature is meant to work before anyone signs in.

Three states, and they are stated rather than blurred. `online` is what the
platform said just now. `cache` is what it said at a named moment in the past —
not a degraded `online`, which is why `checked_at` travels with it. And an
unavailable platform with nothing cached is a typed failure, not an empty page:
`offline-capability.md` forbids turning absence of network into an empty
successful result.
"""

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import httpx

from ai_stp_cli.cloud import client
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache
from ai_stp_cli.paths import ensure_directory
from ai_stp_contracts.catalog import (
    ComponentDetail,
    ComponentListResponse,
    ComponentSearchRequest,
    ComponentVersionResponse,
    SetupDetail,
    SetupListResponse,
    SetupSearchRequest,
    SetupVersionResponse,
)
from ai_stp_contracts.http import PAGE_SIZE_DEFAULT
from ai_stp_contracts.machine_help import (
    AnswerSource,
    CatalogKind,
    CatalogObjectView,
    CatalogSearchResult,
    CatalogVersionView,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_passports.versions import ArtifactRef

#: Codes that mean the platform is not reachable right now. Only these fall back
#: to the cache: a 404 is an answer, and answering it from a stale cache would
#: resurrect an object the catalogue has stopped offering.
UNREACHABLE: frozenset[str] = frozenset(
    {"AI_STP_DEPENDENCY_UNAVAILABLE", "AI_STP_TIMEOUT_UNCONFIRMED", "AI_STP_RATE_LIMITED"}
)


def _moment() -> str:
    return format_timestamp(datetime.now(UTC))


def search(
    endpoint: Endpoint,
    kind: CatalogKind,
    *,
    query: str | None = None,
    cursor: str | None = None,
    page_size: int | None = None,
    include_experimental: bool = False,
) -> CatalogSearchResult:
    """One page of public results.

    Search is not cached. A page is a view over a moving collection, and serving
    yesterday's page as today's would break the one property pagination has to
    keep: that walking the cursors visits each object once.
    """
    path = "/catalog/components" if kind == "component" else "/catalog/setups"
    # `page_size` has a contract default; passing `None` would ask the model to
    # accept a value the schema rejects, so the default is left in place instead.
    bounded = PAGE_SIZE_DEFAULT if page_size is None else page_size
    request = (
        ComponentSearchRequest(
            q=query,
            tags=[],
            cursor=cursor,
            page_size=bounded,
            include_experimental=include_experimental,
        )
        if kind == "component"
        else SetupSearchRequest(
            q=query,
            tags=[],
            cursor=cursor,
            page_size=bounded,
            include_experimental=include_experimental,
        )
    )
    model = ComponentListResponse if kind == "component" else SetupListResponse
    with client.open_client(endpoint) as http:
        answer = client.call(
            http,
            "GET",
            path,
            model,  # pyright: ignore[reportArgumentType]
            # Preserve the frozen #71 query shape when callers accept the new
            # filters' defaults.  Explicit false/relevance do not narrow the
            # catalogue and older contract fixtures never sent them.
            query=client.as_query(
                request,
                omit=frozenset({"schema_version", "verified_only", "sort", "sort_direction"}),
            ),
            attempts=endpoint.max_attempts,
        )
    return CatalogSearchResult(
        kind=kind,
        source="online",
        checked_at=_moment(),
        items=list(answer.items),
        experimental=list(answer.experimental),
        next_cursor=answer.page.next_cursor,
    )


def show(endpoint: Endpoint, kind: CatalogKind, stable_id: str) -> CatalogObjectView:
    """One object with its versions, from the platform or from the cache."""
    key = cache.key_for(kind, stable_id)
    path = f"/catalog/{'components' if kind == 'component' else 'setups'}/{stable_id}"
    model = ComponentDetail if kind == "component" else SetupDetail
    try:
        with client.open_client(endpoint) as http:
            detail = client.call(
                http,
                "GET",
                path,
                model,  # pyright: ignore[reportArgumentType]
                attempts=endpoint.max_attempts,
            )
    except CliFailure as failure:
        if failure.code not in UNREACHABLE:
            # An answer, not an outage. Serving it from the cache would
            # resurrect an object the catalogue has stopped offering.
            raise
        return _from_cache(kind, stable_id, key, failure)

    # One moment, written to the cache and reported in the answer. Two calls to
    # the clock would make a later cached read claim a time the platform never
    # answered at.
    checked_at = _moment()
    document = cast(dict[str, JsonValue], detail.model_dump(mode="json"))
    cache.store(key, document, checked_at=checked_at)
    return CatalogObjectView(
        kind=kind,
        source="online",
        checked_at=checked_at,
        summary=detail.summary,
        versions=list(detail.versions),
    )


def version(
    endpoint: Endpoint, kind: CatalogKind, stable_id: str, number: str
) -> CatalogVersionView:
    """One exact version, with its passport verified against the published digest.

    The verification is the point of fetching a version at all: a passport the
    catalogue promised under a digest that does not describe it is either a
    truncated download or a substituted body, and the two are the same thing to
    a client. Neither is cached.
    """
    path = (
        f"/catalog/{'components' if kind == 'component' else 'setups'}"
        f"/{stable_id}/versions/{number}"
    )
    model = ComponentVersionResponse if kind == "component" else SetupVersionResponse
    key = cache.key_for(f"{kind}-version", f"{stable_id}@{number}")
    try:
        with client.open_client(endpoint) as http:
            answer = client.call(
                http,
                "GET",
                path,
                model,  # pyright: ignore[reportArgumentType]
                attempts=endpoint.max_attempts,
            )
    except CliFailure as failure:
        if failure.code not in UNREACHABLE:
            raise
        return _version_from_cache(kind, key, failure)

    # Serialized, not the model: the digest is computed over the published
    # bytes, and a model instance is not what the catalogue hashed.
    passport = cast(dict[str, JsonValue], answer.passport.model_dump(mode="json"))
    cache.verify(passport, answer.passport_digest)
    checked_at = _moment()
    cache.store(
        key, cast(dict[str, JsonValue], answer.model_dump(mode="json")), checked_at=checked_at
    )
    return _version_view(kind, answer, "online", checked_at)


def _version_view(
    kind: CatalogKind,
    answer: ComponentVersionResponse | SetupVersionResponse,
    source: AnswerSource,
    checked_at: str,
) -> CatalogVersionView:
    return CatalogVersionView(
        kind=kind,
        source=source,
        checked_at=checked_at,
        passport_digest=answer.passport_digest,
        lifecycle=answer.lifecycle,
        trust=answer.trust,
        published_at=answer.published_at,
        passport=cast(dict[str, JsonValue], answer.passport.model_dump(mode="json")),
    )


def _version_from_cache(kind: CatalogKind, key: str, failure: CliFailure) -> CatalogVersionView:
    entry = cache.load(key)
    if entry is None:
        raise failure
    model = ComponentVersionResponse if kind == "component" else SetupVersionResponse
    answer = model.model_validate(entry.document)
    # Verified again on the way out: a cache entry can be edited on disk, and a
    # check performed only on arrival protects only the arrival.
    cache.verify(
        cast(dict[str, JsonValue], answer.passport.model_dump(mode="json")),
        answer.passport_digest,
    )
    return _version_view(kind, answer, "cache", entry.checked_at)


def cached_version(kind: CatalogKind, stable_id: str, number: str) -> CatalogVersionView:
    """Read one previously verified exact version without opening a socket."""
    key = cache.key_for(f"{kind}-version", f"{stable_id}@{number}")
    failure = CliFailure(
        "AI_STP_DEPENDENCY_UNAVAILABLE",
        "the exact catalogue version is not available in the verified cache",
        details={"kind": kind, "stable_id": stable_id, "version": number},
        next_actions=[f"registry acquire --id {stable_id} --version {number} --json"],
    )
    return _version_from_cache(kind, key, failure)


def _from_cache(
    kind: CatalogKind, stable_id: str, key: str, failure: CliFailure
) -> CatalogObjectView:
    entry = cache.load(key)
    if entry is None:
        raise failure
    model = ComponentDetail if kind == "component" else SetupDetail
    detail = model.model_validate(entry.document)
    return CatalogObjectView(
        kind=kind,
        source="cache",
        # The moment the platform answered, not now: this is what stops a cached
        # view claiming to describe the current cloud state.
        checked_at=entry.checked_at,
        summary=detail.summary,
        versions=list(detail.versions),
    )


def fetch_artifact(
    endpoint: Endpoint,
    kind: CatalogKind,
    stable_id: str,
    version_number: str,
    expected: ArtifactRef,
    *,
    transport: httpx.BaseTransport | None = None,
) -> Path:
    """Fetch the exact bytes of one version, verified, into the local cache.

    Verified against the **passport**, not against the response. Headers from
    the same server that sent the bytes cannot attest to them; the passport is
    the versioned, content-addressed description the client already holds, and
    checking against it is what makes a public catalogue an install source
    rather than a demonstration.

    Streamed rather than read whole. An artifact is the one payload here with no
    modelled upper bound, so a server — or something between — could otherwise
    answer with as much as it liked and the client would hold all of it. The
    stream stops the moment more has arrived than the passport declares.

    A cache hit is returned without a request. `object_key` is never asked for
    and never accepted: an opaque storage key is not authority to read (`SPEC-020`
    REQ-2004), and the route is the only way in.
    """
    held = cache.stored_version_artifact(expected.digest)
    if held is not None:
        return held

    path = f"/catalog/{'components' if kind == 'component' else 'setups'}/{stable_id}"
    path = f"{path}/versions/{version_number}/artifact"
    directory = cache.version_artifact_path(expected.digest).parent
    ensure_directory(directory)
    handle, temporary = tempfile.mkstemp(dir=directory, prefix=".artifact.")
    scratch = Path(temporary)

    try:
        with (
            client.open_client(endpoint, transport=transport) as http,
            os.fdopen(handle, "wb") as sink,
            http.stream("GET", path) as answer,
        ):
            if answer.status_code != 200:
                answer.read()
                raise client.failure_from(answer)
            received = 0
            for block in answer.iter_bytes():
                received += len(block)
                if received > expected.size_bytes:
                    raise _oversized(expected.size_bytes, received)
                sink.write(block)
        return cache.keep_version_artifact(scratch, expected)
    except BaseException:
        scratch.unlink(missing_ok=True)
        raise


def _oversized(declared: int, received: int) -> CliFailure:
    return CliFailure(
        "AI_STP_PRECONDITION_FAILED",
        "the artifact is larger than its passport declares",
        details={"expected": str(declared), "received_at_least": str(received)},
        next_actions=["registry version --json"],
    )
