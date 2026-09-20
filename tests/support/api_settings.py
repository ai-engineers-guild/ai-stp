"""Shared `Settings` builders for tests that serve the real ASGI app.

Extracted from `tests/api/platform/conftest.py` so the CLI↔API boundary tests
compose the same app instead of a second opinion about its settings.
"""

from __future__ import annotations

from pathlib import Path

from ai_stp_api.settings import (
    AuthSettings,
    CatalogSettings,
    ContentSettings,
    CorporateSettings,
    ServiceSettings,
    Settings,
)
from ai_stp_platform.settings import DatabaseSettings, StorageSettings

TEST_SECRET = "test-secret-key-at-least-32-bytes-long!!"
TEST_CURSOR_SECRET = "test-catalog-cursor-secret-32b-min!!"
UNREACHABLE = "127.0.0.1:59999"


def make_test_auth(**overrides: object) -> AuthSettings:
    """Build AuthSettings with safe test defaults."""
    values: dict[str, object] = {
        "secret_key": TEST_SECRET,
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
    content: ContentSettings | None = None,
) -> Settings:
    """Compose Settings for ASGI tests."""
    url = database_url or f"postgresql+asyncpg://u:p@{UNREACHABLE}/db"
    return Settings(
        service=ServiceSettings(
            environment="test",
            log_dir=log_dir,
            # Tests that are not about the HTTP gate must not share the
            # process-wide 100/min budget (`ADR-0128`). Explicit 0 disables
            # that dimension; the fail-closed defaults are proven elsewhere.
            rate_limit_overall_requests=0,
            rate_limit_ip_requests=0,
        ),
        database=DatabaseSettings(url=url),
        storage=StorageSettings(
            endpoint=f"http://{UNREACHABLE}",
            bucket="test",
            access_key_id="test-access",
            secret_access_key="test-secret",
        ),
        auth=auth or make_test_auth(),
        catalog=catalog
        or CatalogSettings(cursor_signing_secret=TEST_CURSOR_SECRET, usage_enabled=False),
        content=content or ContentSettings(),
        corporate=CorporateSettings(bootstrap_secret="corporate-bootstrap-test-secret"),
    )
