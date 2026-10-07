# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportPrivateUsage=false, reportMissingTypeStubs=false
"""SAML service-provider machinery: deterministic signed fixtures, no IdP.

A throwaway RSA key pair is generated per module and the fixtures are
signed with signxml — the same library the verifier uses — so the tests
exercise real XML-DSig verification, not a mocked "valid" flag.
"""

from __future__ import annotations

import base64
import zlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml.signer import XMLSigner

from ai_stp_api.settings import AuthSettings
from ai_stp_api.slices.auth import saml
from ai_stp_api.slices.auth.domain import ProviderProfile
from ai_stp_api.slices.auth.saml import (
    NS_SAML,
    NS_SAMLP,
    SamlError,
    SamlIdp,
)

_IDP_ENTITY = "https://idp.corp.example/saml"
_IDP_SSO = "https://idp.corp.example/sso"
_SP_ENTITY = "http://test/v1/auth/saml/metadata"
_ACS = "http://test/v1/auth/saml/acs"
_REQUEST_ID = "_req-test-1"


def _keypair() -> tuple[rsa.RSAPrivateKey, bytes, bytes]:
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
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return key, key_pem, cert_pem


_KEY, _KEY_PEM, _CERT_PEM = _keypair()
_IDP = SamlIdp(entity_id=_IDP_ENTITY, sso_url=_IDP_SSO, certificates=(_CERT_PEM,))


def _auth(**overrides: object) -> AuthSettings:
    values: dict[str, object] = {
        "secret_key": "saml-test-secret-key-32-bytes-long!",
        "cookie_secure": False,
        "public_base_url": "http://test",
        "saml_idp_entity_id": _IDP_ENTITY,
        "saml_idp_sso_url": _IDP_SSO,
        "saml_idp_certificates": _CERT_PEM.decode(),
    }
    values.update(overrides)
    return AuthSettings(**values)  # type: ignore[arg-type]


def _response_xml(
    *,
    nameid: str = "uid-42",
    email: str = "ada@corp.example",
    display_name: str = "Ada",
    issuer: str = _IDP_ENTITY,
    audience: str = _SP_ENTITY,
    recipient: str = _ACS,
    in_response_to: str | None = _REQUEST_ID,
    not_before: datetime | None = None,
    not_on_or_after: datetime | None = None,
    status: str = saml.STATUS_SUCCESS,
) -> etree._Element:
    now = datetime.now(UTC)
    root = etree.fromstring(
        f"""<samlp:Response xmlns:samlp="{NS_SAMLP}" xmlns:saml="{NS_SAML}"
ID="_resp-1" Version="2.0" IssueInstant="{now:%Y-%m-%dT%H:%M:%SZ}" Destination="{_ACS}">
<samlp:Status><samlp:StatusCode Value="{status}"/></samlp:Status>
<saml:Assertion ID="_assert-1" Version="2.0" IssueInstant="{now:%Y-%m-%dT%H:%M:%SZ}">
<saml:Issuer>{issuer}</saml:Issuer>
<saml:Subject><saml:NameID>{nameid}</saml:NameID>
<saml:SubjectConfirmation Method="{saml.CONFIRMATION_BEARER}">
<saml:SubjectConfirmationData
{"InResponseTo=" + '"' + in_response_to + '"' if in_response_to else ""}
Recipient="{recipient}" NotOnOrAfter="{(now + timedelta(minutes=5)):%Y-%m-%dT%H:%M:%SZ}"/>
</saml:SubjectConfirmation></saml:Subject>
<saml:Conditions NotBefore="{(not_before or now - timedelta(minutes=1)):%Y-%m-%dT%H:%M:%SZ}"
NotOnOrAfter="{(not_on_or_after or now + timedelta(minutes=5)):%Y-%m-%dT%H:%M:%SZ}">
<saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>
</saml:Conditions>
<saml:AttributeStatement>
<saml:Attribute Name="email"><saml:AttributeValue>{email}</saml:AttributeValue></saml:Attribute>
<saml:Attribute Name="displayName"><saml:AttributeValue>{display_name}</saml:AttributeValue>
</saml:Attribute>
</saml:AttributeStatement>
</saml:Assertion></samlp:Response>""".encode()
    )
    return root


def _sign_in_place(element: etree._Element) -> etree._Element:
    """Envelop a signature into ``element`` — XMLSigner.sign returns a new
    tree, so the unsigned element is swapped for the signed copy."""
    signed = XMLSigner().sign(element, key=_KEY_PEM, cert=_CERT_PEM.decode())
    parent = element.getparent()
    if parent is None:
        return signed
    position = list(parent).index(element)
    parent.remove(element)
    parent.insert(position, signed)
    return signed


