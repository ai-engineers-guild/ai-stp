"""The bounded second-level index of a project (`SPEC-004` REQ-403 to REQ-406).

The implementation lives in ``ai_stp_sources.project_index`` so the server-side
worker and the CLI run the same walk. This module keeps the historical import
path and translates the one user-facing failure into ``CliFailure``.
"""

from pathlib import Path

from ai_stp_cli.errors import CliFailure
from ai_stp_sources import project_index as _index
from ai_stp_sources.errors import SourceError
from ai_stp_sources.project_index import (
    AGENT_SURFACE_NAMES,
    BINARY_PROBE_BYTES,
    CONFIG_SUFFIXES,
    DOCUMENT_SUFFIXES,
    LOCK_NAMES,
    MANIFEST_NAMES,
    MAX_DEPTH,
    MAX_ENTRIES,
    MAX_FILE_BYTES,
    MAX_SECONDS,
    SECRET_NAMES,
    SECRET_PREFIXES,
    SECRET_SUFFIXES,
    SKIPPED_DIRECTORIES,
    SOURCE_SUFFIXES,
    Budget,
    Entry,
    Excluded,
    Index,
    classify,
    is_binary,
    is_secret_name,
)

__all__ = [
    "AGENT_SURFACE_NAMES",
    "BINARY_PROBE_BYTES",
    "CONFIG_SUFFIXES",
    "DOCUMENT_SUFFIXES",
    "LOCK_NAMES",
    "MANIFEST_NAMES",
    "MAX_DEPTH",
    "MAX_ENTRIES",
    "MAX_FILE_BYTES",
    "MAX_SECONDS",
    "SECRET_NAMES",
    "SECRET_PREFIXES",
    "SECRET_SUFFIXES",
    "SKIPPED_DIRECTORIES",
    "SOURCE_SUFFIXES",
    "Budget",
    "Entry",
    "Excluded",
    "Index",
    "build",
    "classify",
    "is_binary",
    "is_secret_name",
]


def build(root: Path, *, digests: bool = True) -> Index:
    """Walk the root once and describe what is safely readable inside it."""
    try:
        return _index.build(root, digests=digests)
    except SourceError:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "that project root is not a directory",
            next_actions=["project discover --root <path> --json"],
        ) from None
