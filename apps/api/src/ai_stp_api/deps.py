"""Shared FastAPI dependencies: DB session, opaque auth, CSRF (ADR-0041)."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext, verify_raw_token
from ai_stp_api.settings import AuthSettings, Settings

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_BEARER_PREFIX = "bearer "


def get_settings(request: Request) -> Settings:
    """Return the process settings bound on the app state."""
    return request.app.state.settings


def get_auth_settings(request: Request) -> AuthSettings:
    """Return the auth settings group."""
    return request.app.state.settings.auth


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped async DB session and commit on success."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header is None:
        return None
    if not header.lower().startswith(_BEARER_PREFIX):
        return None
    token = header[len(_BEARER_PREFIX) :].strip()
    return token or None


def _extract_cookie_token(request: Request, cookie_name: str) -> str | None:
    return request.cookies.get(cookie_name) or None


def ensure_csrf(
    request: Request,
    *,
    auth: AuthSettings,
    via_cookie: bool,
) -> None:
    """Enforce double-submit CSRF when the session arrived via cookie.

    Bearer (CLI) transport is exempt. Safe methods are exempt.
    """
    if not via_cookie:
        return
    if request.method.upper() not in _UNSAFE_METHODS:
        return
    cookie_value = request.cookies.get(auth.csrf_cookie_name)
    header_value = request.headers.get(auth.csrf_header_name)
    if (
        not cookie_value
        or not header_value
        or not secrets.compare_digest(cookie_value, header_value)
    ):
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "csrf validation failed")


async def optional_auth(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> AuthContext | None:
    """Resolve a session when present. Invalid credentials still fail."""
    if (
        _extract_bearer(request) is None
        and _extract_cookie_token(request, auth.cookie_name) is None
    ):
        return None
    return await require_auth(request, db, auth)


async def require_auth(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> AuthContext:
    """Resolve the opaque session from Bearer or cookie and enforce CSRF."""
    bearer = _extract_bearer(request)
    cookie = _extract_cookie_token(request, auth.cookie_name)
    if bearer is not None:
        raw, via_cookie = bearer, False
    elif cookie is not None:
        raw, via_cookie = cookie, True
    else:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication required")

    ensure_csrf(request, auth=auth, via_cookie=via_cookie)
    return await verify_raw_token(
        db,
        raw,
        admin_account_ids=auth.admin_ids(),
        via_cookie=via_cookie,
    )


def set_session_cookies(
    response: Response,
    *,
    auth: AuthSettings,
    raw_token: str,
    csrf_token: str,
) -> None:
    """Attach HttpOnly session cookie and readable CSRF cookie for web clients."""
    response.set_cookie(
        key=auth.cookie_name,
        value=raw_token,
        httponly=True,
        secure=auth.cookie_secure,
        samesite=auth.cookie_samesite,  # type: ignore[arg-type]
        path="/",
        max_age=auth.session_ttl_seconds,
    )
    response.set_cookie(
        key=auth.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=auth.cookie_secure,
        samesite=auth.cookie_samesite,  # type: ignore[arg-type]
        path="/",
        max_age=auth.session_ttl_seconds,
    )


def clear_session_cookies(response: Response, *, auth: AuthSettings) -> None:
    """Expire session and CSRF cookies on logout."""
    response.delete_cookie(auth.cookie_name, path="/")
    response.delete_cookie(auth.csrf_cookie_name, path="/")


def new_csrf_token() -> str:
    """Mint a double-submit CSRF token (not a session secret)."""
    return secrets.token_urlsafe(32)
