"""Account and device payloads (issue #71, SPEC-002, docs/contracts/device-passport.md).

The device summary here is the **only** representation of a device's environment
that leaves the machine. `device-passport.md` closes its composition to five
facts, and the passport itself — which additionally holds observed environment
facts and detector source paths — is never an API payload (SPEC-010 REQ-1013).
That is why this module declares a summary type of its own instead of reusing or
narrowing the passport: a narrowed passport would still carry the passport's
shape, and the next added passport field would silently join the wire.

The account read is deliberately thin for Sprint 1: an identifier, when it was
created, and which providers are linked. No email address appears, on either the
account or an identity — knowing an address is not an authorization (SPEC-002
security section) and an address the caller already knows is not worth putting
on a route that exists to answer "who am I".
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_stp_contracts.auth import AccountId, DeviceId, DisplayName, OAuthProvider
from ai_stp_contracts.http import (
    PAGE_SIZE_MAX,
    IdempotencyKey,
    PageInfo,
    Timestamp,
    open_wire_object,
    strict_request_object,
)
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.identity import HANDLE_PATTERN, submitted_display_name, normalize_handle

#: A device is either accepted for cloud work or it is not. Revocation is
#: forward-acting: it stops future sync and attestation and leaves local reads
#: and already-received bytes alone (SPEC-002 REQ-205).
type DeviceState = Literal["active", "revoked"]


class DetectedHarness(BaseModel):
    """One harness observed on the device, with the version that was observed.

    Only the supported harnesses are itemised. An unknown harness stays a
    local observation and never leaves the machine (SPEC-011 REQ-1109): it
    creates no managed object, so listing it here would put an environment fact
    on the wire for something the platform cannot act on.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    harness_id: HarnessId
    version: Annotated[str, Field(min_length=1, max_length=64)]


class DeviceSummary(BaseModel):
    """The closed five-fact summary a device is allowed to publish.

    Closed by `device-passport.md`: display name, operating system and
    architecture, detected harnesses with versions, toolchain profile version,
    and when the summary was last refreshed. Secret values, environment variable
    values and absolute user paths are excluded there and unrepresentable here.

    Note the wire policy still tolerates additive fields, as everywhere else —
    the closure is a rule about what a *conforming server* sends, and the
    fixtures and contract tests are what hold it.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    display_name: DisplayName
    operating_system: Literal["linux", "macos", "windows"]
    architecture: Literal["x86_64", "arm64"]
    detected_harnesses: Annotated[list[DetectedHarness], Field(max_length=16)]
    toolchain_profile_version: Annotated[str, Field(min_length=1, max_length=64)]
    summary_updated_at: Timestamp


class DeviceRecord(BaseModel):
    """One device as the account owner sees it, in the web or through the CLI."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    device_id: DeviceId
    state: DeviceState
    registered_at: Timestamp
    last_active_at: Timestamp
    device_type: Literal["cli", "web"]
    approximate_location: Annotated[str | None, Field(max_length=160)]
    user_agent: Annotated[str | None, Field(max_length=512)]

    #: Present only when the device has published one: synchronisation is off by
    #: default, and a device that never sent a summary must be listed rather
    #: than hidden — the owner still needs to be able to revoke it.
    summary: DeviceSummary | None

    #: The current version of this record, for `If-Match` on revoke. A stale
    #: value answers `AI_STP_PRECONDITION_FAILED`, which is distinct from a
    #: concurrent-change conflict.
    etag: Annotated[str, Field(min_length=1, max_length=128)]


class DeviceListResponse(BaseModel):
    """Every device of the current account, newest activity first."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    items: Annotated[list[DeviceRecord], Field(max_length=PAGE_SIZE_MAX)]
    page: PageInfo


class DeviceRevokeRequest(BaseModel):
    """Revoke one device.

    Idempotent by key, so a retried revoke after a timeout does not become a
    second operation. The expected `etag` travels in the `If-Match` header
    rather than the body; it is named here only so the contract states that the
    precondition is required.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    idempotency_key: IdempotencyKey


class DeviceRevokeResponse(BaseModel):
    """The device after revocation.

    Revocation is forward-acting and reported as such: the record survives, the
    summary is marked revoked rather than deleted, and the device keeps its
    local data (SPEC-002 REQ-205, REQ-215).
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    device: DeviceRecord
    revoked_at: Timestamp


class LinkedIdentity(BaseModel):
    """One provider linked to the account.

    No address: an identity is named by its provider and when it was linked. The
    address belongs to the provider and adding it here would put personal data
    on a route that does not need it (SPEC-013). Optional avatar_url is a
    provider-hosted HTTPS image URL, not an email or long-lived token.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    provider: OAuthProvider
    linked_at: Timestamp
    # Presentation fields (HTTPS avatar URL + short label). Null when the provider
    # did not supply them — still required keys on the open wire object.
    avatar_url: Annotated[str | None, Field(max_length=2048)]
    display_name: Annotated[str | None, Field(max_length=120)]


class AccountProfile(BaseModel):
    """The current account, as the caller who holds it sees it.

    Separate from `PublicProfile` (ADR-0023, ADR-0010), which is an authored
    public object and is not derived from this one.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    account_id: AccountId
    created_at: Timestamp
    identities: Annotated[list[LinkedIdentity], Field(min_length=1, max_length=8)]
    show_profile_publicly: bool
    allow_publisher_listing: bool
    handle: Annotated[str, Field(default="", max_length=32)] = ""
    display_name: Annotated[str, Field(default="", max_length=80)] = ""


class AccountIdentityUpdate(BaseModel):
    """Replace the current account public handle and display name."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    handle: Annotated[str, Field(pattern=HANDLE_PATTERN, min_length=1, max_length=32)]
    display_name: Annotated[str, Field(min_length=1, max_length=80)]
    idempotency_key: IdempotencyKey

    @field_validator("handle")
    @classmethod
    def closed_handle(cls, value: str) -> str:
        return normalize_handle(value)

    @field_validator("display_name")
    @classmethod
    def collapsed_display(cls, value: str) -> str:
        return submitted_display_name(value)


class AccountPrivacyUpdate(BaseModel):
    """Replace the current account privacy preferences."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    show_profile_publicly: bool
    allow_publisher_listing: bool


class DeviceRegisterResponse(BaseModel):
    """POST /v1/devices registration resource body."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    device: DeviceRecord
    created: bool
