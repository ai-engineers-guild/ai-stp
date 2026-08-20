"""ASGI fixtures for authenticated platform API tests.

PostgreSQL isolation fixtures are local to this tree (testing.md: platform
conftest hierarchy; do not import CLI or sibling-area conftest modules).
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Protocol

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_stp_api.app import create_app
from ai_stp_api.settings import AuthSettings, CatalogSettings, ServiceSettings, Settings
from ai_stp_platform.settings import DatabaseSettings, StorageSettings

pytestmark = pytest.mark.platform

_TEST_SECRET = "test-secret-key-at-least-32-bytes-long!!"
TEST_CURSOR_SECRET = "test-catalog-cursor-secret-32b-min!!"
_UNREACHABLE = "127.0.0.1:59999"
TEST_DB_ENV = "AI_STP_TEST_DB_URL"
_VALID_DATABASE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


class SettingsFactory(Protocol):
    """Typed factory for building API Settings in tests."""

    def __call__(
        self,
        *,
        database_url: str | None = None,
        auth: AuthSettings | None = None,
        **auth_overrides: object,
    ) -> Settings: ...


def make_test_auth(**overrides: object) -> AuthSettings:
    """Build AuthSettings with safe test defaults."""
    values: dict[str, object] = {
        "secret_key": _TEST_SECRET,
        "cookie_secure": False,
        "google_client_id": "google-test-id",
        "google_client_secret": "google-test-secret",
        "github_client_id": "github-test-id",
        "github_client_secret": "github-test-secret",
        "public_base_url": "http://test",
    }
    values.update(overrides)
    return AuthSettings(**values)  # type: ignore[arg-type]


def make_settings(
    log_dir: Path,
    *,
    database_url: str | None = None,
    auth: AuthSettings | None = None,
    catalog: CatalogSettings | None = None,
) -> Settings:
    """Compose Settings for ASGI tests."""
    url = database_url or f"postgresql+asyncpg://u:p@{_UNREACHABLE}/db"
    return Settings(
        service=ServiceSettings(environment="test", version="0.0.0-test", log_dir=log_dir),
        database=DatabaseSettings(url=url),
        storage=StorageSettings(
            endpoint=f"http://{_UNREACHABLE}",
            bucket="test",
            access_key_id="test-access",
            secret_access_key="test-secret",
        ),
        auth=auth or make_test_auth(),
        catalog=catalog
        or CatalogSettings(cursor_signing_secret=TEST_CURSOR_SECRET, usage_enabled=False),
    )


def _run(coro: object) -> None:
    asyncio.run(coro)  # type: ignore[arg-type]


def _database_name() -> str:
    return f"ai_stp_it_{uuid.uuid4().hex[:24]}"


def _quote_identifier(identifier: str) -> str:
    if not _VALID_DATABASE_NAME.fullmatch(identifier):
        raise ValueError(f"unsafe PostgreSQL identifier: {identifier!r}")
    return f'"{identifier}"'


def _url_with_database(url: str, database: str) -> str:
    from sqlalchemy.engine import make_url

    # str(URL) redacts the password as "***"; render explicitly for a usable DSN.
    return make_url(url).set(database=database).render_as_string(hide_password=False)


async def _execute_admin(url: str, statement: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


@pytest.fixture()
def isolated_database_url() -> Iterator[str]:
    """Create a temporary PostgreSQL database and remove it after one test."""
    template_url = os.environ.get(TEST_DB_ENV)
    if not template_url:
        pytest.skip(f"{TEST_DB_ENV} is required for PostgreSQL integration tests")

    database = _database_name()
    quoted = _quote_identifier(database)
    admin_url = template_url
    _run(_execute_admin(admin_url, f"CREATE DATABASE {quoted} TEMPLATE template0"))
    try:
        yield _url_with_database(template_url, database)
    finally:
        _run(_execute_admin(admin_url, f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)"))


@pytest.fixture()
def migrated_database_url(
    isolated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[str]:
    """Apply all Alembic migrations to an isolated PostgreSQL database."""
    monkeypatch.setenv("AI_STP_DB_URL", isolated_database_url)
    command.upgrade(Config("alembic.ini"), "head")
    yield isolated_database_url


@pytest.fixture
def auth_settings() -> AuthSettings:
    """Default AuthSettings for tests."""
    return make_test_auth()


@pytest.fixture
def settings_factory(tmp_path: Path) -> SettingsFactory:
    """Return a callable that builds Settings for the test tmp_path."""

    def _factory(
        *,
        database_url: str | None = None,
        auth: AuthSettings | None = None,
        **auth_overrides: object,
    ) -> Settings:
        resolved_auth = auth
        if resolved_auth is None and auth_overrides:
            resolved_auth = make_test_auth(**auth_overrides)
        elif resolved_auth is None:
            resolved_auth = make_test_auth()
        return make_settings(tmp_path, database_url=database_url, auth=resolved_auth)

    return _factory


@pytest_asyncio.fixture
async def api_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """HTTP client against an app with unreachable dependencies (no DB tests)."""
    app = create_app(make_settings(tmp_path))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest_asyncio.fixture
async def db_api_client(
    tmp_path: Path,
    migrated_database_url: str,
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession], Settings]]:
    """HTTP client + sessionmaker bound to an isolated migrated PostgreSQL DB."""
    settings = make_settings(tmp_path, database_url=migrated_database_url)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app.state.sessionmaker, settings
