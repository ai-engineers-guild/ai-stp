"""Official sync acquisition through the shared source resolver (REQ-5608, REQ-5715)."""

from __future__ import annotations

from datetime import datetime

from ai_stp_platform.models import OfficialUpstreamSource
from ai_stp_platform.official_upstream.errors import (
    FAILED_VALIDATION,
    INVALID_SOURCE,
    UNAVAILABLE_UPSTREAM,
    UNSAFE_ARCHIVE,
    OfficialUpstreamError,
)
from ai_stp_platform.official_upstream.github import FetchFn, default_fetch, worker_github_token
from ai_stp_sources.errors import (
    AMBIGUOUS_DISTRIBUTION,
    FLOATING_FROZEN_SOURCE,
    INTEGRITY_MISMATCH,
    UNAVAILABLE_SOURCE,
    UNSUPPORTED_SOURCE,
    SourceError,
)
from ai_stp_sources.errors import INVALID_SOURCE as SOURCE_INVALID
from ai_stp_sources.errors import UNSAFE_ARCHIVE as SOURCE_UNSAFE
from ai_stp_sources.models import GitIntent, PackageIntent, SourceSnapshot
from ai_stp_sources.resolve import resolve_source

_SOURCE_ERROR_MAP = {
    SOURCE_INVALID: INVALID_SOURCE,
    UNSUPPORTED_SOURCE: INVALID_SOURCE,
    UNAVAILABLE_SOURCE: UNAVAILABLE_UPSTREAM,
    SOURCE_UNSAFE: UNSAFE_ARCHIVE,
    INTEGRITY_MISMATCH: FAILED_VALIDATION,
    AMBIGUOUS_DISTRIBUTION: INVALID_SOURCE,
    FLOATING_FROZEN_SOURCE: UNAVAILABLE_UPSTREAM,
}


def source_intent(source: OfficialUpstreamSource) -> GitIntent | PackageIntent:
    """Build the shared intent for one operator-managed source row."""
    if source.kind == "package":
        if not source.ecosystem or not source.package_name or not source.package_version:
            raise OfficialUpstreamError(INVALID_SOURCE, "package source fields are incomplete")
        return PackageIntent(
            ecosystem=source.ecosystem,  # type: ignore[arg-type]
            name=source.package_name,
            version=source.package_version,
            filename=source.package_filename,
            platform=source.package_platform,
        )
    if not source.repository_url or not source.tracked_ref or not source.component_subpath:
        raise OfficialUpstreamError(INVALID_SOURCE, "git source fields are incomplete")
    return GitIntent(
        repository_url=source.repository_url,
        tracked_ref=source.tracked_ref,
        subpath=source.component_subpath,
    )


def map_source_error(error: SourceError) -> OfficialUpstreamError:
    code = _SOURCE_ERROR_MAP.get(error.code, FAILED_VALIDATION)
    return OfficialUpstreamError(code, error.message)


async def resolve_official_snapshot(
    source: OfficialUpstreamSource,
    *,
    fetch: FetchFn | None = None,
    now: datetime | None = None,
) -> SourceSnapshot:
    """Resolve one official source through SourceIntent/SourceSnapshot."""
    return await resolve_intent(source_intent(source), fetch=fetch, now=now)


async def resolve_intent(
    intent: GitIntent | PackageIntent,
    *,
    fetch: FetchFn | None = None,
    now: datetime | None = None,
) -> SourceSnapshot:
    try:
        return await resolve_source(
            intent,
            fetch=fetch or default_fetch,
            token=worker_github_token(),
            now=now,
        )
    except SourceError as error:
        raise map_source_error(error) from error
