# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportPrivateUsage=false, reportMissingTypeStubs=false
"""SAML login/ACS route tests against a real migrated database.

The IdP is simulated by signing deterministic response fixtures with a
throwaway key pair — same shape as the local OIDC lab, but hermetic.
"""

from __future__ import annotations

import base64
import zlib
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
import pytest_asyncio
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from lxml import etree
from signxml.signer import XMLSigner
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.support.api_settings import make_test_auth

from ai_stp_api.app import create_app
from ai_stp_api.settings import AuthSettings, Settings
from ai_stp_api.slices.auth import saml
from ai_stp_api.slices.auth.saml import NS_SAML, NS_SAMLP
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import AuditEvent, OAuthIdentity, SamlSsoRequest
from ai_stp_platform.organization_models import Organization

pytestmark = pytest.mark.platform

_IDP_ENTITY = "https://idp.corp.example/saml"
_IDP_SSO = "https://idp.corp.example/sso"


def _keypair() -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp.corp.example")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return key_pem, cert.public_bytes(serialization.Encoding.PEM)


_KEY_PEM, _CERT_PEM = _keypair()


def _saml_auth(**overrides: object) -> AuthSettings:
    values: dict[str, object] = {
        "saml_idp_entity_id": _IDP_ENTITY,
        "saml_idp_sso_url": _IDP_SSO,
        "saml_idp_certificates": _CERT_PEM.decode(),
    }
    values.update(overrides)
    return make_test_auth(**values)


