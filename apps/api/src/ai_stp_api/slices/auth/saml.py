"""SAML 2.0 service provider: AuthnRequest, ACS validation, SP metadata (ADR-0226).

One IdP per deployment, provider name ``saml``. SP-initiated SSO only:
the AuthnRequest leaves over HTTP-Redirect and the response returns as a
form POST to ``/v1/auth/saml/acs``. Flow state rides in a
``saml_sso_request`` row keyed by a random RelayState token because the
IdP's cross-site POST carries no SameSite=Lax cookies.

Assertions are verified against configured IdP certificates only; a
certificate embedded in the response's own KeyInfo is never trusted.
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode, urlsplit
from xml.sax.saxutils import escape as xml_escape

import httpx
from cryptography.x509.verification import ExtensionPolicy
from lxml import etree
from signxml.verifier import SignatureConfiguration, XMLVerifier
from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.settings import AuthSettings
from ai_stp_api.slices.auth.domain import (
    ProviderProfile,
    normalize_display_name,
    normalize_email,
    normalize_subject,
)
from ai_stp_platform.models import SamlSsoRequest

# lxml's element class is literally named _Element; alias it once so the
# signatures below stay annotated without a per-site private-usage ignore.
XmlElement = etree._Element  # pyright: ignore[reportPrivateUsage]

NS_MD = "urn:oasis:names:tc:SAML:2.0:metadata"
NS_SAML = "urn:oasis:names:tc:SAML:2.0:assertion"
NS_SAMLP = "urn:oasis:names:tc:SAML:2.0:protocol"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"

BINDING_REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
BINDING_POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
STATUS_SUCCESS = "urn:oasis:names:tc:SAML:2.0:status:Success"
CONFIRMATION_BEARER = "urn:oasis:names:tc:SAML:2.0:cm:bearer"

REQUEST_TTL = timedelta(minutes=10)
CLOCK_SKEW = timedelta(minutes=5)
MAX_RESPONSE_BYTES = 1_048_576

_PEM_BLOCK = re.compile(rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.DOTALL)


def _xml_parser() -> etree.XMLParser:
    """Hardened parser for untrusted assertion and metadata documents."""
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        recover=False,
        huge_tree=False,
    )


class SamlError(ApiError):
    """ACS rejection carrying a log-safe machine reason, never assertion data."""

    def __init__(self, reason: str) -> None:
        super().__init__(ErrorCategory.AUTH_REQUIRED, "authentication failed")
        self.reason = reason


@dataclass(frozen=True)
class SamlIdp:
    """Resolved IdP configuration: entity id, SSO endpoint, signing certs."""

    entity_id: str
    sso_url: str
    certificates: tuple[bytes, ...]


def _pem_blocks(raw: bytes) -> list[bytes]:
    return [block + b"\n" for block in _PEM_BLOCK.findall(raw)]


def _certificate_pems(auth: AuthSettings) -> list[bytes]:
    value = auth.saml_idp_certificates.strip()
    if not value:
        return []
    raw = value.encode() if "BEGIN CERTIFICATE" in value else Path(value).read_bytes()
    return _pem_blocks(raw)


def _fetch_idp_metadata(url: str) -> SamlIdp:
    """Fetch and parse IdP EntityDescriptor (startup-time, fail-loud)."""
    response = httpx.get(url, timeout=10, follow_redirects=True)
    response.raise_for_status()
    return parse_idp_metadata(response.content)


def parse_idp_metadata(content: bytes) -> SamlIdp:
    """Parse an IdP EntityDescriptor into entity id, SSO URL and certs."""
    root = etree.fromstring(content, parser=_xml_parser())
    if root.tag != f"{{{NS_MD}}}EntityDescriptor":
        raise ValueError("saml metadata root is not EntityDescriptor")
    entity_id = (root.get("entityID") or "").strip()
    descriptor = root.find(f"{{{NS_MD}}}IDPSSODescriptor")
    if descriptor is None:
        raise ValueError("saml metadata has no IDPSSODescriptor")
    sso_url = ""
    for binding in (BINDING_REDIRECT, BINDING_POST):
        service = descriptor.find(f"{{{NS_MD}}}SingleSignOnService[@Binding='{binding}']")
        if service is not None and service.get("Location"):
            sso_url = service.get("Location", "").strip()
            break
    certificates = tuple(
        block + b"\n"
        for cert_text in descriptor.findall(
            f".//{{{NS_DS}}}KeyInfo/{{{NS_DS}}}X509Data/{{{NS_DS}}}X509Certificate"
        )
        if cert_text.text
        for block in _pem_blocks(
            b"-----BEGIN CERTIFICATE-----\n"
            + cert_text.text.strip().encode()
            + b"\n-----END CERTIFICATE-----"
        )
    )
    if not (entity_id and sso_url and certificates):
        raise ValueError("saml metadata lacks entityID, SSO service or certificates")
    return SamlIdp(entity_id=entity_id, sso_url=sso_url, certificates=certificates)


def load_saml_idp(auth: AuthSettings) -> SamlIdp | None:
    """Resolve the configured IdP once at startup; None when disabled.

    Explicit settings win over metadata values; the metadata URL only fills
    what the operator did not set. A configured but unresolvable IdP raises —
    a half-configured SSO surface must not boot.
    """
    if not auth.provider_enabled("saml"):
        return None
    metadata = (
        _fetch_idp_metadata(auth.saml_idp_metadata_url) if auth.saml_idp_metadata_url else None
    )
    entity_id = auth.saml_idp_entity_id.strip() or (metadata.entity_id if metadata else "")
    sso_url = auth.saml_idp_sso_url or (metadata.sso_url if metadata else "")
    certificates = _certificate_pems(auth) or list(metadata.certificates if metadata else [])
    if not (entity_id and sso_url and certificates):
        raise ValueError("incomplete SAML IdP configuration")
    return SamlIdp(entity_id=entity_id, sso_url=sso_url, certificates=tuple(certificates))


def new_sso_request(
    *,
    flow: str,
    client: str,
    return_to: str | None,
    link_account_id: str | None,
    device_id: str | None,
    now: datetime | None = None,
) -> SamlSsoRequest:
    """One pending SP-initiated request; RelayState stays under 80 bytes."""
    moment = now or datetime.now(UTC)
    return SamlSsoRequest(
        id=f"_{secrets.token_urlsafe(24)}",
        relay_state=secrets.token_urlsafe(24),
        flow=flow,
        client=client,
        return_to=return_to,
        link_account_id=link_account_id,
        device_id=device_id,
        expires_at=moment + REQUEST_TTL,
    )


async def purge_expired_requests(db: AsyncSession, *, now: datetime | None = None) -> None:
    """Drop stale pending requests; called opportunistically at login start."""
    await db.execute(
        delete(SamlSsoRequest).where(SamlSsoRequest.expires_at < (now or datetime.now(UTC)))
    )


def build_sso_redirect(
    idp: SamlIdp, *, request_id: str, relay_state: str, auth: AuthSettings
) -> str:
    """HTTP-Redirect binding: DEFLATE+base64 AuthnRequest onto the SSO URL."""
    issue_instant = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    acs_url = auth.saml_acs_url()
    request_xml = (
        f'<samlp:AuthnRequest xmlns:samlp="{NS_SAMLP}" xmlns:saml="{NS_SAML}" '
        f'ID="{xml_escape(request_id)}" Version="2.0" '
        f'IssueInstant="{issue_instant}" Destination="{xml_escape(idp.sso_url)}" '
        f'AssertionConsumerServiceURL="{xml_escape(acs_url)}" '
        f'ProtocolBinding="{BINDING_POST}">'
        f"<saml:Issuer>{xml_escape(auth.saml_sp_entity_id_resolved())}</saml:Issuer>"
        "<samlp:NameIDPolicy "
        'Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified" '
        'AllowCreate="true"/></samlp:AuthnRequest>'
    )
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    deflated = compressor.compress(request_xml.encode()) + compressor.flush()
    query = urlencode(
        {
            "SAMLRequest": base64.b64encode(deflated).decode(),
            "RelayState": relay_state,
        }
    )
    return f"{idp.sso_url}?{query}"


def sp_metadata_xml(auth: AuthSettings) -> str:
    """SP EntityDescriptor for IdP-side registration."""
    return (
        f'<md:EntityDescriptor xmlns:md="{NS_MD}" '
        f'entityID="{xml_escape(auth.saml_sp_entity_id_resolved())}">'
        f'<md:SPSSODescriptor protocolSupportEnumeration="{NS_SAMLP}" '
        'AuthnRequestsSigned="false">'
        "<md:NameIDFormat>"
        "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
        "</md:NameIDFormat>"
        f'<md:AssertionConsumerService Binding="{BINDING_POST}" '
        f'Location="{xml_escape(auth.saml_acs_url())}" index="0" isDefault="true"/>'
        "</md:SPSSODescriptor></md:EntityDescriptor>"
    )


def _instant(value: str | None) -> datetime | None:
    if value is None:
        return None
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _signed_covering(response_el: XmlElement, assertion_el: XmlElement, idp: SamlIdp) -> bool:
    """True when a configured cert signs the Response or the Assertion.

    Three defenses, all needed ("see what is signed" / signature wrapping):
    the signature must sit at one of the two legal positions, its Reference
    must name the expected element's ID, and that ID must be unique in the
    document — a grafted same-ID node would otherwise resolve the reference
    to attacker-controlled content.
    """
    verifier = XMLVerifier()
    for location, expected in (
        ("./", response_el),
        (f"./{{{NS_SAML}}}Assertion/", assertion_el),
    ):
        expected_id = expected.get("ID")
        signature = expected.find(f"{{{NS_DS}}}Signature")
        if expected_id is None or signature is None:
            continue
        reference = signature.find(f"./{{{NS_DS}}}SignedInfo/{{{NS_DS}}}Reference")
        if reference is None or reference.get("URI") != f"#{expected_id}":
            continue
        if sum(1 for el in response_el.iter() if el.get("ID") == expected_id) != 1:
            continue
        config = SignatureConfiguration(location=location, expect_references=1)
        for certificate in idp.certificates:
            try:
                verifier.verify(  # pyright: ignore[reportUnknownMemberType]
                    response_el,
                    x509_cert=certificate.decode(),
                    id_attribute="ID",
                    # Trust is pinned to the configured cert itself; corporate
                    # IdP signing certs regularly carry no KeyUsage extension.
                    ee_policy=ExtensionPolicy.permit_all(),
                    expect_config=config,
                )
            except Exception:
                continue
            return True
    return False


def _required_text(element: XmlElement | None) -> str:
    if element is None or not (element.text or "").strip():
        raise SamlError("assertion_missing_field")
    return (element.text or "").strip()


def _qualified_subject(entity_id: str, nameid: str) -> str:
    """IdP-qualified subject within the 255-char provider_subject column."""
    qualifier = urlsplit(entity_id).hostname or hashlib.sha256(entity_id.encode()).hexdigest()[:16]
    subject = f"{qualifier}:{nameid}"
    if len(subject) > 255:
        subject = f"{qualifier}:{hashlib.sha256(nameid.encode()).hexdigest()}"
    return subject


def _attribute_values(assertion: XmlElement, names: tuple[str, ...]) -> str | None:
    wanted = {name.lower() for name in names}
    for attribute in assertion.iter(f"{{{NS_SAML}}}Attribute"):
        if (attribute.get("Name") or "").lower() not in wanted:
            continue
        value = attribute.find(f"{{{NS_SAML}}}AttributeValue")
        if value is not None and (value.text or "").strip():
            return (value.text or "").strip()
    return None


def validate_response(
    saml_response_b64: str,
    *,
    idp: SamlIdp,
    auth: AuthSettings,
    expected_request_id: str,
    now: datetime | None = None,
) -> tuple[ProviderProfile, str]:
    """Validate a base64 SAMLResponse into a ProviderProfile + assertion id.

    Raises SamlError on any failed check; every rejection is a uniform
    "authentication failed" to the caller, with the reason kept for logs.
    """
    moment = now or datetime.now(UTC)
    try:
        raw = base64.b64decode(saml_response_b64.strip(), validate=True)
    except ValueError as exc:
        raise SamlError("response_not_base64") from exc
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise SamlError("response_size")
    try:
        root = etree.fromstring(raw, parser=_xml_parser())
    except etree.XMLSyntaxError as exc:
        raise SamlError("response_not_xml") from exc
    if root.tag != f"{{{NS_SAMLP}}}Response":
        raise SamlError("response_wrong_root")

    status_code = root.find(f"./{{{NS_SAMLP}}}Status/{{{NS_SAMLP}}}StatusCode")
    if status_code is None or status_code.get("Value") != STATUS_SUCCESS:
        raise SamlError("status_not_success")

    assertions = root.findall(f"{{{NS_SAML}}}Assertion")
    if len(assertions) != 1:
        # Zero assertions carries no identity; more than one is the classic
        # signature-wrapping shape — neither is negotiated.
        raise SamlError("assertion_count")
    assertion = assertions[0]
    if not _signed_covering(root, assertion, idp):
        raise SamlError("signature_invalid")

    issuer = _required_text(assertion.find(f"{{{NS_SAML}}}Issuer"))
    if issuer != idp.entity_id:
        raise SamlError("issuer_mismatch")

    conditions = assertion.find(f"{{{NS_SAML}}}Conditions")
    if conditions is not None:
        not_before = _instant(conditions.get("NotBefore"))
        not_on_or_after = _instant(conditions.get("NotOnOrAfter"))
        if not_before is not None and moment < not_before - CLOCK_SKEW:
            raise SamlError("assertion_not_yet_valid")
        if not_on_or_after is not None and moment >= not_on_or_after + CLOCK_SKEW:
            raise SamlError("assertion_expired")
        audiences = [
            (node.text or "").strip() for node in conditions.iter(f"{{{NS_SAML}}}Audience")
        ]
        if auth.saml_sp_entity_id_resolved() not in audiences:
            raise SamlError("audience_mismatch")
    else:
        raise SamlError("conditions_missing")

    subject = assertion.find(f"{{{NS_SAML}}}Subject")
    if subject is None:
        raise SamlError("subject_missing")
    confirmations = subject.findall(f"{{{NS_SAML}}}SubjectConfirmation")
    bearer_data = None
    for confirmation in confirmations:
        if confirmation.get("Method") == CONFIRMATION_BEARER:
            bearer_data = confirmation.find(f"{{{NS_SAML}}}SubjectConfirmationData")
            break
    if bearer_data is None:
        raise SamlError("subject_confirmation_missing")
    if bearer_data.get("InResponseTo") != expected_request_id:
        raise SamlError("in_response_to_mismatch")
    if bearer_data.get("Recipient") != auth.saml_acs_url():
        raise SamlError("recipient_mismatch")
    confirmation_expiry = _instant(bearer_data.get("NotOnOrAfter"))
    if confirmation_expiry is not None and moment >= confirmation_expiry + CLOCK_SKEW:
        raise SamlError("confirmation_expired")

    nameid = _required_text(subject.find(f"{{{NS_SAML}}}NameID"))
    email = _attribute_values(assertion, auth.saml_attribute_names("email"))
    if email is None or "@" not in email:
        raise SamlError("email_attribute_missing")

    assertion_id = assertion.get("ID") or root.get("ID") or ""
    profile = ProviderProfile(
        provider="saml",
        subject=normalize_subject(_qualified_subject(idp.entity_id, nameid)),
        email=normalize_email(email),
        # The corporate IdP's signed assertion is the verification source; the
        # attribute exists only because the IdP asserted it (ADR-0226).
        email_verified=True,
        avatar_url=None,
        display_name=normalize_display_name(
            _attribute_values(assertion, auth.saml_attribute_names("display_name"))
        ),
        username=None,
    )
    return profile, assertion_id


async def consume_sso_request(
    db: AsyncSession,
    *,
    relay_state: str,
    now: datetime | None = None,
) -> SamlSsoRequest:
    """Fetch the pending request a RelayState names; rejects stale/consumed."""
    row = await db.scalar(select(SamlSsoRequest).where(SamlSsoRequest.relay_state == relay_state))
    moment = now or datetime.now(UTC)
    if row is None:
        raise SamlError("relay_state_unknown")
    if row.expires_at <= moment:
        raise SamlError("request_expired")
    if row.assertion_id is not None:
        raise SamlError("request_consumed")
    return row


async def mark_consumed(db: AsyncSession, *, request_id: str, assertion_id: str) -> None:
    """Bind the assertion id to the request exactly once (replay guard)."""
    result = cast(
        CursorResult[Any],
        await db.execute(
            update(SamlSsoRequest)
            .where(SamlSsoRequest.id == request_id, SamlSsoRequest.assertion_id.is_(None))
            .values(assertion_id=assertion_id)
        ),
    )
    if result.rowcount != 1:
        raise SamlError("request_consumed")