def _signed_response_b64(xml_root: etree._Element, *, sign_assertion: bool = True) -> str:
    if sign_assertion:
        assertion = xml_root.find(f"{{{NS_SAML}}}Assertion")
        assert assertion is not None
        _sign_in_place(assertion)
        root = xml_root
    else:
        root = _sign_in_place(xml_root)
    return base64.b64encode(etree.tostring(root)).decode()


def _validate(
    b64: str, *, auth: AuthSettings | None = None, idp: SamlIdp = _IDP
) -> tuple[ProviderProfile, str]:
    return saml.validate_response(
        b64,
        idp=idp,
        auth=auth or _auth(),
        expected_request_id=_REQUEST_ID,
    )


def test_validate_response_happy_path() -> None:
    profile, assertion_id = _validate(_signed_response_b64(_response_xml()))
    assert assertion_id == "_assert-1"
    assert profile.provider == "saml"
    assert profile.subject == "idp.corp.example:uid-42"
    assert profile.email == "ada@corp.example"
    assert profile.email_verified is True
    assert profile.display_name == "Ada"


def test_validate_response_signed_at_response_level() -> None:
    profile, _ = _validate(_signed_response_b64(_response_xml(), sign_assertion=False))
    assert profile.email == "ada@corp.example"


def test_validate_response_rejects_wrong_cert() -> None:
    _, _, foreign_cert = _keypair()
    foreign_idp = SamlIdp(entity_id=_IDP_ENTITY, sso_url=_IDP_SSO, certificates=(foreign_cert,))
    with pytest.raises(SamlError):
        _validate(_signed_response_b64(_response_xml()), idp=foreign_idp)


def test_validate_response_rejects_tampered_attribute() -> None:
    root = _response_xml()
    assertion = root.find(f"{{{NS_SAML}}}Assertion")
    assert assertion is not None
    _sign_in_place(assertion)
    for value in root.iter(f"{{{NS_SAML}}}AttributeValue"):
        if value.text == "ada@corp.example":
            value.text = "mallory@corp.example"
    with pytest.raises(SamlError):
        _validate(base64.b64encode(etree.tostring(root)).decode())


def test_validate_response_rejects_expired_assertion() -> None:
    root = _response_xml(not_on_or_after=datetime.now(UTC) - timedelta(minutes=10))
    with pytest.raises(SamlError):
        _validate(_signed_response_b64(root))


def test_validate_response_rejects_wrong_audience() -> None:
    root = _response_xml(audience="https://somebody-else.example/sp")
    with pytest.raises(SamlError):
        _validate(_signed_response_b64(root))


def test_validate_response_rejects_wrong_request_id() -> None:
    root = _response_xml(in_response_to="_other-request")
    with pytest.raises(SamlError):
        _validate(_signed_response_b64(root))


def test_validate_response_rejects_unsolicited_response() -> None:
    root = _response_xml(in_response_to=None)
    with pytest.raises(SamlError):
        _validate(_signed_response_b64(root))


def test_validate_response_rejects_wrong_recipient() -> None:
    root = _response_xml(recipient="https://evil.example/acs")
    with pytest.raises(SamlError):
        _validate(_signed_response_b64(root))


def test_validate_response_rejects_wrong_issuer() -> None:
    root = _response_xml(issuer="https://other-idp.example/entity")
    with pytest.raises(SamlError):
        _validate(_signed_response_b64(root))


def test_validate_response_rejects_double_assertion() -> None:
    root = _response_xml()
    first = root.find(f"{{{NS_SAML}}}Assertion")
    assert first is not None
    clone = etree.fromstring(etree.tostring(first))
    root.append(clone)
    with pytest.raises(SamlError):
        _validate(_signed_response_b64(root))


def test_validate_response_rejects_signature_covering_unrelated_node() -> None:
    """A valid signature that signs something else must not satisfy us."""
    root = _response_xml()
    carrier = etree.SubElement(root, "Carrier")
    carrier.set("ID", "_evil-carrier")
    carrier.text = "attacker-controlled payload"
    signed_carrier = XMLSigner().sign(carrier, key=_KEY_PEM, cert=_CERT_PEM.decode())
    signature = signed_carrier.find(f"{{{saml.NS_DS}}}Signature")
    assert signature is not None
    # Graft the signature at the legal Response-level position; its Reference
    # still resolves to Carrier, not to Response or Assertion.
    root.append(signature)
    with pytest.raises(SamlError):
        _validate(base64.b64encode(etree.tostring(root)).decode())


def test_validate_response_rejects_failure_status() -> None:
    root = _response_xml(status="urn:oasis:names:tc:SAML:2.0:status:Requester")
    with pytest.raises(SamlError):
        _validate(_signed_response_b64(root))


def test_validate_response_rejects_garbage() -> None:
    with pytest.raises(SamlError):
        _validate("!!!not-base64!!!")
    with pytest.raises(SamlError):
        _validate(base64.b64encode(b"<not-xml").decode())


