"""Unit tests for OAuth provider claim extraction (avatars / display names)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from authlib.integrations.starlette_client import OAuth  # type: ignore[import-untyped]

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.slices.auth import oauth as oauth_module
from ai_stp_api.slices.auth.domain import normalize_display_name, normalize_https_url
from ai_stp_api.slices.auth.oauth import profile_from_token


def test_https_url_accepts_only_https_and_bounds_length() -> None:
    assert normalize_https_url("https://example.com/a.png") == "https://example.com/a.png"
    assert normalize_https_url("http://example.com/a.png") is None
    assert normalize_https_url("  https://example.com/x  ") == "https://example.com/x"
    assert normalize_https_url(None) is None
    assert normalize_https_url("https://" + ("a" * 2100)) is None


def test_display_name_trims_and_truncates() -> None:
    assert normalize_display_name("  Alice  ") == "Alice"
    assert normalize_display_name("") is None
    assert normalize_display_name(None) is None
    long = "x" * 200
    assert normalize_display_name(long) == "x" * 120


# The google branch of profile_from_token never touches the OAuth registry, so a
# bare instance is enough and the test stays offline. Going through the public
# entry point also covers provider dispatch, which a direct call would skip.
async def test_google_profile_extracts_picture_and_name() -> None:
    profile = await profile_from_token(
        OAuth(),
        "google",
        {
            "userinfo": {
                "sub": "google-sub-99",
                "email": "User@Example.COM",
                "email_verified": True,
                "picture": "https://lh3.googleusercontent.com/a/photo",
                "name": "Example User",
            }
        },
    )
    assert profile.provider == "google"
    assert profile.subject == "google-sub-99"
    assert profile.email == "user@example.com"
    assert profile.email_verified is True
    assert profile.avatar_url == "https://lh3.googleusercontent.com/a/photo"
    assert profile.display_name == "Example User"


async def test_google_profile_rejects_missing_email() -> None:
    with pytest.raises(ApiError) as exc:
        await profile_from_token(
            OAuth(),
            "google",
            {"userinfo": {"sub": "only-sub", "email_verified": True}},
        )
    assert exc.value.category is ErrorCategory.AUTH_REQUIRED


async def test_unknown_provider_is_a_validation_error() -> None:
    with pytest.raises(ApiError) as exc:
        await profile_from_token(OAuth(), "gitlab", {"userinfo": {}})
    assert exc.value.category is ErrorCategory.VALIDATION


class _Response:
    def __init__(self, value: object) -> None:
        self.value = value

    def json(self) -> object:
        return self.value


class _GithubClient:
    def __init__(self, user: object, emails: object) -> None:
        self.user = user
        self.emails = emails

    async def get(self, url: str, token: object = None) -> _Response:
        del token
        return _Response(self.user if url == "user" else self.emails)


def _client_factory(
    remote: _GithubClient | None,
) -> Callable[[OAuth], Callable[[str], _GithubClient | None]]:
    def bind(_oauth: OAuth) -> Callable[[str], _GithubClient | None]:
        def create(_name: str) -> _GithubClient | None:
            return remote

        return create

    return bind


async def test_github_profile_prefers_verified_primary_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = _GithubClient(
        {
            "id": 42,
            "email": "public@example.com",
            "name": None,
            "login": "octocat",
            "avatar_url": "https://avatars.example/octocat",
        },
        [
            {"email": "public@example.com", "primary": False, "verified": True},
            {"email": "primary@example.com", "primary": True, "verified": True},
        ],
    )
    monkeypatch.setattr(oauth_module, "_create_client_fn", _client_factory(remote))

    profile = await profile_from_token(OAuth(), "github", {"access_token": "redacted"})

    assert profile.subject == "42"
    assert profile.email == "primary@example.com"
    assert profile.email_verified is True
    assert profile.display_name == "octocat"
    assert profile.avatar_url == "https://avatars.example/octocat"


@pytest.mark.parametrize(
    ("user", "emails"),
    [
        ("not-a-mapping", []),
        ({"login": "missing-id"}, []),
        ({"id": 1, "email": None}, []),
        ({"id": 1, "email": "public@example.com"}, "not-a-list"),
    ],
)
async def test_github_profile_rejects_untrusted_claim_shapes(
    monkeypatch: pytest.MonkeyPatch, user: object, emails: object
) -> None:
    remote = _GithubClient(user, emails)
    monkeypatch.setattr(oauth_module, "_create_client_fn", _client_factory(remote))

    with pytest.raises(ApiError) as raised:
        await profile_from_token(OAuth(), "github", {})
    assert raised.value.category is ErrorCategory.AUTH_REQUIRED


async def test_github_profile_accepts_verified_public_email_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = _GithubClient(
        {"id": 7, "email": "public@example.com", "name": "Git Hub"},
        [{"email": "public@example.com", "primary": False, "verified": True}],
    )
    monkeypatch.setattr(oauth_module, "_create_client_fn", _client_factory(remote))

    profile = await profile_from_token(OAuth(), "github", {})

    assert profile.email == "public@example.com"
    assert profile.display_name == "Git Hub"


async def test_github_profile_requires_registered_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oauth_module, "_create_client_fn", _client_factory(None))

    with pytest.raises(ApiError) as raised:
        await profile_from_token(OAuth(), "github", {})
    assert raised.value.category is ErrorCategory.VALIDATION
