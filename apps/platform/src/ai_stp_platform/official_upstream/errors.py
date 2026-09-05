"""Typed official-upstream failures (SPEC-056)."""

from __future__ import annotations

INVALID_SOURCE = "invalid_source"
UNAVAILABLE_UPSTREAM = "unavailable_upstream"
CHANGED_REPOSITORY_IDENTITY = "changed_repository_identity"
UNSAFE_ARCHIVE = "unsafe_archive"
FAILED_VALIDATION = "failed_validation"
IDEMPOTENCY_CONFLICT = "idempotency_conflict"
STALE_OWNERSHIP = "stale_ownership_fence"
MANIFEST_MISMATCH = "manifest_mismatch"


class OfficialUpstreamError(Exception):
    """A closed sync or source-configuration failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