def test_validate_response_requires_email() -> None:
    root = _response_xml()
    for attr in list(root.iter(f"{{{NS_SAML}}}Attribute")):
        if attr.get("Name") == "email":
            parent = attr.getparent()
            assert parent is not None
            parent.remove(attr)
    with pytest.raises(SamlError):
        _validate(_signed_response_b64(root))


def test_attribute_mapping_is_configurable() -> None:
    root = _response_xml()
    for attr in root.iter(f"{{{NS_SAML}}}Attribute"):
        if attr.get("Name") == "email":
            attr.set("Name", "corpEmail")
    auth = _auth(saml_attribute_email="corpEmail,email")
    profile, _ = _validate(_signed_response_b64(root), auth=auth)
    assert profile.email == "ada@corp.example"


def test_parse_idp_metadata() -> None:
    cert_body = (
        _CERT_PEM.decode()
        .replace("-----BEGIN CERTIFICATE-----", "")
        .replace("-----END CERTIFICATE-----", "")
        .replace("\n", "")
    )
    metadata = f"""<md:EntityDescriptor xmlns:md="{saml.NS_MD}" xmlns:ds="{saml.NS_DS}"
entityID="{_IDP_ENTITY}">
<md:IDPSSODescriptor protocolSupportEnumeration="{NS_SAMLP}">
<md:KeyDescriptor use="signing">
<ds:KeyInfo><ds:X509Data><ds:X509Certificate>{cert_body}</ds:X509Certificate></ds:X509Data></ds:KeyInfo>
</md:KeyDescriptor>
<md:SingleSignOnService Binding="{saml.BINDING_POST}" Location="{_IDP_SSO}-post"/>
<md:SingleSignOnService Binding="{saml.BINDING_REDIRECT}" Location="{_IDP_SSO}"/>
</md:IDPSSODescriptor></md:EntityDescriptor>"""
    idp = saml.parse_idp_metadata(metadata.encode())
    assert idp.entity_id == _IDP_ENTITY
    assert idp.sso_url == _IDP_SSO
    assert idp.certificates


def test_certificate_pems_inline_and_file(tmp_path: object) -> None:
    inline = _auth().saml_idp_certificates
    assert saml._certificate_pems(_auth()) == [_CERT_PEM]
    path = tmp_path / "idp.pem"  # type: ignore[operator]
    path.write_bytes(_CERT_PEM + b"\n")
    assert saml._certificate_pems(_auth(saml_idp_certificates=str(path))) == [_CERT_PEM]
    assert inline


def test_build_sso_redirect_deflates_request() -> None:
    url = saml.build_sso_redirect(_IDP, request_id=_REQUEST_ID, relay_state="relay-1", auth=_auth())
    query = parse_qs(urlsplit(url).query)
    assert url.startswith(_IDP_SSO)
    assert query["RelayState"] == ["relay-1"]
    inflated = zlib.decompress(base64.b64decode(query["SAMLRequest"][0]), wbits=-15).decode()
    assert f'ID="{_REQUEST_ID}"' in inflated
    assert f'AssertionConsumerServiceURL="{_ACS}"' in inflated
    assert f"<saml:Issuer>{_SP_ENTITY}</saml:Issuer>" in inflated
    assert f'Destination="{_IDP_SSO}"' in inflated


def test_sp_metadata_lists_acs_and_entity() -> None:
    xml = saml.sp_metadata_xml(_auth())
    assert f'entityID="{_SP_ENTITY}"' in xml
    assert f'Location="{_ACS}"' in xml


def test_provider_enabled_saml_matrix() -> None:
    assert _auth().provider_enabled("saml")
    assert not _auth(saml_idp_sso_url="").provider_enabled("saml")
    assert not _auth(saml_idp_certificates="").provider_enabled("saml")
    metadata_only = _auth(
        saml_idp_sso_url="",
        saml_idp_certificates="",
        saml_idp_metadata_url="https://idp.corp.example/metadata.xml",
    )
    assert metadata_only.provider_enabled("saml")
    disabled = _auth(disabled_providers="saml")
    assert not disabled.provider_enabled("saml")


def test_saml_urls_reject_query_and_scheme() -> None:
    with pytest.raises(ValueError):
        _auth(saml_idp_sso_url="ftp://idp/sso")
    with pytest.raises(ValueError):
        _auth(saml_idp_metadata_url="https://idp.example/m?x=1")


def test_qualified_subject_bounds_length() -> None:
    subject = saml._qualified_subject(_IDP_ENTITY, "n" * 300)
    assert len(subject) <= 255
    assert subject.startswith("idp.corp.example:")
    urn = saml._qualified_subject("urn:corp:idp", "uid-9")
    assert len(urn.split(":", 1)[0]) == 16
