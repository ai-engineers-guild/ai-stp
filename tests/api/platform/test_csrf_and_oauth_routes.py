"""CSRF double-submit and OAuth route wiring tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.responses import RedirectResponse

from ai_stp_api.app import create_app
from ai_stp_api.session import issue_session
from ai_stp_api.settings import Settings
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, AccountSession, Device, OAuthIdentity

pytestmark = pytest.mark.platform


@pytest_asyncio.fixture
async def app_client(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


def test_oauth_callback_base_prefers_explicit_redirect_origin() -> None:
    """Provider redirect_uri may differ from the public web origin (dev :8000 vs :8080)."""
    from tests.api.platform.conftest import make_test_auth

    auth = make_test_auth(
        public_base_url="http://localhost:8080",
        oauth_redirect_base_url="http://localhost:8000",
    )
    assert auth.oauth_callback_base() == "http://localhost:8000"
    defaulted = make_test_auth(public_base_url="http://localhost:8080")
    assert defaulted.oauth_callback_base() == "http://localhost:8080"


async def test_oauth_login_redirects_when_provider_configured(
    app_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    fake = AsyncMock(return_value=RedirectResponse(url="https://accounts.google.com/o/oauth2"))
    # Patch the registered google client authorize_redirect.
    oauth = app.state.oauth  # type: ignore[attr-defined]
    google = oauth.create_client("google")
    assert google is not None
    google.authorize_redirect = fake  # type: ignore[method-assign]

    response = await client.get("/v1/auth/google/login", follow_redirects=False)
    assert response.status_code in {302, 307}
    fake.assert_awaited()


async def test_oauth_login_stores_web_client_and_return_to(
    app_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = app_client
    fake = AsyncMock(return_value=RedirectResponse(url="https://accounts.google.com/o/oauth2"))
    google = app.state.oauth.create_client("google")  # type: ignore[attr-defined]
    assert google is not None
    google.authorize_redirect = fake  # type: ignore[method-assign]

    response = await client.get(
        "/v1/auth/google/login",
        params={"client": "web", "return_to": "/en/account"},
        follow_redirects=False,
    )
    assert response.status_code in {302, 307}
    fake.assert_awaited()


async def test_oauth_login_unknown_provider_is_validation_error(
    app_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, _ = app_client
    response = await client.get("/v1/auth/facebook/login")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AI_STP_VALIDATION_ERROR"


async def test_cookie_transport_requires_csrf_on_unsafe_methods(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)
    engine = create_async_engine(migrated_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        db.add(account)
        await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        raw = issued.raw_token

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Cookie present, CSRF missing → 401 on POST.
            client.cookies.set(settings.auth.cookie_name, raw)
            missing = await client.post("/v1/auth/logout")
            assert missing.status_code == 401
            assert missing.json()["error"]["code"] == "AI_STP_AUTH_REQUIRED"

            # Matching double-submit CSRF → success.
            csrf = "csrf-test-token-value-0001"
            client.cookies.set(settings.auth.csrf_cookie_name, csrf)
            ok = await client.post(
                "/v1/auth/logout",
                headers={settings.auth.csrf_header_name: csrf},
            )
            assert ok.status_code == 200
            assert ok.json()["revoked"] is True

            # Replay of revoked session fails.
            again = await client.post(
                "/v1/auth/logout",
                headers={settings.auth.csrf_header_name: csrf},
            )
            assert again.status_code == 401

    await engine.dispose()


async def test_bearer_transport_skips_csrf(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)
    engine = create_async_engine(migrated_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        db.add(account)
        await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        raw = issued.raw_token

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/auth/logout",
                headers={"Authorization": f"Bearer {raw}"},
            )
            assert response.status_code == 200
            assert response.json()["revoked"] is True

    await engine.dispose()


async def test_oauth_callback_with_mocked_token_issues_session(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)

    token_payload = {
        "userinfo": {
            "sub": "callback-sub-1",
            "email": "callback@example.com",
            "email_verified": True,
        }
    }

    async with app.router.lifespan_context(app):
        async with app.state.sessionmaker() as db:
            account = Account(id=new_id("account"), status="active")
            db.add(account)
            db.add(
                OAuthIdentity(
                    account_id=account.id,
                    provider="google",
                    provider_subject="callback-sub-1",
                    email="callback@example.com",
                    email_verified=True,
                    state="linked",
                )
            )
            await db.commit()
        google = app.state.oauth.create_client("google")  # type: ignore[attr-defined]
        assert google is not None
        google.authorize_access_token = AsyncMock(return_value=token_payload)  # type: ignore[method-assign]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Prime SessionMiddleware cookie via a login hit with mocked redirect.
            google.authorize_redirect = AsyncMock(  # type: ignore[method-assign]
                return_value=RedirectResponse(url="https://example.invalid")
            )
            await client.get("/v1/auth/google/login", follow_redirects=False)

            response = await client.get(
                "/v1/auth/google/callback",
                headers={"Accept": "application/json"},
            )
            assert response.status_code == 200
            # CLI JSON branch still uses success envelope with session_token.
            payload = response.json()
            data = payload.get("data", payload)
            assert data["account_id"].startswith("account_")
            assert data["link_state"] == "linked"
            assert data["session_token"]

            me = await client.get(
                "/v1/auth/me",
                headers={"Authorization": f"Bearer {data['session_token']}"},
            )
            assert me.status_code == 200
            me_body = me.json()
            me_data = me_body.get("data", me_body)
            assert me_data["account_id"] == data["account_id"]


async def test_oauth_callback_web_client_redirects_with_session_cookies(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)

    token_payload = {
        "userinfo": {
            "sub": "callback-web-sub-1",
            "email": "web-callback@example.com",
            "email_verified": True,
        }
    }

    async with app.router.lifespan_context(app):
        google = app.state.oauth.create_client("google")  # type: ignore[attr-defined]
        assert google is not None
        google.authorize_access_token = AsyncMock(return_value=token_payload)  # type: ignore[method-assign]
        google.authorize_redirect = AsyncMock(  # type: ignore[method-assign]
            return_value=RedirectResponse(url="https://example.invalid")
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get(
                "/v1/auth/google/login",
                params={"client": "web", "return_to": "/en/account"},
                follow_redirects=False,
            )

            response = await client.get(
                "/v1/auth/google/callback",
                headers={"Accept": "text/html"},
                follow_redirects=False,
            )
            assert response.status_code == 303
            expected = (
                f"{settings.auth.public_base_url.rstrip('/')}/en/onboarding"
                "?returnTo=%2Fen%2Faccount"
            )
            assert response.headers["location"] == expected
            # Session and CSRF cookies must be set on the redirect response.
            cookie_blob = " ".join(
                value
                for name, value in response.headers.multi_items()
                if name.lower() == "set-cookie"
            )
            assert settings.auth.cookie_name in cookie_blob
            assert settings.auth.csrf_cookie_name in cookie_blob
            assert "session_token" not in (response.text or "")

            async with app.state.sessionmaker() as session:
                device = (await session.execute(select(Device))).scalar_one()
                assert device.device_type == "web"
                assert device.last_seen_at is not None
                assert device.user_agent is not None


async def test_oauth_callback_same_browser_reuses_device_and_rotates_session(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    """REQ-2313: repeat browser login must not multiply one browser device."""
    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)
    token_payload = {
        "userinfo": {
            "sub": "callback-web-repeat",
            "email": "web-repeat@example.com",
            "email_verified": True,
        }
    }

    async with app.router.lifespan_context(app):
        google = app.state.oauth.create_client("google")  # type: ignore[attr-defined]
        assert google is not None
        google.authorize_access_token = AsyncMock(return_value=token_payload)  # type: ignore[method-assign]
        google.authorize_redirect = AsyncMock(  # type: ignore[method-assign]
            return_value=RedirectResponse(url="https://example.invalid")
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            session_values: list[str] = []
            for _ in range(2):
                await client.get(
                    "/v1/auth/google/login",
                    params={"client": "web"},
                    follow_redirects=False,
                )
                response = await client.get(
                    "/v1/auth/google/callback",
                    headers={"Accept": "text/html"},
                    follow_redirects=False,
                )
                assert response.status_code == 303
                session_values.append(client.cookies[settings.auth.cookie_name])

            assert session_values[0] != session_values[1]
            async with app.state.sessionmaker() as session:
                devices = (await session.scalars(select(Device))).all()
                assert len(devices) == 1
                sessions = (await session.scalars(select(AccountSession))).all()
                assert len(sessions) == 2
                assert {row.device_id for row in sessions} == {devices[0].id}


async def test_oauth_callback_browser_error_redirects_to_login_not_json(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    """Failed browser OAuth must 303 to login?status=error (not raw JSON 401)."""
    from authlib.integrations.base_client import OAuthError

    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        google = app.state.oauth.create_client("google")  # type: ignore[attr-defined]
        assert google is not None
        google.authorize_redirect = AsyncMock(  # type: ignore[method-assign]
            return_value=RedirectResponse(url="https://example.invalid")
        )
        google.authorize_access_token = AsyncMock(  # type: ignore[method-assign]
            side_effect=OAuthError("invalid_grant", "state mismatch")
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get(
                "/v1/auth/google/login",
                params={"client": "web", "return_to": "/en/account"},
                follow_redirects=False,
            )
            response = await client.get(
                "/v1/auth/google/callback",
                headers={"Accept": "text/html"},
                follow_redirects=False,
            )
            assert response.status_code == 303
            location = response.headers.get("location", "")
            assert "/en/login" in location
            assert "status=error" in location


async def test_login_passes_oauth_redirect_base_as_redirect_uri(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    """redirect_uri must match provider console, not the public web origin alone."""
    from tests.api.platform.conftest import make_test_auth

    settings = settings_factory(
        database_url=migrated_database_url,
        auth=make_test_auth(
            public_base_url="http://localhost:8080",
            oauth_redirect_base_url="http://localhost:8000",
        ),
    )
    app = create_app(settings)
    captured: dict[str, str] = {}

    async def _capture_redirect(request: object, redirect_uri: str) -> RedirectResponse:
        del request
        captured["redirect_uri"] = redirect_uri
        return RedirectResponse(url="https://accounts.google.com/o/oauth2")

    async with app.router.lifespan_context(app):
        google = app.state.oauth.create_client("google")  # type: ignore[attr-defined]
        assert google is not None
        google.authorize_redirect = _capture_redirect  # type: ignore[method-assign]
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/v1/auth/google/login", follow_redirects=False)
            assert response.status_code in {302, 307}
            assert captured["redirect_uri"] == "http://localhost:8000/v1/auth/google/callback"


async def test_step_up_link_get_requires_auth(
    app_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, _ = app_client
    response = await client.get("/v1/auth/link/google", follow_redirects=False)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AI_STP_AUTH_REQUIRED"


async def test_step_up_link_get_redirects_and_sets_handshake_cookie(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    """Browser GET start must 302 and Set-Cookie session (OAuth state/PKCE)."""
    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)
    engine = create_async_engine(migrated_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with sessionmaker() as db:
        account = Account(id=new_id("account"))
        db.add(account)
        await db.flush()
        issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
        await db.commit()
        raw = issued.raw_token

    async with app.router.lifespan_context(app):
        google = app.state.oauth.create_client("google")  # type: ignore[attr-defined]
        assert google is not None
        google.authorize_redirect = AsyncMock(  # type: ignore[method-assign]
            return_value=RedirectResponse(url="https://accounts.google.com/o/oauth2/link")
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/v1/auth/link/google",
                params={"return_to": "/en/account"},
                headers={"Authorization": f"Bearer {raw}"},
                follow_redirects=False,
            )
            assert response.status_code in {302, 307}
            assert "accounts.google.com" in response.headers.get("location", "")
            # Handshake cookie must be on the redirect response (browser-owned).
            cookie_blob = " ".join(
                value
                for name, value in response.headers.multi_items()
                if name.lower() == "set-cookie"
            )
            assert "session=" in cookie_blob
            google.authorize_redirect.assert_awaited()  # type: ignore[attr-defined]
            call_args = google.authorize_redirect.await_args  # type: ignore[attr-defined]
            assert call_args is not None
            # redirect_uri is the second positional arg after request.
            expected_redirect = f"{settings.auth.oauth_callback_base()}/v1/auth/google/callback"
            assert call_args.args[1] == expected_redirect

    await engine.dispose()


async def test_unlink_http_and_account_profile_returns_avatar(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    """DELETE identity + GET /account expose avatar fields and block last unlink."""
    from sqlalchemy import select

    from ai_stp_api.slices.auth.domain import ProviderProfile
    from ai_stp_api.slices.auth.service import resolve_login_identity
    from ai_stp_platform.models import OAuthIdentity

    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)
    engine = create_async_engine(migrated_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with sessionmaker() as db:
        first = await resolve_login_identity(
            db,
            ProviderProfile(
                provider="google",
                subject="http-g",
                email="http-pair@example.com",
                email_verified=True,
                avatar_url="https://example.com/g.png",
                display_name="G User",
            ),
        )
        account = await db.get(Account, first.account_id)
        assert account is not None
        account.status = "active"
        await resolve_login_identity(
            db,
            ProviderProfile(
                provider="github",
                subject="http-gh",
                email="http-pair@example.com",
                email_verified=True,
                avatar_url="https://example.com/gh.png",
                display_name="GH User",
            ),
        )
        issued = await issue_session(
            db, account_id=first.account_id, device_id=None, ttl_seconds=3600
        )
        await db.commit()
        raw = issued.raw_token

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {raw}"}
            profile = await client.get("/v1/account", headers=headers)
            assert profile.status_code == 200
            body = profile.json()
            assert body["schema_version"] == 1
            # Wire timestamps must be canonical UTC milliseconds (SPEC-015).
            import re

            ts = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
            assert ts.match(body["created_at"])
            by_provider = {item["provider"]: item for item in body["identities"]}
            assert ts.match(by_provider["google"]["linked_at"])
            assert by_provider["google"]["avatar_url"] == "https://example.com/g.png"
            assert by_provider["google"]["display_name"] == "G User"
            assert by_provider["github"]["avatar_url"] == "https://example.com/gh.png"

            unlinked = await client.delete("/v1/account/identities/github", headers=headers)
            assert unlinked.status_code == 200
            remaining = unlinked.json()["identities"]
            assert len(remaining) == 1
            assert remaining[0]["provider"] == "google"

            blocked = await client.delete("/v1/account/identities/google", headers=headers)
            assert blocked.status_code == 400
            assert blocked.json()["error"]["code"] == "AI_STP_VALIDATION_ERROR"

    async with sessionmaker() as db:
        rows = (
            (
                await db.execute(
                    select(OAuthIdentity).where(OAuthIdentity.account_id == first.account_id)
                )
            )
            .scalars()
            .all()
        )
        states = {row.provider: row.state for row in rows}
        assert states["github"] == "revoked"
        assert states["google"] == "linked"

    await engine.dispose()


async def test_step_up_callback_links_second_provider_with_avatar(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    """OAuth callback with flow=link attaches second provider and stores avatar."""
    from ai_stp_api.slices.auth.domain import ProviderProfile
    from ai_stp_api.slices.auth.service import resolve_login_identity

    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)
    engine = create_async_engine(migrated_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with sessionmaker() as db:
        primary = await resolve_login_identity(
            db,
            ProviderProfile(
                provider="github",
                subject="primary-gh",
                email="owner@example.com",
                email_verified=True,
            ),
        )
        account = await db.get(Account, primary.account_id)
        assert account is not None
        account.status = "active"
        issued = await issue_session(
            db, account_id=primary.account_id, device_id=None, ttl_seconds=3600
        )
        await db.commit()
        raw = issued.raw_token

    token_payload = {
        "userinfo": {
            "sub": "google-step-up-sub",
            "email": "other@example.com",
            "email_verified": True,
            "picture": "https://lh3.googleusercontent.com/a/step-up",
            "name": "Step Up User",
        }
    }

    async with app.router.lifespan_context(app):
        google = app.state.oauth.create_client("google")  # type: ignore[attr-defined]
        assert google is not None
        google.authorize_access_token = AsyncMock(return_value=token_payload)  # type: ignore[method-assign]
        google.authorize_redirect = AsyncMock(  # type: ignore[method-assign]
            return_value=RedirectResponse(url="https://example.invalid/link")
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Authenticated browser start of step-up (sets flow=link in session cookie).
            start = await client.get(
                "/v1/auth/link/google",
                params={"return_to": "/en/account"},
                headers={"Authorization": f"Bearer {raw}"},
                follow_redirects=False,
            )
            assert start.status_code in {302, 307}

            callback = await client.get(
                "/v1/auth/google/callback",
                headers={"Accept": "text/html"},
                follow_redirects=False,
            )
            assert callback.status_code == 303
            assert callback.headers["location"].endswith("/en/account")

            # New session cookie after callback; use me then account via bearer from login path.
            # Re-issue: read account with original bearer still valid until revoked.
            account = await client.get(
                "/v1/account",
                headers={"Authorization": f"Bearer {raw}"},
            )
            # Original session still valid; profile should show both identities after commit.
            # After callback a new session was issued but the link is on the account.
            assert account.status_code == 200
            providers = {item["provider"] for item in account.json()["identities"]}
            assert providers == {"github", "google"}
            google_row = next(
                item for item in account.json()["identities"] if item["provider"] == "google"
            )
            assert google_row["avatar_url"] == "https://lh3.googleusercontent.com/a/step-up"
            assert google_row["display_name"] == "Step Up User"

    await engine.dispose()
