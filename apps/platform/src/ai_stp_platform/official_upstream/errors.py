"""Typed official-upstream failures (SPEC-056)."""

from __future__ import annotations

from datetime import datetime

INVALID_SOURCE = "invalid_source"
UNAVAILABLE_UPSTREAM = "unavailable_upstream"
CHANGED_REPOSITORY_IDENTITY = "changed_repository_identity"
UNSAFE_ARCHIVE = "unsafe_archive"
FAILED_VALIDATION = "failed_validation"
IDEMPOTENCY_CONFLICT = "idempotency_conflict"
STALE_OWNERSHIP = "stale_ownership_fence"
MANIFEST_MISMATCH = "manifest_mismatch"

#: Failures a retry of the same attempt cannot change: the archive of the
#: resolved commit, the reviewed source fields and the repository identity
#: are fixed for that attempt. The next daily attempt resolves them again.
DETERMINISTIC_FAILURES = frozenset(
    {INVALID_SOURCE, UNSAFE_ARCHIVE, CHANGED_REPOSITORY_IDENTITY, MANIFEST_MISMATCH}
)


class OfficialUpstreamError(Exception):
    """A closed sync or source-configuration failure."""

    def __init__(self, code: str, message: str, *, retry_at: datetime | None = None) -> None:
        self.code = code
        self.message = message
        #: The moment the upstream named for a retry, such as a rate-limit reset.
        self.retry_at = retry_at
        super().__init__(message)
