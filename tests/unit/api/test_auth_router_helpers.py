# pyright: reportPrivateUsage=false
"""Unit tests for pure OAuth router helpers (SPEC-010 auth surface).

These helpers decide browser vs CLI transport and same-origin return paths.
Breakage: open redirects, wrong locale, or JSON/HTML negotiation regressions.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from starlette.requests import Request

from ai_stp_api.settings import AuthSettings
from ai_stp_api.slices.auth.router import (
    _callback_uri,
    _locale_from_return_to,
    _prefer_browser_redirect,
    _safe_return_to,
    _wants_json,
    _web_login_status_location,
    _web_return_location,
)

pytestmark = pytest.mark.platform

_PUBLIC_BASE = "https://app.example.test"
_SECRET = "test-secret-key-at-least-32-bytes-long!!"


def _auth(**overrides: object) -> AuthSettings:
    payload: dict[str, object] = {
        "secret_key": _SECRET,
        "public_base_url": _PUBLIC_BASE,
    }
    payload.update(overrides)
    return AuthSettings.model_validate(payload)


def _request(*, accept: str = "*/*", method: str = "GET") -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": "/v1/auth/github/login",
        "raw_path": b"/v1/auth/github/login",
        "query_string": b"",
        "headers": [(b"accept", accept.encode("latin-1"))],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 443),
    }
    return Request(scope)


def test_wants_json_honours_mode_and_accept_header() -> None:
    assert _wants_json(_request(), "json") is True
    assert _wants_json(_request(accept="application/json"), "redirect") is False
    assert _wants_json(_request(accept="application/json"), None) is True
    assert _wants_json(_request(accept="text/html,application/json"), None) is False
    assert _wants_json(_request(accept="text/plain"), None) is False


def test_safe_return_to_rejects_open_redirects_and_control_chars() -> None:
    assert _safe_return_to(None) is None
    assert _safe_return_to("/ru/account") == "/ru/account"
    assert _safe_return_to("//evil.example/phish") is None
    assert _safe_return_to("https://evil.example/phish") is None
    assert _safe_return_to("/path?next=https://evil.example") is None
    assert _safe_return_to("/ok\\evil") is None
    assert _safe_return_to("/ok\n/evil") is None
    assert _safe_return_to("/ok\r/evil") is None
    assert _safe_return_to("relative") is None


def test_locale_from_return_to_defaults_and_filters() -> None:
    assert _locale_from_return_to(None) == "ru"
    assert _locale_from_return_to("/en/catalog") == "en"
    assert _locale_from_return_to("/ru/account") == "ru"
    assert _locale_from_return_to("/de/account") == "ru"
    assert _locale_from_return_to("//evil") == "ru"


def test_prefer_browser_redirect_uses_client_hint_then_accept() -> None:
    json_req = _request(accept="application/json")
    html_req = _request(accept="text/html")
    assert _prefer_browser_redirect(json_req, "web") is True
    assert _prefer_browser_redirect(html_req, "cli") is False
    assert _prefer_browser_redirect(json_req, None) is False
    assert _prefer_browser_redirect(html_req, None) is True


def _asked_from(origin: str) -> Request:
    """A request whose URL says which origin the browser is on."""
    scheme, _, netloc = origin.partition("://")
    return cast(Request, SimpleNamespace(url=SimpleNamespace(scheme=scheme, netloc=netloc)))


def test_callback_and_return_locations_use_configured_origins() -> None:
    auth = _auth(oauth_redirect_base_url="https://api.example.test:8000")
    assert (
        _callback_uri(_asked_from("https://elsewhere.test"), auth, "github")
        == "https://api.example.test:8000/v1/auth/github/callback"
    )

    assert _web_return_location(auth, "/en/account") == f"{_PUBLIC_BASE}/en/account"
    assert _web_return_location(auth, "//evil") == f"{_PUBLIC_BASE}/ru/account"
    assert (
        _web_login_status_location(auth, return_to="/en/catalog", status="cancel")
        == f"{_PUBLIC_BASE}/en/login?status=cancel"
    )
    assert (
        _web_login_status_location(auth, return_to=None, status="error")
        == f"{_PUBLIC_BASE}/ru/login?status=error"
    )


def test_a_second_declared_origin_keeps_its_own_callback() -> None:
    """`#62`, measured to the mechanism and fixed at it.

    The handshake state lives in a session cookie on the origin that started the
    flow. One pinned callback with two served domains meant a sign-in begun on
    the canonical domain landed on the other, `authorize_access_token` found no
    state, and the browser showed "Sign-in failed" — twice in one production log,
    both attempts from the canonical domain.

    The origin is *selected* from what the deployment declares, never introduced
    by the request: a forged `Host` can pick another declared origin, which is
    already registered in the provider console, and nothing else.
    """
    auth = _auth(
        oauth_redirect_base_url="https://nddev.asia",
        oauth_callback_origins="https://ai-stp.aiguild.space/, https://nddev.asia",
    )
    assert auth.oauth_callback_bases() == ("https://nddev.asia", "https://ai-stp.aiguild.space")

    assert (
        _callback_uri(_asked_from("https://ai-stp.aiguild.space"), auth, "google")
        == "https://ai-stp.aiguild.space/v1/auth/google/callback"
    )
    assert (
        _callback_uri(_asked_from("https://nddev.asia"), auth, "google")
        == "https://nddev.asia/v1/auth/google/callback"
    )
    # Undeclared, so the flow falls back to the single origin it always used.
    assert (
        _callback_uri(_asked_from("https://forged.example"), auth, "google")
        == "https://nddev.asia/v1/auth/google/callback"
    )


def test_a_deployment_declaring_no_extra_origin_behaves_exactly_as_before() -> None:
    auth = _auth(oauth_redirect_base_url="https://only.example")
    assert auth.oauth_callback_bases() == ("https://only.example",)
    assert (
        _callback_uri(_asked_from("https://only.example"), auth, "github")
        == "https://only.example/v1/auth/github/callback"
    )
