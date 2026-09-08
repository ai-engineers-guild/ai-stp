"""Authenticated exact private versions, independent of public discovery trust."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.auth import AccountId, DeviceId
from ai_stp_contracts.catalog import PassportDigest, PublicLifecycle, Version
from ai_stp_contracts.http import IdempotencyKey, Timestamp, open_wire_object, strict_request_object
from ai_stp_contracts.publication import ObjectKind, PlanId
from ai_stp_foundation.canonical import JsonValue


class PrivateVersionTrust(BaseModel):
    """Exact local acquisition authority does not assert public verification."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    trust_lane: Literal["local_owner_or_pinned"] = "local_owner_or_pinned"
    author_verified: bool
    component_verified: bool


class CliPrivateVersionResponse(BaseModel):
    """Metadata delivered only after exact owner or major-line grant authorization."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    kind: ObjectKind
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    version: Version
    passport_digest: PassportDigest
    passport: dict[str, JsonValue]
    lifecycle: PublicLifecycle
    trust: PrivateVersionTrust
    published_at: Timestamp
    access_basis: Literal["owner", "grant", "admin"]


PrivateVersionResponse = CliPrivateVersionResponse


class VisibilityPlanCreateRequest(BaseModel):
    """Plan one owner's access change without rewriting immutable content."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    object_kind: ObjectKind
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    version: Version
    visibility: Literal["public", "private"]
    device_id: DeviceId
    idempotency_key: IdempotencyKey


class VisibilityPlanResponse(BaseModel):
    """A reviewed exposure effect with immutable identity and current access bindings."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    plan_id: PlanId
    plan_hash: PassportDigest
    state: Literal["planned", "applied", "expired", "refused"]
    object_kind: ObjectKind
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    version: Version
    passport_digest: PassportDigest
    previous_visibility: Literal["public", "private"]
    visibility: Literal["public", "private"]
    actor_id: AccountId
    device_id: DeviceId
    expires_at: Timestamp
    effects: list[str]
