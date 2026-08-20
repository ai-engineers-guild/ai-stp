"""Author attestation record (ADR-0026, docs/contracts/validation-policy.md).

The accepted evidence for a credential-dependent mandatory check: signed by
the author's device key and bound to the exact object digest, object version,
policy, tool, harness and provider versions, test-case IDs, result, account,
device and time. Secret values, tokens and issuance URLs are not
representable; the record is platform-owned, so unknown fields fail closed
instead of being preserved.

The signature covers the canonical bytes of the record without the
``signature`` field, hashed in the ``ai-stp:attestation:v1`` domain. Actual
key handling arrives with the CLI device identity; this module owns the wire
shape and the signed-payload boundary.
"""

from typing import Annotated, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import DIGEST_PATTERN, digest_canonical
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.refs import ComponentRef, SetupRef
from ai_stp_foundation.timestamps import TIMESTAMP_PATTERN

_ATTESTATION_DOMAIN: Final[str] = "ai-stp:attestation:v1"

# An Ed25519 signature is exactly 64 bytes: 86 base64 characters plus padding.
SIGNATURE_PATTERN: Final[str] = r"^[A-Za-z0-9+/]{86}==$"


class AuthorAttestation(BaseModel):
    """Signed evidence of one credential-dependent check on the author's device."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    object_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    subject: ComponentRef | SetupRef
    check_id: Annotated[str, Field(min_length=1)]
    policy_version: Annotated[str, Field(min_length=1)]
    tool_versions: dict[str, str] = Field(default_factory=dict)
    harness_id: HarnessId
    harness_version: Annotated[str, Field(min_length=1)]
    provider_version: Annotated[str, Field(min_length=1)]
    test_case_ids: Annotated[list[str], Field(min_length=1)]
    result: Literal["passed", "failed"]
    account_id: Annotated[str, Field(pattern=stable_id_pattern("account"))]
    device_id: Annotated[str, Field(pattern=stable_id_pattern("device"))]
    attested_at: Annotated[str, Field(pattern=TIMESTAMP_PATTERN)]
    signature: Annotated[str, Field(pattern=SIGNATURE_PATTERN)]


def attestation_payload(record: AuthorAttestation) -> JsonValue:
    """Return the signed portion of the record: everything but the signature."""
    data = cast(dict[str, JsonValue], record.model_dump(mode="json"))
    del data["signature"]
    return data


def attestation_digest(record: AuthorAttestation) -> str:
    """Hash the signed payload in the attestation domain."""
    return digest_canonical(_ATTESTATION_DOMAIN, attestation_payload(record))
