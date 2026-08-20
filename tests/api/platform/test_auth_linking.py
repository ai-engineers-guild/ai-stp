"""Integration tests for OAuth identity linking and sessions (SPEC-002)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_stp_api.app import create_app
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import hash_session_token, issue_session, verify_raw_token
from ai_stp_api.settings import Settings
from ai_stp_api.slices.auth.domain import ProviderProfile
from ai_stp_api.slices.auth.service import resolve_login_identity, resolve_step_up_link
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, AccountSession, AuditEvent, Device, OAuthIdentity

pytestmark = pytest.mark.platform


@pytest_asyncio.fixture
async def db(
    migrated_database_url: str,
) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
        await session.rollback()
    await engine.dispose()


async def test_first_login_creates_account_and_links_identity(db: AsyncSession) -> None:
    decision = await resolve_login_identity(
        db,
        ProviderProfile(
            provider="google",
            subject="google-sub-1",
            email="user1@example.com",
            email_verified=True,
            avatar_url="https://lh3.googleusercontent.com/a/test",
            display_name="User One",
        ),
    )
    await db.commit()
    assert decision.created_account is True
    assert decision.linked_identity is True
    assert decision.state.value == "linked"

    account = await db.get(Account, decision.account_id)
    assert account is not None
    identities = (
        (
            await db.execute(
                select(OAuthIdentity).where(OAuthIdentity.account_id == decision.account_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(identities) == 1
    assert identities[0].provider_subject == "google-sub-1"
    assert identities[0].email == "user1@example.com"
    assert identities[0].avatar_url == "https://lh3.googleusercontent.com/a/test"
    assert identities[0].display_name == "User One"


async def test_unlink_identity_and_relink_preserves_row(db: AsyncSession) -> None:
    from ai_stp_api.slices.auth.service import unlink_identity

    first = await resolve_login_identity(
        db,
        ProviderProfile(
            provider="google",
            subject="g-unlink",
            email="pair@example.com",
            email_verified=True,
            avatar_url="https://example.com/g.png",
            display_name="G",
        ),
    )
    second = await resolve_login_identity(
        db,
        ProviderProfile(
            provider="github",
            subject="99",
            email="pair@example.com",
            email_verified=True,
            avatar_url="https://example.com/gh.png",
            display_name="GH",
        ),
    )
    assert first.account_id == second.account_id
    await unlink_identity(db, account_id=first.account_id, provider="github")
    await db.commit()

    rows = (
        (
            await db.execute(
                select(OAuthIdentity).where(OAuthIdentity.account_id == first.account_id)
            )
        )
        .scalars()
        .all()
    )
    by_provider = {row.provider: row for row in rows}
    assert by_provider["github"].state == "revoked"
    assert by_provider["google"].state == "linked"

    # Last identity cannot be unlinked.
    with pytest.raises(ApiError) as blocked:
        await unlink_identity(db, account_id=first.account_id, provider="google")
    assert blocked.value.category == ErrorCategory.VALIDATION

    # Re-login re-links the revoked github identity and refreshes avatar.
    relinked = await resolve_login_identity(
        db,
        ProviderProfile(
            provider="github",
            subject="99",
            email="pair@example.com",
            email_verified=True,
            avatar_url="https://example.com/gh2.png",
            display_name="GH2",
        ),
    )
    await db.commit()
    assert relinked.linked_identity is True
    await db.refresh(by_provider["github"])
    assert by_provider["github"].state == "linked"
    assert by_provider["github"].avatar_url == "https://example.com/gh2.png"
    assert by_provider["github"].display_name == "GH2"


async def test_same_email_links_without_creating_second_account(db: AsyncSession) -> None:
    first = await resolve_login_identity(
        db,
        ProviderProfile(
            provider="google",
            subject="g-1",
            email="shared@example.com",
            email_verified=True,
        ),
    )
    second = await resolve_login_identity(
        db,
        ProviderProfile(
            provider="github",
            subject="42",
            email="Shared@Example.com",
            email_verified=True,
        ),
    )
    await db.commit()
    assert first.account_id == second.account_id
    assert second.created_account is False
    assert second.linked_identity is True


async def test_existing_identity_logs_into_same_account(db: AsyncSession) -> None:
    first = await resolve_login_identity(
        db,
        ProviderProfile(
            provider="google",
            subject="stable-sub",
            email="repeat@example.com",
            email_verified=True,
        ),
    )
    again = await resolve_login_identity(
        db,
        ProviderProfile(
            provider="google",
            subject="stable-sub",
            email="repeat@example.com",
            email_verified=True,
        ),
    )
    assert again.account_id == first.account_id
    assert again.linked_identity is False


async def test_step_up_conflict_when_identity_owned_by_other_populated_account(
    db: AsyncSession,
) -> None:
    a = await resolve_login_identity(
        db,
        ProviderProfile(
            provider="google",
            subject="a-sub",
            email="a@example.com",
            email_verified=True,
        ),
    )
    b = await resolve_login_identity(
        db,
        ProviderProfile(
            provider="github",
            subject="b-sub",
            email="b@example.com",
            email_verified=True,
        ),
    )
    # Populate both accounts with a device so merge would be silent-data-merge.
    db.add(
        Device(
            id=new_id("device"),
            account_id=a.account_id,
            public_key="pk-a-" + "x" * 20,
            state="active",
        )
    )
    db.add(
        Device(
            id=new_id("device"),
            account_id=b.account_id,
            public_key="pk-b-" + "x" * 20,
            state="active",
        )
    )
    await db.flush()

    with pytest.raises(ApiError) as exc:
        await resolve_step_up_link(
            db,
            session_account_id=a.account_id,
            profile=ProviderProfile(
                provider="github",
                subject="b-sub",
                email="b@example.com",
                email_verified=True,
            ),
        )
    assert exc.value.category is ErrorCategory.CONFLICT
    assert exc.value.message == "identity link conflict"


async def test_step_up_links_different_email_from_authenticated_session(
    db: AsyncSession,
) -> None:
    primary = await resolve_login_identity(
        db,
        ProviderProfile(
            provider="google",
            subject="primary-sub",
            email="primary@example.com",
            email_verified=True,
        ),
    )
    linked = await resolve_step_up_link(
        db,
        session_account_id=primary.account_id,
        profile=ProviderProfile(
            provider="github",
            subject="secondary-sub",
            email="other@example.com",
            email_verified=True,
        ),
    )
    assert linked.account_id == primary.account_id
    assert linked.linked_identity is True


async def test_unverified_email_fails_uniformly(db: AsyncSession) -> None:
    with pytest.raises(ApiError) as exc:
        await resolve_login_identity(
            db,
            ProviderProfile(
                provider="google",
                subject="no-verify",
                email="x@example.com",
                email_verified=False,
            ),
        )
    assert exc.value.category is ErrorCategory.AUTH_REQUIRED
    assert exc.value.message == "authentication failed"


async def test_session_issue_stores_hash_only_and_verify_works(db: AsyncSession) -> None:
    account = Account(id=new_id("account"))
    db.add(account)
    await db.flush()
    issued = await issue_session(db, account_id=account.id, device_id=None, ttl_seconds=3600)
    await db.commit()

    row = await db.get(AccountSession, issued.session.id)
    assert row is not None
    assert row.id == hash_session_token(issued.raw_token)
    assert row.id != issued.raw_token

    ctx = await verify_raw_token(
        db,
        issued.raw_token,
        admin_account_ids=frozenset(),
        via_cookie=False,
    )
    assert ctx.account_id == account.id

    # Logout / revoke → replay rejected.
    row.revoked_at = datetime.now(UTC)
    await db.commit()
    with pytest.raises(ApiError) as exc:
        await verify_raw_token(
            db,
            issued.raw_token,
            admin_account_ids=frozenset(),
            via_cookie=False,
        )
    assert exc.value.category is ErrorCategory.AUTH_REQUIRED


async def test_audit_events_emitted_without_secrets(db: AsyncSession) -> None:
    decision = await resolve_login_identity(
        db,
        ProviderProfile(
            provider="google",
            subject="audit-sub",
            email="audit@example.com",
            email_verified=True,
        ),
    )
    await db.commit()
    events = (
        (
            await db.execute(
                select(AuditEvent).where(AuditEvent.actor_account_id == decision.account_id)
            )
        )
        .scalars()
        .all()
    )
    assert events
    for event in events:
        rendered = repr(event.payload)
        assert "session_token" not in rendered
        assert "nonce" not in rendered
        assert "access_token" not in rendered


@pytest_asyncio.fixture
async def client_with_db(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> AsyncIterator[AsyncClient]:
    settings = settings_factory(database_url=migrated_database_url)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_logout_and_me_require_auth(client_with_db: AsyncClient) -> None:
    response = await client_with_db.get("/v1/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "AI_STP_AUTH_REQUIRED"
    # No token-like values in browser-visible error.
    assert "session" not in body["error"]["message"].lower()
