"""Authlib OAuth client registration (ADR-0041).

Google uses OIDC discovery; GitHub uses classic OAuth endpoints plus the
``user`` and ``user:email`` APIs for a verified primary email.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol, cast

# authlib ships no complete type stubs for the Starlette integration.
from authlib.integrations.starlette_client import OAuth  # type: ignore[import-untyped]
from starlette.requests import Request

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.settings import AuthSettings
from ai_stp_api.slices.auth.domain import (
    ProviderProfile,
    normalize_display_name,
    normalize_email,
    normalize_https_url,
    normalize_subject,
)

GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"
GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_API = "https://api.github.com/"


class OAuthJsonResponse(Protocol):
    """Minimal response surface used after Authlib remote GET calls."""

    def json(self) -> object: ...


class OAuthClientPort(Protocol):
    """Test seam for authorize redirect, token exchange and remote GETs."""

    async def authorize_redirect(self, request: Request, redirect_uri: str) -> Any: ...

    async def authorize_access_token(self, request: Request) -> Mapping[str, Any]: ...

    async def get(self, url: str, token: Mapping[str, Any] | None = None) -> OAuthJsonResponse: ...


_RegisterFn = Callable[..., object]
_CreateClientFn = Callable[[str], OAuthClientPort | None]


def _register_fn(oauth: OAuth) -> _RegisterFn:
    # Authlib OAuth methods are untyped; cast once at the library boundary.
    return cast(_RegisterFn, cast(Any, oauth).register)


def _create_client_fn(oauth: OAuth) -> _CreateClientFn:
    return cast(_CreateClientFn, cast(Any, oauth).create_client)


def build_oauth(auth: AuthSettings) -> OAuth:
    """Register configured providers with PKCE S256."""
    oauth = OAuth()
    register = _register_fn(oauth)
    if auth.provider_enabled("google"):
        register(
            name="google",
            client_id=auth.google_client_id,
            client_secret=auth.google_client_secret,
            server_metadata_url=GOOGLE_METADATA,
            client_kwargs={
                "scope": "openid email profile",
                "code_challenge_method": "S256",
            },
        )
    if auth.provider_enabled("github"):
        register(
            name="github",
            client_id=auth.github_client_id,
            client_secret=auth.github_client_secret,
            authorize_url=GITHUB_AUTHORIZE,
            access_token_url=GITHUB_TOKEN,
            api_base_url=GITHUB_API,
            client_kwargs={
                "scope": "read:user user:email",
                "code_challenge_method": "S256",
            },
        )
    return oauth


def get_client(oauth: OAuth, provider: str) -> OAuthClientPort:
    """Return a registered remote app or raise a typed error."""
    client = _create_client_fn(oauth)(provider)
    if client is None:
        raise ApiError(ErrorCategory.VALIDATION, "unsupported oauth provider")
    return client


async def profile_from_token(
    oauth: OAuth,
    provider: str,
    token: Mapping[str, Any],
) -> ProviderProfile:
    """Extract a ProviderProfile from a provider token response."""
    if provider == "google":
        return _google_profile(token)
    if provider == "github":
        return await _github_profile(oauth, token)
    raise ApiError(ErrorCategory.VALIDATION, "unsupported oauth provider")


def _mapping_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_object_mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return cast(Mapping[str, object], value)


def _google_profile(token: Mapping[str, Any]) -> ProviderProfile:
    raw_userinfo: object = token.get("userinfo") or token.get("id_token") or {}
    userinfo = _as_object_mapping(raw_userinfo)
    if userinfo is None:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication failed")
    subject = _mapping_str(userinfo.get("sub"))
    email = _mapping_str(userinfo.get("email"))
    verified = bool(userinfo.get("email_verified"))
    if not subject or not email:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication failed")
    return ProviderProfile(
        provider="google",
        subject=normalize_subject(subject),
        email=normalize_email(email),
        email_verified=verified,
        avatar_url=normalize_https_url(_mapping_str(userinfo.get("picture"))),
        display_name=normalize_display_name(_mapping_str(userinfo.get("name"))),
    )


async def _github_profile(oauth: OAuth, token: Mapping[str, Any]) -> ProviderProfile:
    client = _create_client_fn(oauth)("github")
    if client is None:
        raise ApiError(ErrorCategory.VALIDATION, "unsupported oauth provider")
    resp = await client.get("user", token=token)
    data_raw: object = resp.json()
    data = _as_object_mapping(data_raw)
    if data is None:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication failed")
    subject = data.get("id")
    if subject is None:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication failed")

    email: str | None = _mapping_str(data.get("email"))
    verified = False
    emails_resp = await client.get("user/emails", token=token)
    emails_raw: object = emails_resp.json()
    if isinstance(emails_raw, list):
        email_rows = [
            row_map
            for row in cast(list[object], emails_raw)
            if (row_map := _as_object_mapping(row)) is not None
        ]
        primary_verified = next(
            (row for row in email_rows if row.get("primary") and row.get("verified")),
            None,
        )
        if primary_verified is not None:
            email = _mapping_str(primary_verified.get("email"))
            verified = True
        elif email:
            # Fall back: any verified email matching the public field.
            match = next(
                (row for row in email_rows if row.get("email") == email and row.get("verified")),
                None,
            )
            verified = match is not None

    if not email or not verified:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication failed")

    name = normalize_display_name(_mapping_str(data.get("name"))) or normalize_display_name(
        _mapping_str(data.get("login"))
    )
    return ProviderProfile(
        provider="github",
        subject=normalize_subject(str(subject)),
        email=normalize_email(email),
        email_verified=True,
        avatar_url=normalize_https_url(_mapping_str(data.get("avatar_url"))),
        display_name=name,
        username=_mapping_str(data.get("login")),
    )