@pytest_asyncio.fixture
async def saml_client(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    settings = settings_factory(database_url=migrated_database_url, auth=_saml_auth())
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


def _request_id_from(location: str) -> tuple[str, str]:
    """Inflate the AuthnRequest out of the redirect; return (id, relay)."""
    query = parse_qs(urlsplit(location).query)
    inflated = zlib.decompress(base64.b64decode(query["SAMLRequest"][0]), wbits=-15).decode()
    request_id = inflated.split('ID="', 1)[1].split('"', 1)[0]
    return request_id, query["RelayState"][0]


def _response_b64(
    *, request_id: str, email: str = "ada@corp.example", nameid: str = "uid-42"
) -> str:
    now = datetime.now(UTC)
    acs = "http://test/v1/auth/saml/acs"
    audience = "http://test/v1/auth/saml/metadata"
    root = etree.fromstring(
        f"""<samlp:Response xmlns:samlp="{NS_SAMLP}" xmlns:saml="{NS_SAML}"
ID="_resp-1" Version="2.0" IssueInstant="{now:%Y-%m-%dT%H:%M:%SZ}" Destination="{acs}">
<samlp:Status><samlp:StatusCode Value="{saml.STATUS_SUCCESS}"/></samlp:Status>
<saml:Assertion ID="_assert-{nameid}" Version="2.0" IssueInstant="{now:%Y-%m-%dT%H:%M:%SZ}">
<saml:Issuer>{_IDP_ENTITY}</saml:Issuer>
<saml:Subject><saml:NameID>{nameid}</saml:NameID>
<saml:SubjectConfirmation Method="{saml.CONFIRMATION_BEARER}">
<saml:SubjectConfirmationData InResponseTo="{request_id}" Recipient="{acs}"
NotOnOrAfter="{(now + timedelta(minutes=5)):%Y-%m-%dT%H:%M:%SZ}"/>
</saml:SubjectConfirmation></saml:Subject>
<saml:Conditions NotBefore="{(now - timedelta(minutes=1)):%Y-%m-%dT%H:%M:%SZ}"
NotOnOrAfter="{(now + timedelta(minutes=5)):%Y-%m-%dT%H:%M:%SZ}">
<saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>
</saml:Conditions>
<saml:AttributeStatement>
<saml:Attribute Name="email"><saml:AttributeValue>{email}</saml:AttributeValue></saml:Attribute>
</saml:AttributeStatement>
</saml:Assertion></samlp:Response>""".encode()
    )
    assertion = root.find(f"{{{NS_SAML}}}Assertion")
    assert assertion is not None
    signed = XMLSigner().sign(assertion, key=_KEY_PEM, cert=_CERT_PEM.decode())
    position = list(root).index(assertion)
    root.remove(assertion)
    root.insert(position, signed)
    return base64.b64encode(etree.tostring(root)).decode()


async def test_saml_login_redirects_to_idp(
    saml_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = saml_client
    response = await client.get(
        "/v1/auth/saml/login",
        params={"return_to": "/en/account"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith(_IDP_SSO)
    request_id, relay = _request_id_from(location)
    assert request_id.startswith("_")
    async with app.state.sessionmaker() as db:
        row = await db.scalar(select(SamlSsoRequest).where(SamlSsoRequest.id == request_id))
        assert row is not None
        assert row.relay_state == relay
        assert row.return_to == "/en/account"


async def test_saml_metadata_serves_entity_descriptor(
    saml_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, _ = saml_client
    response = await client.get("/v1/auth/saml/metadata")
    assert response.status_code == 200
    assert 'entityID="http://test/v1/auth/saml/metadata"' in response.text
    assert 'Location="http://test/v1/auth/saml/acs"' in response.text


async def test_saml_acs_issues_session(
    saml_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = saml_client
    started = await client.get("/v1/auth/saml/login", follow_redirects=False)
    request_id, relay = _request_id_from(started.headers["location"])

    response = await client.post(
        "/v1/auth/saml/acs",
        data={"SAMLResponse": _response_b64(request_id=request_id), "RelayState": relay},
        follow_redirects=False,
    )
    assert response.status_code == 303
    # A first sign-in lands on legal onboarding like every other provider.
    assert "/onboarding" in response.headers["location"]
    assert "status=error" not in response.headers["location"]
    cookie_blob = " ".join(
        value for name, value in response.headers.multi_items() if name.lower() == "set-cookie"
    )
    assert "ai_stp_session" in cookie_blob
    async with app.state.sessionmaker() as db:
        identity = await db.scalar(select(OAuthIdentity).where(OAuthIdentity.provider == "saml"))
        assert identity is not None
        assert identity.provider_subject == "idp.corp.example:uid-42"
        assert identity.email == "ada@corp.example"
        row = await db.scalar(select(SamlSsoRequest).where(SamlSsoRequest.id == request_id))
        assert row is not None
        assert row.assertion_id == "_assert-uid-42"
        audit = (
            await db.scalars(select(AuditEvent).where(AuditEvent.action == "auth.saml_login"))
        ).all()
        assert len(audit) == 1
        assert audit[0].outcome == "succeeded"
        # The audit row names the provider, never assertion or cert material.
        assert audit[0].payload == {"provider": "saml", "flow": "login"}


async def test_saml_acs_rejects_replay(
    saml_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, app = saml_client
    started = await client.get("/v1/auth/saml/login", follow_redirects=False)
    request_id, relay = _request_id_from(started.headers["location"])
    body = {
        "SAMLResponse": _response_b64(request_id=request_id),
        "RelayState": relay,
    }
    first = await client.post("/v1/auth/saml/acs", data=body, follow_redirects=False)
    assert first.status_code == 303
    assert "status=error" not in first.headers["location"]
    replayed = await client.post("/v1/auth/saml/acs", data=body, follow_redirects=False)
    assert replayed.status_code == 303
    assert "status=error" in replayed.headers["location"]
    async with app.state.sessionmaker() as db:
        failures = (
            await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "auth.saml_login",
                    AuditEvent.outcome == "failed",
                    AuditEvent.reason == "request_consumed",
                )
            )
        ).all()
        assert len(failures) == 1


async def test_saml_acs_rejects_unknown_relay_state(
    saml_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, _ = saml_client
    response = await client.post(
        "/v1/auth/saml/acs",
        data={"SAMLResponse": "AAAA", "RelayState": "forged"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "status=error" in response.headers["location"]


async def test_saml_login_disabled_is_dependency_error(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    settings = settings_factory(
        database_url=migrated_database_url,
        auth=_saml_auth(disabled_providers="saml"),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/v1/auth/saml/login", follow_redirects=False)
            assert response.status_code in {400, 503}
            denied = await client.post(
                "/v1/auth/saml/acs",
                data={"SAMLResponse": "AAAA", "RelayState": "x"},
                follow_redirects=False,
            )
            assert denied.status_code in {400, 503}


async def test_saml_org_restriction(
    migrated_database_url: str,
    settings_factory: Callable[..., Settings],
) -> None:
    """With saml_organization_id, only the org's domains or provisions sign in."""
    engine = create_async_engine(migrated_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        organization = Organization(
            id=new_id("organization"),
            kind="corporate",
            display_name="Corp",
            allowed_email_domains=["corp.example"],
        )
        db.add(organization)
        await db.commit()
        org_id = organization.id
    await engine.dispose()

    settings = settings_factory(
        database_url=migrated_database_url,
        auth=_saml_auth(saml_organization_id=org_id),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # In-domain email passes the gate.
            started = await client.get("/v1/auth/saml/login", follow_redirects=False)
            request_id, relay = _request_id_from(started.headers["location"])
            ok = await client.post(
                "/v1/auth/saml/acs",
                data={
                    "SAMLResponse": _response_b64(request_id=request_id),
                    "RelayState": relay,
                },
                follow_redirects=False,
            )
            assert "status=error" not in ok.headers["location"]

            # Off-domain email is rejected before any account is created.
            started = await client.get("/v1/auth/saml/login", follow_redirects=False)
            request_id, relay = _request_id_from(started.headers["location"])
            denied = await client.post(
                "/v1/auth/saml/acs",
                data={
                    "SAMLResponse": _response_b64(
                        request_id=request_id,
                        email="eve@elsewhere.example",
                        nameid="uid-9",
                    ),
                    "RelayState": relay,
                },
                follow_redirects=False,
            )
            assert "status=error" in denied.headers["location"]
            async with app.state.sessionmaker() as db:
                assert (
                    await db.scalar(
                        select(OAuthIdentity).where(OAuthIdentity.email == "eve@elsewhere.example")
                    )
                ) is None


async def test_saml_idp_only_suppresses_other_providers() -> None:
    auth = _saml_auth(saml_idp_only=True)
    assert auth.provider_enabled("saml")
    assert not auth.provider_enabled("google")
    assert not auth.provider_enabled("github")
    assert not auth.provider_enabled("gitlab")


async def test_saml_idp_only_requires_configured_idp() -> None:
    with pytest.raises(ValueError, match="saml_idp_only"):
        _saml_auth(
            saml_idp_only=True,
            saml_idp_sso_url="",
            saml_idp_certificates="",
        )
