"""Authenticated exact private versions, independent of public discovery trust."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.auth import AccountId, DeviceId
from ai_stp_contracts.catalog import (
    PassportDigest,
    PrivateVersionResponse,
    PrivateVersionTrust,
    Version,
)
from ai_stp_contracts.http import IdempotencyKey, Timestamp, open_wire_object, strict_request_object
from ai_stp_contracts.publication import ObjectKind, PlanId

__all__ = [
    "CliPrivateVersionResponse",
    "PrivateVersionTrust",
    "VisibilityPlanCreateRequest",
    "VisibilityPlanResponse",
]


# The API and CLI deserialize exactly the same private catalog document.
CliPrivateVersionResponse = PrivateVersionResponse


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
