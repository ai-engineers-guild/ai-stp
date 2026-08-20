"""Domain-level account linking behaviour (SPEC-002 REQ-201/202/203)."""

from __future__ import annotations

from ai_stp_api.slices.auth.domain import (
    SUPPORTED_PROVIDERS,
    normalize_email,
    normalize_subject,
    validate_provider,
)

pytestmark = __import__("pytest").mark.platform


def test_email_normalization_is_case_insensitive() -> None:
    assert normalize_email("  Alice@Example.COM ") == "alice@example.com"


def test_subject_normalization_does_not_case_fold() -> None:
    # Provider-native subjects stay case-sensitive after strip.
    assert normalize_subject("  AbC123  ") == "AbC123"


def test_supported_providers_are_google_and_github() -> None:
    assert frozenset({"google", "github"}) == SUPPORTED_PROVIDERS
    assert validate_provider("Google") == "google"
