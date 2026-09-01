"""Auth slice routes: OAuth login/callback, step-up link, logout."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, cast
from urllib.parse import urlencode

from authlib.integrations.base_client import OAuthError
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import (
    clear_session_cookies,
    get_auth_settings,
    get_db,
    new_csrf_token,
    require_auth,
    require_onboarding_auth,
    set_session_cookies,
)
from ai_stp_api.envelope import success_response
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.geoip import approximate_location
from ai_stp_api.session import AuthContext, issue_session, revoke_session
from ai_stp_api.settings import AuthSettings
from ai_stp_api.slices.auth.domain import validate_provider
from ai_stp_api.slices.auth.oauth import get_client, profile_from_token
from ai_stp_api.slices.auth.onboarding import complete_onboarding, required_revisions
from ai_stp_api.slices.auth.service import (
    resolve_login_identity,
    resolve_step_up_link,
    unlink_identity,
)
from ai_stp_contracts.auth import LegalOnboardingCompleteRequest
from ai_stp_contracts.identity import AccountPrivacyUpdate
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.logging import get_logger
from ai_stp_platform.models import Account, Device, OAuthIdentity

router = APIRouter(tags=["auth"])
_log = get_logger("auth")

_SESSION_KEY_LINK_ACCOUNT = "oauth_link_account_id"
_SESSION_KEY_FLOW = "oauth_flow"
_SESSION_KEY_CLIENT = "oauth_client"
_WEB_DEVICE_TYPE = "web"
_SESSION_KEY_RETURN_TO = "oauth_return_to"
_DEFAULT_WEB_RETURN_TO = "/ru/account"


def _oauth(request: Request) -> Any:
    return request.app.state.oauth


def _wants_json(request: Request, response_mode: str | None) -> bool:
    if response_mode == "json":
        return True
    if response_mode == "redirect":
        return False
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept


def _callback_uri(request: Request, auth: AuthSettings, provider: str) -> str:
    """The console-registered callback for the origin this flow started on.

    Must match an Authorized redirect URI in the provider console exactly, so
    the origin is chosen from the list this deployment declares rather than read
    from `Host`, which a proxy controls. The request may *select* among declared
    origins; it cannot introduce one.

    `#62` is why this is per-request. The handshake state lives in a session
    cookie on the origin that started the flow. With one pinned callback and two
    served domains, a sign-in begun on the second domain landed on the first,
    `authorize_access_token` found no state, and the user saw "Sign-in failed" —
    twice in one production log, both from the canonical domain.
    """
    declared = auth.oauth_callback_bases()
    origin = f"{request.url.scheme}://{request.url.netloc}".rstrip("/")
    base = origin if origin in declared else declared[0]
    return f"{base}/v1/auth/{provider}/callback"


def _safe_return_to(value: str | None) -> str | None:
    """Accept only same-origin relative paths (must start with a single '/')."""
    if value is None:
        return None
    if not value.startswith("/") or value.startswith("//"):
        return None
    if "://" in value or "\\" in value or "\n" in value or "\r" in value:
        return None
    return value


def _web_return_location(auth: AuthSettings, return_to: str | None) -> str:
    path = _safe_return_to(return_to) or _DEFAULT_WEB_RETURN_TO
    return f"{auth.public_base_url.rstrip('/')}{path}"


def _locale_from_return_to(return_to: str | None) -> str:
    path = _safe_return_to(return_to)
    if path is None:
        return "ru"
    head = path.strip("/").split("/", 1)[0]
    return head if head in {"en", "ru"} else "ru"


def _web_login_status_location(
    auth: AuthSettings,
    *,
    return_to: str | None,
    status: str,
) -> str:
    """Browser-facing login URL with a safe status query (error|cancel|conflict)."""
    locale = _locale_from_return_to(return_to)
    params = urlencode({"status": status})
    return f"{auth.public_base_url.rstrip('/')}/{locale}/login?{params}"


def _prefer_browser_redirect(request: Request, client_hint: str | None) -> bool:
    """True when the OAuth browser half should leave via 303, not JSON error body."""
    if client_hint == "web":
        return True
    if client_hint == "cli":
        return False
    return not _wants_json(request, None)


@router.get("/auth/{provider}/login", response_model=None)
async def oauth_login(
    provider: str,
    request: Request,
    auth: Annotated[AuthSettings, Depends(get_auth_settings)],
    client: str | None = Query(default=None, description="cli or web"),
    return_to: str | None = Query(
        default=None,
        description="Relative post-login path for web clients (must start with /)",
    ),
) -> RedirectResponse:
    """Start the OAuth authorization redirect with PKCE (REQ-1002)."""
    try:
        name = validate_provider(provider)
    except ValueError as exc:
        raise ApiError(ErrorCategory.VALIDATION, "unsupported oauth provider") from exc
    if not auth.provider_enabled(name):
        raise ApiError(ErrorCategory.DEPENDENCY, "oauth provider is not configured")

    # Transient handshake state lives in the signed SessionMiddleware cookie.
    request.session[_SESSION_KEY_FLOW] = "login"
    request.session.pop(_SESSION_KEY_LINK_ACCOUNT, None)
    if client in {"cli", "web"}:
        request.session[_SESSION_KEY_CLIENT] = client
    safe_return = _safe_return_to(return_to)
    if safe_return is not None:
        request.session[_SESSION_KEY_RETURN_TO] = safe_return
    else:
        request.session.pop(_SESSION_KEY_RETURN_TO, None)

    remote = get_client(_oauth(request), name)
    redirect_uri = _callback_uri(request, auth, name)
    return await remote.authorize_redirect(request, redirect_uri)


@router.get("/auth/{provider}/callback", response_model=None)
async def oauth_callback(
    provider: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[AuthSettings, Depends(get_auth_settings)],
    response_mode: str | None = Query(default=None),
) -> JSONResponse | RedirectResponse:
    """Complete OAuth, resolve identity and issue an opaque session."""
    # Peek handshake hints before authlib may clear session on error paths.
    client_hint_early = request.session.get(_SESSION_KEY_CLIENT)
    return_to_early = request.session.get(_SESSION_KEY_RETURN_TO)
    client_hint_early = client_hint_early if isinstance(client_hint_early, str) else None
    return_to_early = return_to_early if isinstance(return_to_early, str) else None

    try:
        name = validate_provider(provider)
    except ValueError as exc:
        raise ApiError(ErrorCategory.VALIDATION, "unsupported oauth provider") from exc

    def _fail(
        status: str, category: ErrorCategory, message: str
    ) -> JSONResponse | RedirectResponse:
        if _prefer_browser_redirect(request, client_hint_early):
            return RedirectResponse(
                url=_web_login_status_location(auth, return_to=return_to_early, status=status),
                status_code=303,
            )
        raise ApiError(category, message)

    remote = get_client(_oauth(request), name)
    try:
        token = await remote.authorize_access_token(request)
    except OAuthError:
        _log.info("oauth_callback_failed", provider=name, reason="oauth_error")
        return _fail("error", ErrorCategory.AUTH_REQUIRED, "authentication failed")
    except Exception:
        _log.info("oauth_callback_failed", provider=name, reason="exchange_failed")
        return _fail("error", ErrorCategory.AUTH_REQUIRED, "authentication failed")

    # Never log token contents.
    try:
        profile = await profile_from_token(_oauth(request), name, token)
    except ApiError:
        return _fail("error", ErrorCategory.AUTH_REQUIRED, "authentication failed")

    flow = request.session.pop(_SESSION_KEY_FLOW, "login")
    link_account_id = request.session.pop(_SESSION_KEY_LINK_ACCOUNT, None)
    client_hint = request.session.pop(_SESSION_KEY_CLIENT, None)
    return_to = request.session.pop(_SESSION_KEY_RETURN_TO, None)
    client_hint = client_hint if isinstance(client_hint, str) else client_hint_early
    return_to = return_to if isinstance(return_to, str) else return_to_early

    try:
        if flow == "link" and link_account_id:
            decision = await resolve_step_up_link(
                db, session_account_id=str(link_account_id), profile=profile
            )
        else:
            decision = await resolve_login_identity(db, profile)
    except ApiError as exc:
        if exc.category is ErrorCategory.CONFLICT:
            return _fail("conflict", ErrorCategory.CONFLICT, exc.message)
        if exc.category is ErrorCategory.AUTH_REQUIRED:
            return _fail("error", ErrorCategory.AUTH_REQUIRED, "authentication failed")
        if _prefer_browser_redirect(request, client_hint):
            return _fail("error", exc.category, exc.message)
        raise

    web_device: Device | None = None
    if client_hint == "web" or (client_hint != "cli" and not _wants_json(request, response_mode)):
        location = approximate_location(
            request.headers.get("x-ai-stp-client-ip"), auth.geoip_city_db_path
        )
        if location is None:
            forwarded_country = request.headers.get("x-vercel-ip-country") or request.headers.get(
                "cf-ipcountry"
            )
            forwarded_city = request.headers.get("x-vercel-ip-city")
            location = (
                ", ".join(part for part in (forwarded_city, forwarded_country) if part) or None
            )
        remembered_id = request.cookies.get(auth.device_cookie_name)
        if remembered_id:
            web_device = await db.scalar(
                select(Device).where(
                    Device.id == remembered_id,
                    Device.account_id == decision.account_id,
                    Device.device_type == _WEB_DEVICE_TYPE,
                    Device.state == "active",
                )
            )
        if web_device is None:
            web_device_id = new_id("device")
            web_device = Device(
                id=web_device_id,
                account_id=decision.account_id,
                public_key=f"web:{web_device_id}",
                device_type=_WEB_DEVICE_TYPE,
                state="active",
            )
            db.add(web_device)
        web_device.approximate_location = location
        web_device.user_agent = (request.headers.get("user-agent") or "")[:512] or None
        web_device.last_seen_at = datetime.now(UTC)
        await db.flush()

    account = await db.get(Account, decision.account_id)
    if account is None:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication failed")
    pending_onboarding = account.status == "onboarding_pending"

    issued = await issue_session(
        db,
        account_id=decision.account_id,
        device_id=web_device.id if web_device else None,
        ttl_seconds=auth.session_ttl_seconds,
    )

    # Web clients (explicit client=web or non-JSON Accept) leave with a redirect
    # that carries Set-Cookie. CLI/json keeps the session_token body.
    wants_json = client_hint == "cli" or (
        client_hint != "web" and _wants_json(request, response_mode)
    )
    csrf = new_csrf_token()
    if wants_json and pending_onboarding:
        raise ApiError(ErrorCategory.PERMISSION, "complete legal onboarding in the web service")
    if wants_json:
        data: dict[str, object] = {
            "account_id": decision.account_id,
            "link_state": decision.state.value,
            "operation_id": new_id("operation"),
            "session_token": issued.raw_token,
        }
        response: JSONResponse | RedirectResponse = success_response(
            request_id=request.state.request_id,
            data=data,
            operation_id=str(data["operation_id"]),
        )
    else:
        if pending_onboarding:
            locale = _locale_from_return_to(return_to if isinstance(return_to, str) else None)
            target = _safe_return_to(return_to if isinstance(return_to, str) else None)
            params = urlencode({"returnTo": target}) if target else ""
            location = f"{auth.public_base_url.rstrip('/')}/{locale}/onboarding"
            if params:
                location = f"{location}?{params}"
        else:
            location = _web_return_location(auth, return_to if isinstance(return_to, str) else None)
        response = RedirectResponse(url=location, status_code=303)
    set_session_cookies(response, auth=auth, raw_token=issued.raw_token, csrf_token=csrf)
    if web_device is not None:
        response.set_cookie(
            key=auth.device_cookie_name,
            value=web_device.id,
            httponly=True,
            secure=auth.cookie_secure,
            samesite=auth.cookie_samesite,  # type: ignore[arg-type]
            path="/",
            max_age=auth.session_ttl_seconds,
        )
    return response


# Two decorators rather than `api_route(methods=["GET", "POST"])`. FastAPI
# derives an operation identifier from the handler name, the path and the
# *first* method of a set, so one registration for two methods emits the same
# identifier twice — a document no client generator can turn into two callable
# functions. Registering twice gives `..._get` and `..._post`.
@router.get("/auth/link/{provider}", response_model=None)
@router.post("/auth/link/{provider}", response_model=None)
async def start_step_up_link(
    provider: str,
    request: Request,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    auth: Annotated[AuthSettings, Depends(get_auth_settings)],
    return_to: str | None = Query(
        default=None,
        description="Relative post-link path for web clients (must start with /)",
    ),
) -> JSONResponse | RedirectResponse:
    """Start step-up OAuth to attach another identity (REQ-203).

    Browser clients MUST navigate here directly (GET) so the OAuth handshake
    cookie (state/PKCE) is set on the browser. A server-side fetch would keep
    that cookie on the web container and the provider callback would fail.
    """
    try:
        name = validate_provider(provider)
    except ValueError as exc:
        raise ApiError(ErrorCategory.VALIDATION, "unsupported oauth provider") from exc
    if not auth.provider_enabled(name):
        raise ApiError(ErrorCategory.DEPENDENCY, "oauth provider is not configured")

    request.session[_SESSION_KEY_FLOW] = "link"
    request.session[_SESSION_KEY_LINK_ACCOUNT] = ctx.account_id
    # CLI/json clients keep the session_token response path; browsers get Set-Cookie.
    request.session[_SESSION_KEY_CLIENT] = "cli" if _wants_json(request, None) else "web"
    safe_return = _safe_return_to(return_to)
    if safe_return is not None:
        request.session[_SESSION_KEY_RETURN_TO] = safe_return
    else:
        request.session.pop(_SESSION_KEY_RETURN_TO, None)

    remote = get_client(_oauth(request), name)
    redirect_uri = _callback_uri(request, auth, name)
    redirect = await remote.authorize_redirect(request, redirect_uri)
    # Browser clients follow the redirect; CLI/json clients receive the URL.
    if _wants_json(request, None):
        location = redirect.headers.get("location", "")
        return success_response(
            request_id=request.state.request_id,
            data={"authorization_url": location},
        )
    return redirect


@router.post("/auth/logout", response_model=None)
async def logout(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_onboarding_auth)],
    auth: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> JSONResponse:
    """Revoke the current session; replay of the old token is rejected."""
    del request
    revoked = await revoke_session(db, ctx.session_id)
    response = JSONResponse(
        content={"schema_version": 1, "revoked": revoked},
        status_code=200,
    )
    clear_session_cookies(response, auth=auth)
    return response


@router.get("/auth/me", response_model=None)
async def current_account(
    request: Request,
    ctx: Annotated[AuthContext, Depends(require_onboarding_auth)],
) -> JSONResponse:
    """Return the authenticated account id (resource body, no envelope)."""
    del request
    return JSONResponse(
        content={
            "schema_version": 1,
            "account_id": ctx.account_id,
            "device_id": ctx.device_id,
            "account_status": ctx.account_status,
        },
        status_code=200,
    )


@router.get("/auth/onboarding", response_model=None)
async def read_legal_onboarding(
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_onboarding_auth)],
    locale: Annotated[str, Query()] = "en",
) -> JSONResponse:
    """Return the exact revisions a pending account must accept."""
    return JSONResponse(
        content=await required_revisions(db, account_id=ctx.account_id, locale=locale)
    )


@router.post("/auth/onboarding/complete", response_model=None)
async def complete_legal_onboarding(
    payload: LegalOnboardingCompleteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_onboarding_auth)],
    locale: Annotated[str, Query()] = "en",
) -> JSONResponse:
    """Record exact acceptances and activate the current account."""
    return JSONResponse(
        content=await complete_onboarding(
            db,
            account_id=ctx.account_id,
            locale=locale,
            service_rules_revision_id=payload.service_rules_revision_id,
            personal_data_consent_revision_id=payload.personal_data_consent_revision_id,
        )
    )


@router.post("/auth/device", response_model=None)
async def start_device_auth(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> JSONResponse:
    """Start RFC 8628 device-code authorization (CLI)."""
    from ai_stp_api.slices.auth.device_flow import start_device_authorization, verification_uris
    from ai_stp_contracts.auth import DeviceAuthorizationRequest

    try:
        body = DeviceAuthorizationRequest.model_validate(await request.json())
    except Exception as exc:
        raise ApiError(ErrorCategory.VALIDATION, "request validation failed") from exc

    row = await start_device_authorization(db, provider=body.provider, auth=auth)
    plain, complete = verification_uris(auth, row.user_code)
    expires_in = max(60, int((row.expires_at - datetime.now(UTC)).total_seconds()))
    return JSONResponse(
        content={
            "schema_version": 1,
            "device_code": row.device_code,
            "user_code": row.user_code,
            "verification_uri": plain,
            "verification_uri_complete": complete,
            "expires_in": min(expires_in, 1800),
            "interval": row.interval_seconds,
        },
        status_code=201,
    )


@router.post("/auth/device/token", response_model=None)
async def exchange_device_auth(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> JSONResponse:
    """Poll device-code exchange and bind the device public key."""
    from ai_stp_api.slices.auth.device_flow import exchange_device_code
    from ai_stp_contracts.auth import DeviceTokenRequest

    try:
        body = DeviceTokenRequest.model_validate(await request.json())
    except Exception as exc:
        raise ApiError(ErrorCategory.VALIDATION, "request validation failed") from exc

    payload = await exchange_device_code(
        db,
        auth=auth,
        device_code=body.device_code,
        device_id=body.device_id,
        public_key=body.public_key,
        display_name=body.display_name,
    )
    return JSONResponse(content=payload, status_code=200)


@router.post("/auth/device/approve", response_model=None)
async def approve_device_auth(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    """Browser-approved binding of a user_code to the signed-in account."""
    from ai_stp_api.slices.auth.device_flow import approve_device_authorization

    try:
        # request.json() is Any; annotating as object forces the narrowing below
        # instead of letting an unknown type leak into the handler.
        raw: object = await request.json()
    except Exception as exc:
        raise ApiError(ErrorCategory.VALIDATION, "request validation failed") from exc
    if not isinstance(raw, dict):
        raise ApiError(ErrorCategory.VALIDATION, "user_code required")
    body = cast("dict[str, object]", raw)
    user_code = body.get("user_code")
    if not isinstance(user_code, str) or not user_code.strip():
        raise ApiError(ErrorCategory.VALIDATION, "user_code required")
    row = await approve_device_authorization(db, user_code=user_code, account_id=ctx.account_id)
    return JSONResponse(
        content={
            "schema_version": 1,
            "user_code": row.user_code,
            "status": row.status,
            "provider": row.provider,
        },
        status_code=200,
    )


def _wire_timestamp(value: datetime) -> str:
    """Canonical UTC millisecond timestamp (docs/contracts/canonical-data.md)."""
    moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if moment.utcoffset() != UTC.utcoffset(None):
        moment = moment.astimezone(UTC)
    return format_timestamp(moment)


async def _account_profile_body(db: AsyncSession, account_id: str) -> dict[str, object]:
    """Build the identity-account-profile resource body (no email on the wire)."""
    account = await db.get(Account, account_id)
    if account is None:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication required")

    result = await db.execute(
        select(OAuthIdentity)
        .where(
            OAuthIdentity.account_id == account_id,
            OAuthIdentity.state.in_(("linked", "pending")),
        )
        .order_by(OAuthIdentity.created_at.asc())
    )
    identities: list[dict[str, object]] = []
    for row in result.scalars().all():
        identities.append(
            {
                "provider": row.provider,
                "linked_at": _wire_timestamp(row.created_at),
                "avatar_url": row.avatar_url,
                "display_name": row.display_name,
            }
        )
    # Contract requires at least one identity for a sign-in-capable account.
    if not identities:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication required")

    return {
        "schema_version": 1,
        "account_id": account.id,
        "created_at": _wire_timestamp(account.created_at),
        "identities": identities,
        "show_profile_publicly": account.show_profile_publicly,
        "allow_publisher_listing": account.allow_publisher_listing,
    }


@router.get("/account", response_model=None)
async def read_account(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    """Read the current account profile (OpenAPI identity-account-profile).

    Success carries the resource body itself (docs/contracts/http-api.md), not
    a CLI success envelope. No email address is returned (SPEC-013).
    """
    del request  # correlation already attached by middleware when needed
    return JSONResponse(content=await _account_profile_body(db, ctx.account_id))


@router.put("/account/privacy", response_model=None)
async def update_account_privacy(
    payload: AccountPrivacyUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    """Replace the authenticated account's privacy preferences."""
    account = await db.get(Account, ctx.account_id)
    if account is None:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "authentication required")
    account.show_profile_publicly = payload.show_profile_publicly
    account.allow_publisher_listing = payload.allow_publisher_listing
    await db.commit()
    return JSONResponse(content=await _account_profile_body(db, ctx.account_id))


@router.delete("/account/identities/{provider}", response_model=None)
async def unlink_account_identity(
    provider: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> JSONResponse:
    """Unlink one OAuth identity. The last active identity cannot be removed."""
    del request
    try:
        name = validate_provider(provider)
    except ValueError as exc:
        raise ApiError(ErrorCategory.VALIDATION, "unsupported oauth provider") from exc

    await unlink_identity(db, account_id=ctx.account_id, provider=name)
    return JSONResponse(content=await _account_profile_body(db, ctx.account_id))
