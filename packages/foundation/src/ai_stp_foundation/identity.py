"""Versioned public-identity normalization (SPEC-059, ADR-0149).

API, CLI, migrations, and PostgreSQL unique keys use this module. The
normalization version is part of the contract so a later algorithm cannot
silently reinterpret stored keys.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

IDENTITY_NORMALIZATION_VERSION: Final[str] = "identity-normalization/1"
HANDLE_PATTERN: Final[str] = r"^[a-z](?:[a-z0-9]|-[a-z0-9]){0,31}$"
HANDLE_MAX_LENGTH: Final[int] = 32
DISPLAY_NAME_MAX_LENGTH: Final[int] = 80
OFFICIAL_HANDLE: Final[str] = "ai-stp-official"
OFFICIAL_DISPLAY_NAME: Final[str] = "AI STP Official"

_HANDLE_RE: Final[re.Pattern[str]] = re.compile(HANDLE_PATTERN)
_MULTI_HYPHEN: Final[re.Pattern[str]] = re.compile(r"-{2,}")


class IdentityNormalizationError(ValueError):
    """Submitted identity text cannot be stored under the current contract."""


def normalize_display_key(value: str) -> str:
    """NFKC, trim, collapse whitespace, casefold. Empty after this is rejected."""
    if "\ufeff" in value:
        raise IdentityNormalizationError("byte-order mark is rejected")
    collapsed = " ".join(unicodedata.normalize("NFKC", value).split())
    key = collapsed.casefold()
    if not key:
        raise IdentityNormalizationError("display name is empty after normalization")
    if len(collapsed) > DISPLAY_NAME_MAX_LENGTH:
        raise IdentityNormalizationError("display name exceeds the length bound")
    return key


def submitted_display_name(value: str) -> str:
    """Return the stored spelling after NFKC, trim, and whitespace collapse."""
    normalize_display_key(value)
    return " ".join(unicodedata.normalize("NFKC", value).split())


def normalize_handle(value: str) -> str:
    """NFKC, strip, casefold, then the closed ASCII handle grammar."""
    if "\ufeff" in value:
        raise IdentityNormalizationError("byte-order mark is rejected")
    folded = unicodedata.normalize("NFKC", value).strip().casefold()
    if _MULTI_HYPHEN.search(folded):
        raise IdentityNormalizationError("handle contains consecutive hyphens")
    if not _HANDLE_RE.fullmatch(folded):
        raise IdentityNormalizationError("handle is not a closed ASCII handle")
    if len(folded) > HANDLE_MAX_LENGTH:
        raise IdentityNormalizationError("handle exceeds the length bound")
    return folded


def canonical_slug(value: str) -> str:
    """Language-independent unique component slug from submitted text."""
    key = normalize_display_key(value)
    slug = _MULTI_HYPHEN.sub("-", key.replace(" ", "-")).strip("-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    if not slug:
        raise IdentityNormalizationError("canonical name is empty after normalization")
    if len(slug) > DISPLAY_NAME_MAX_LENGTH:
        raise IdentityNormalizationError("canonical name exceeds the length bound")
    return slug


def handle_from_account_id(account_id: str) -> str:
    """Deterministic unique handle used only for backfill of unnamed accounts."""
    _prefix, _sep, suffix = account_id.partition("_")
    compact = re.sub(r"[^a-z0-9]", "", suffix.casefold()) or "account"
    return normalize_handle(f"user-{compact[:24]}")


def is_protected_official_handle(handle: str) -> bool:
    try:
        return normalize_handle(handle) == OFFICIAL_HANDLE
    except IdentityNormalizationError:
        return False


def is_protected_official_display(display_name: str) -> bool:
    try:
        return normalize_display_key(display_name) == normalize_display_key(OFFICIAL_DISPLAY_NAME)
    except IdentityNormalizationError:
        return False
