"""ASGI tests for the health and system slices (SPEC-017)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from importlib.metadata import version as installed_version
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from ai_stp_api.app import create_app
from ai_stp_api.errors import CATEGORY_CODE, CATEGORY_STATUS, ErrorCategory
from ai_stp_api.settings import (
    RATE_LIMIT_OVERALL_REQUESTS,
    AuthSettings,
    CatalogSettings,
    ServiceSettings,
    Settings,
)
from ai_stp_platform.settings import DatabaseSettings, StorageSettings

pytestmark = pytest.mark.platform

# An address that refuses fast, so dependency probes fail quickly and readiness
# reports them as not ready without any live service.
_UNREACHABLE = "127.0.0.1:59999"
_TEST_SECRET = "test-secret-key-at-least-32-bytes-long!!"
_TEST_CURSOR_SECRET = "test-catalog-cursor-secret-32b-min!!"


def _settings(
    log_dir: Path,
    *,
    rate_limit_overall_requests: int = 0,
    rate_limit_ip_requests: int = 0,
) -> Settings:
    return Settings(
        service=ServiceSettings(
            environment="test",
            log_dir=log_dir,
            rate_limit_overall_requests=rate_limit_overall_requests,
            rate_limit_ip_requests=rate_limit_ip_requests,
        ),
        database=DatabaseSettings(url=f"postgresql+asyncpg://u:p@{_UNREACHABLE}/db"),
        storage=StorageSettings(
            endpoint=f"http://{_UNREACHABLE}",
            bucket="test",
            access_key_id="test-access",
            secret_access_key="test-secret",
        ),
        auth=AuthSettings(secret_key=_TEST_SECRET, cookie_secure=False),
        catalog=CatalogSettings(cursor_signing_secret=_TEST_CURSOR_SECRET),
    )


@pytest_asyncio.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    app = create_app(_settings(tmp_path))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client


async def test_liveness_is_independent_of_dependencies(client: AsyncClient) -> None:
    response = await client.get("/v1/health/live")
    assert response.status_code == 200
    body = response.json()
    # Resource body (LivenessResponse), not CLI success envelope.
    assert body == {"schema_version": 1, "status": "alive"}
    assert response.headers["X-Request-Id"].startswith("request_")


async def test_version_reports_service_metadata(client: AsyncClient) -> None:
    response = await client.get("/v1/system/version")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == 1
    # The installed distribution, not a value this test chose. Injecting one
    # only proved the injection worked: production served `0.1.0` from
    # `AI_STP_API_VERSION` while the container underneath was `0.0.2`, and this
    # assertion was green throughout. The build is the only honest source.
    assert data["version"] == installed_version("ai-stp-api")
    assert data["environment"] == "test"
    # Safe diagnostics fields are always present; values may be null when unset
    # or when the database is unreachable (REQ-2411).
    assert "git_commit" in data
    assert "schema_revision" in data
    # No secret-bearing keys.
    for key in data:
        assert "secret" not in key.lower()
        assert "password" not in key.lower()
        assert "token" not in key.lower()


async def test_readiness_reports_missing_dependencies(client: AsyncClient) -> None:
    response = await client.get("/v1/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["schema_version"] == 1
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "fail"
    assert body["checks"]["object_storage"] == "fail"
    assert "checked_at" in body


async def test_rate_limit_rejects_repeated_route_before_handler(tmp_path: Path) -> None:
    limited_status = int(CATEGORY_STATUS[ErrorCategory.RATE_LIMITED])
    limited_code = CATEGORY_CODE[ErrorCategory.RATE_LIMITED]
    for _session in range(2):
        settings = _settings(tmp_path, rate_limit_overall_requests=1)
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as rate_client:
                first = await rate_client.get("/v1/health/live")
                limited = await rate_client.get("/v1/health/live")

        assert first.status_code == 200
        assert limited.status_code == limited_status
        assert limited.headers["Retry-After"] == str(
            settings.service.rate_limit_overall_window_seconds
        )
        assert limited.json()["error"]["code"] == limited_code


async def test_rate_limit_factory_isolates_transport_peers(tmp_path: Path) -> None:
    """Overall stays at the shipped default so a shared budget cannot explain the 429."""
    limited_status = int(CATEGORY_STATUS[ErrorCategory.RATE_LIMITED])
    limited_code = CATEGORY_CODE[ErrorCategory.RATE_LIMITED]
    settings = _settings(
        tmp_path,
        rate_limit_overall_requests=RATE_LIMIT_OVERALL_REQUESTS,
        rate_limit_ip_requests=1,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("10.0.0.1", 1)),
            base_url="http://test",
        ) as first_peer:
            admitted = await first_peer.get("/v1/health/live")
            limited = await first_peer.get("/v1/health/live")
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("10.0.0.2", 1)),
            base_url="http://test",
        ) as second_peer:
            other = await second_peer.get("/v1/health/live")

    assert admitted.status_code == 200
    assert limited.status_code == limited_status
    assert limited.json()["error"]["code"] == limited_code
    assert limited.headers["Retry-After"] == str(settings.service.rate_limit_ip_window_seconds)
    assert other.status_code == 200


async def test_rate_limit_factory_disables_overall_without_disabling_peer(tmp_path: Path) -> None:
    """The live IP probe sets overall=0 so only the peer window can explain a 429."""
    limited_status = int(CATEGORY_STATUS[ErrorCategory.RATE_LIMITED])
    limited_code = CATEGORY_CODE[ErrorCategory.RATE_LIMITED]
    settings = _settings(
        tmp_path,
        rate_limit_overall_requests=0,
        rate_limit_ip_requests=1,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("10.0.0.1", 1)),
            base_url="http://test",
        ) as first_peer:
            admitted = await first_peer.get("/v1/health/live")
            limited = await first_peer.get("/v1/health/live")
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("10.0.0.2", 1)),
            base_url="http://test",
        ) as second_peer:
            other = await second_peer.get("/v1/health/live")

    assert admitted.status_code == 200
    assert limited.status_code == limited_status
    assert limited.json()["error"]["code"] == limited_code
    assert limited.headers["Retry-After"] == str(settings.service.rate_limit_ip_window_seconds)
    assert other.status_code == 200
