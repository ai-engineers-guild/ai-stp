# pyright: reportPrivateUsage=false
"""Unit tests for Bearer/cookie extraction and CSRF enforcement (ADR-0041).

Breakage: CSRF skipped on cookie POSTs, or Bearer headers misparsed as sessions.
"""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from ai_stp_api.deps import (
    _extract_bearer,
    _extract_cookie_token,
    ensure_csrf,
    new_csrf_token,
)
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.settings import AuthSettings

pytestmark = pytest.mark.platform

_SECRET = "test-secret-key-at-least-32-bytes-long!!"


def _auth() -> AuthSettings:
    return AuthSettings.model_validate({"secret_key": _SECRET})


def _request(
    *,
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
    cookies: dict[str, str] | None = None,
) -> Request:
    header_list = list(headers or [])
    if cookies:
        cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
        header_list.append((b"cookie", cookie_header.encode("latin-1")))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": "/v1/me",
        "raw_path": b"/v1/me",
        "query_string": b"",
        "headers": header_list,
        "client": ("127.0.0.1", 12345),
        "server": ("test", 443),
    }
    return Request(scope)


def test_extract_bearer_accepts_only_bearer_scheme() -> None:
    assert _extract_bearer(_request()) is None
    assert _extract_bearer(_request(headers=[(b"authorization", b"Basic abc")])) is None
    assert _extract_bearer(_request(headers=[(b"authorization", b"Bearer   ")])) is None
    token = "opaque-session-token-value"
    assert (
        _extract_bearer(_request(headers=[(b"authorization", f"Bearer {token}".encode())])) == token
    )
    assert (
        _extract_bearer(_request(headers=[(b"authorization", f"bearer {token}".encode())])) == token
    )


def test_extract_cookie_token_reads_named_cookie() -> None:
    auth = _auth()
    assert _extract_cookie_token(_request(), auth.cookie_name) is None
    assert (
        _extract_cookie_token(
            _request(cookies={auth.cookie_name: "cookie-token"}),
            auth.cookie_name,
        )
        == "cookie-token"
    )


def test_ensure_csrf_skips_bearer_and_safe_methods() -> None:
    auth = _auth()
    # Bearer transport never requires double-submit CSRF.
    ensure_csrf(_request(method="POST"), auth=auth, via_cookie=False)
    # Cookie + safe method is also exempt.
    ensure_csrf(
        _request(
            method="GET",
            cookies={auth.csrf_cookie_name: "token"},
        ),
        auth=auth,
        via_cookie=True,
    )


def test_ensure_csrf_rejects_mismatch_or_missing_on_unsafe_cookie_write() -> None:
    auth = _auth()
    token = new_csrf_token()
    with pytest.raises(ApiError) as missing:
        ensure_csrf(_request(method="POST"), auth=auth, via_cookie=True)
    assert missing.value.category is ErrorCategory.AUTH_REQUIRED

    with pytest.raises(ApiError) as mismatch:
        ensure_csrf(
            _request(
                method="DELETE",
                cookies={auth.csrf_cookie_name: token},
                headers=[(auth.csrf_header_name.lower().encode(), b"other")],
            ),
            auth=auth,
            via_cookie=True,
        )
    assert mismatch.value.category is ErrorCategory.AUTH_REQUIRED

    ensure_csrf(
        _request(
            method="PATCH",
            cookies={auth.csrf_cookie_name: token},
            headers=[(auth.csrf_header_name.lower().encode(), token.encode())],
        ),
        auth=auth,
        via_cookie=True,
    )


async def test_require_variants_publish_auth_context_on_request_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every auth dependency must leave `request.state.auth_context` populated:
    error auditing keys off it, and a missing context reads as anonymous."""
    import ai_stp_api.deps as deps
    from ai_stp_api.session import AuthContext

    context = AuthContext(
        account_id="account-x",
        session_id="session-x",
        device_id=None,
        account_status="active",
        is_admin=False,
        via_cookie=False,
    )
    calls: list[dict[str, object]] = []

    async def _verify(db: object, raw: str, **kwargs: object) -> AuthContext:
        calls.append(kwargs)
        return context

    monkeypatch.setattr(deps, "verify_raw_token", _verify)
    auth = _auth()
    db = cast(AsyncSession, object())

    for dependency in (
        deps.require_auth,
        deps.require_onboarding_auth,
        deps.require_refresh_auth,
    ):
        request = _request(
            method="GET",
            headers=[(b"authorization", b"Bearer opaque-token")],
        )
        resolved = await dependency(request, db, auth)
        assert resolved is context
        assert request.state.auth_context is context

    assert calls[0].get("allow_onboarding") in (None, False)
    assert calls[1]["allow_onboarding"] is True
    assert calls[2]["allow_refresh"] is True
