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
        await profile_from_token(OAuth(), "bitbucket", {"userinfo": {}})
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


async def test_authentik_profile_uses_generic_oidc_claims() -> None:
    profile = await profile_from_token(
        OAuth(),
        "authentik",
        {
            "userinfo": {
                "sub": "a1b2c3",
                "email": "Corp@Example.LOCAL",
                "email_verified": True,
                "preferred_username": "corp.user",
            }
        },
    )
    assert profile.provider == "authentik"
    assert profile.subject == "a1b2c3"
    assert profile.email == "corp@example.local"
    assert profile.email_verified is True


async def test_keycloak_profile_uses_generic_oidc_claims() -> None:
    profile = await profile_from_token(
        OAuth(),
        "keycloak",
        {
            "userinfo": {
                "sub": "f:realm:uuid-1",
                "email": "user@corp.example",
                "email_verified": True,
                "name": "Realm User",
            }
        },
    )
    assert profile.provider == "keycloak"
    assert profile.subject == "f:realm:uuid-1"
    assert profile.email == "user@corp.example"
    assert profile.display_name == "Realm User"


async def test_gitlab_profile_qualifies_subject_by_issuer_host() -> None:
    profile = await profile_from_token(
        OAuth(),
        "gitlab",
        {
            "userinfo": {
                "sub": "42",
                "email": "Dev@Corp.Example",
                "email_verified": True,
                "preferred_username": "dev.user",
                "name": "Corp Dev",
            }
        },
        issuer="https://gitlab.corp.example",
    )
    assert profile.provider == "gitlab"
    # Per-instance integer subjects are host-qualified so a re-pointed issuer
    # can never collide old and new identities.
    assert profile.subject == "gitlab.corp.example:42"
    assert profile.email == "dev@corp.example"
    assert profile.username == "dev.user"
    assert profile.display_name == "Corp Dev"


async def test_gitlab_profile_requires_a_configured_issuer() -> None:
    with pytest.raises(ApiError) as exc:
        await profile_from_token(
            OAuth(),
            "gitlab",
            {"userinfo": {"sub": "1", "email": "d@corp.example", "email_verified": True}},
        )
    assert exc.value.category is ErrorCategory.AUTH_REQUIRED


async def test_corporate_oidc_profile_rejects_missing_subject() -> None:
    with pytest.raises(ApiError) as exc:
        await profile_from_token(
            OAuth(),
            "keycloak",
            {"userinfo": {"email": "user@corp.example", "email_verified": True}},
        )
    assert exc.value.category is ErrorCategory.AUTH_REQUIRED


def test_build_oauth_registers_corporate_oidc_only_when_configured() -> None:
    from ai_stp_api.settings import AuthSettings
    from ai_stp_api.slices.auth.oauth import build_oauth, get_client

    auth = AuthSettings(
        secret_key="s" * 32,
        keycloak_issuer_url="https://sso.example.com/realms/corp/",
        keycloak_client_id="ai-stp",
        keycloak_client_secret="kc-secret",
    )
    oauth = build_oauth(auth)
    assert get_client(oauth, "keycloak") is not None
    # Issuer unset → the provider is off entirely.
    for off in ("authentik", "google"):
        with pytest.raises(ApiError) as exc:
            get_client(oauth, off)
        assert exc.value.category is ErrorCategory.VALIDATION

    both = AuthSettings(
        secret_key="s" * 32,
        authentik_issuer_url="http://localhost:9000/application/o/stp",
        authentik_client_id="stp",
        authentik_client_secret="ak-secret",
        keycloak_issuer_url="https://sso.example.com/realms/corp",
        keycloak_client_id="ai-stp",
        keycloak_client_secret="kc-secret",
        gitlab_issuer_url="https://gitlab.corp.example",
        gitlab_client_id="ai-stp-gitlab",
        gitlab_client_secret="gl-secret",
    )
    oauth = build_oauth(both)
    assert get_client(oauth, "authentik") is not None
    assert get_client(oauth, "keycloak") is not None
    assert get_client(oauth, "gitlab") is not None

    partial = AuthSettings(
        secret_key="s" * 32,
        gitlab_issuer_url="https://gitlab.corp.example",
        gitlab_client_id="ai-stp-gitlab",
    )
    # Issuer without client credentials stays off.
    with pytest.raises(ApiError) as exc:
        get_client(build_oauth(partial), "gitlab")
    assert exc.value.category is ErrorCategory.VALIDATION
