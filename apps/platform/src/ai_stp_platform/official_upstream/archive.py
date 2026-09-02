"""Bounded GitHub archive extraction for one official component root."""

from __future__ import annotations

from ai_stp_platform.official_upstream.errors import UNSAFE_ARCHIVE, OfficialUpstreamError
from ai_stp_sources.archive import (
    MAX_ARCHIVE_BYTES,
    MAX_EXTRACTED_BYTES,
)
from ai_stp_sources.archive import (
    extract_component_files as extract_source_files,
)
from ai_stp_sources.errors import SourceError

__all__ = ["MAX_ARCHIVE_BYTES", "MAX_EXTRACTED_BYTES", "extract_component_files"]


def extract_component_files(archive_bytes: bytes, *, subpath: str) -> dict[str, bytes]:
    """Extract component-root files; reject links, traversal, secrets, binaries."""
    try:
        return extract_source_files(archive_bytes, subpath=subpath)
    except SourceError as exc:
        raise OfficialUpstreamError(UNSAFE_ARCHIVE, exc.message) from exc
