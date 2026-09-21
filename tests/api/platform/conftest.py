"""ASGI fixtures for authenticated platform API tests.

PostgreSQL isolation fixtures are local to this tree (testing.md: platform
conftest hierarchy). The machinery itself lives in `tests/support/postgres.py`
and `tests/support/api_settings.py`, shared with the CLI↔API boundary tree —
fixture names stay identical because the root conftest marks `pg` from them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Protocol

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Re-exported: sibling test modules import this name from this conftest.
from tests.support.api_settings import TEST_CURSOR_SECRET as TEST_CURSOR_SECRET
from tests.support.api_settings import make_settings, make_test_auth
from tests.support.postgres import (
    isolated_database,
    migrated_database,
    migrated_template,
)

from ai_stp_api.app import create_app
from ai_stp_api.settings import AuthSettings, Settings

pytestmark = pytest.mark.platform

TEST_DB_ENV = "AI_STP_TEST_DB_URL"


class SettingsFactory(Protocol):
    """Typed factory for building API Settings in tests."""

    def __call__(
        self,
        *,
        database_url: str | None = None,
        auth: AuthSettings | None = None,
        **auth_overrides: object,
    ) -> Settings: ...


@pytest.fixture()
def isolated_database_url() -> Iterator[str]:
    """Create a temporary PostgreSQL database and remove it after one test."""
    with isolated_database(f"{TEST_DB_ENV} is required for PostgreSQL API tests") as url:
        yield url


@pytest.fixture(scope="session")
def pg_migrated_template() -> Iterator[str | None]:
    """One fully migrated database per xdist worker; individual tests clone it.

    Session scope never calls `pytest.skip`: a skip there would abandon every
    test in the worker, not just the ones that need the database. Without
    `TEST_DB_ENV` this yields None and the function-scoped fixture below skips
    on exactly the same condition.
    """
    with migrated_template() as database:
        yield database


@pytest.fixture()
def migrated_database_url(
    pg_migrated_template: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[str]:
    """Clone the per-worker migrated template into a disposable database.

    The skip message matches `isolated_database_url`: the same environment
    variable gates both, and a test that needs migrations needs the server
    behind it just as much.
    """
    with migrated_database(
        pg_migrated_template,
        monkeypatch,
        skip_reason=f"{TEST_DB_ENV} is required for PostgreSQL API tests",
    ) as url:
        yield url


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
