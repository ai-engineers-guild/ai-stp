"""Public discovery uses deployment sign-in policy and never exposes IdP secrets."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tests.support.api_settings import make_test_auth

from ai_stp_api.deps import get_auth_settings
from ai_stp_api.slices.auth.router import router

pytestmark = pytest.mark.platform


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, ["google", "github"]),
        ({"disabled_providers": "google,github"}, []),
        ({"google_client_secret": "", "github_client_id": ""}, []),
        (
            {
                "authentik_issuer_url": "https://idp.example.test",
                "authentik_client_id": "test-client",
                "authentik_client_secret": "private-test-value",
                "keycloak_issuer_url": "https://keycloak.example.test",
                "keycloak_client_id": "test-client",
            },
            ["google", "github", "authentik"],
        ),
        (
            {
                "saml_idp_sso_url": "https://idp.example.test/sso",
                "saml_idp_certificates": "private-test-certificate",
                "saml_idp_only": True,
            },
            ["saml"],
        ),
    ],
)
async def test_public_provider_discovery(overrides: dict[str, object], expected: list[str]) -> None:
    auth = make_test_auth(**overrides)
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_auth_settings] = lambda: auth
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://api.test") as client:
        response = await client.get("/v1/auth/providers")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"schema_version": 1, "providers": expected}
