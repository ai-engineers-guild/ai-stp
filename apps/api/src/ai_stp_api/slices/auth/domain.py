"""Auth domain types and identity-linking invariants (SPEC-002 REQ-201..203)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OAuthProvider(StrEnum):
    """Supported OAuth providers for MVP."""

    GOOGLE = "google"
    GITHUB = "github"


class LinkState(StrEnum):
    """OAuth identity link states from SPEC-002."""

    PENDING = "pending"
    LINKED = "linked"
    CONFLICT = "conflict"
    REVOKED = "revoked"


SUPPORTED_PROVIDERS: frozenset[str] = frozenset(p.value for p in OAuthProvider)


@dataclass(frozen=True)
class ProviderProfile:
    """Normalized claims extracted from a provider token response.

    ``subject`` is the provider-native stable subject (no case-fold).
    ``email`` is stored and matched after lower-case normalization.
    ``avatar_url`` / ``display_name`` are presentation-only (HTTPS URL + label).
    """

    provider: str
    subject: str
    email: str
    email_verified: bool
    avatar_url: str | None = None
    display_name: str | None = None
    username: str | None = None


def normalize_email(email: str) -> str:
    """Normalize an email for comparison and storage."""
    return email.strip().lower()


def normalize_subject(subject: str) -> str:
    """Normalize a provider subject without case-folding.

    Assumption (flagged): provider-native subject strings are used as-is after
    strip. Google ``sub`` and GitHub numeric id are stable and case-sensitive
    opaque identifiers; case-folding would risk collisions.
    """
    return subject.strip()


def normalize_https_url(value: str | None) -> str | None:
    """Return a bounded HTTPS URL or None.

    Presentation-only claims arrive from the provider unvalidated: a non-HTTPS
    scheme would become mixed content and an unbounded string would land in a
    column with a limit. Anything not plainly acceptable becomes None rather
    than an error, because a missing avatar is not a login failure.
    """
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed.startswith("https://") or len(trimmed) > 2048:
        return None
    return trimmed


def normalize_display_name(value: str | None) -> str | None:
    """Return a trimmed, length-bounded label or None for an empty one."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed[:120]


def validate_provider(provider: str) -> str:
    """Return a known provider name or raise ValueError."""
    name = provider.strip().lower()
    if name not in SUPPORTED_PROVIDERS:
        msg = f"unsupported oauth provider: {provider!r}"
        raise ValueError(msg)
    return name


@dataclass(frozen=True)
class LinkDecision:
    """Outcome of the account/identity resolution algorithm."""

    account_id: str
    identity_id: int | None
    created_account: bool
    linked_identity: bool
    state: LinkState
