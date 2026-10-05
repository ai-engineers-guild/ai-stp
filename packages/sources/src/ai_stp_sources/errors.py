"""Typed source-resolution failures (SPEC-057)."""

from __future__ import annotations

from datetime import datetime

INVALID_SOURCE = "invalid_source"
UNSUPPORTED_SOURCE = "unsupported_source"
FLOATING_FROZEN_SOURCE = "floating_frozen_source"
UNAVAILABLE_SOURCE = "unavailable_source"
UNSAFE_ARCHIVE = "unsafe_archive"
AMBIGUOUS_DISTRIBUTION = "ambiguous_distribution"
INTEGRITY_MISMATCH = "integrity_mismatch"
CATALOG_COLLISION = "catalog_collision"
INCOMPLETE_PASSPORT = "incomplete_passport"
PROHIBITED_REDISTRIBUTION = "prohibited_redistribution"
MISSING_EMBEDDED_REF = "missing_embedded_ref"


class SourceError(Exception):
    """A closed source canonicalization or resolution failure."""

    def __init__(self, code: str, message: str, *, retry_at: datetime | None = None) -> None:
        self.code = code
        self.message = message
        #: The moment the upstream named for a retry, such as a rate-limit reset.
        self.retry_at = retry_at
        super().__init__(message)
