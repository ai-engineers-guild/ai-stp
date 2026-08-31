"""The published `$id` URL serves the generated provider-info schema bytes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import pytest
from httpx import ASGITransport, AsyncClient

from ai_stp_api.app import create_app
from ai_stp_api.settings import AuthSettings, CatalogSettings, ServiceSettings, Settings
from ai_stp_platform.settings import DatabaseSettings, StorageSettings

KIT_SCHEMAS = (
    *sorted(Path("provider-kit/v3").glob("*-response.schema.json")),
    Path("provider-kit/v3/provider-info.schema.json"),
)
_UNREACHABLE = "127.0.0.1:59999"
_TEST_SECRET = "test-secret-key-at-least-32-bytes-long!!"
_TEST_CURSOR_SECRET = "test-catalog-cursor-secret-32b-min!!"


def _settings(log_dir: Path) -> Settings:
    return Settings(
        service=ServiceSettings(
            environment="test",
            log_dir=log_dir,
            rate_limit_overall_requests=0,
            rate_limit_ip_requests=0,
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


@pytest.mark.parametrize("kit_schema", KIT_SCHEMAS, ids=lambda path: path.name)
async def test_provider_schema_id_serves_the_exact_kit_bytes(
    tmp_path: Path, kit_schema: Path
) -> None:
    """A validator that follows `$id` must receive the kit file, not a 404.

    The identifier is still an identifier. Serving it is what stops an external
    tool from treating the published claim as a dead link.
    """
    document = cast(dict[str, object], json.loads(kit_schema.read_text(encoding="utf-8")))
    schema_id = document.get("$id")
    assert isinstance(schema_id, str)
    published_path = urlsplit(schema_id).path
    app = create_app(_settings(tmp_path))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(published_path)
    assert response.status_code == 200
    assert response.content == kit_schema.read_bytes()
    assert "schema+json" in response.headers["content-type"]
