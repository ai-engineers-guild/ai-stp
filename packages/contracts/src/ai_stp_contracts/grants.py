"""Access grant and invitation wire payloads (SPEC-026, SPEC-002, ADR-0020/0030)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.auth import AccountId
from ai_stp_contracts.http import (
    IdempotencyKey,
    Timestamp,
    open_wire_object,
    strict_request_object,
)

type InvitationState = Literal["pending", "accepted", "expired", "revoked"]
type GrantState = Literal["active", "revoked"]
type ObjectKind = Literal["component", "setup"]
type DirectRecipientKind = Literal["github_username", "user_id"]


class DirectGrantCreateRequest(BaseModel):
    """POST /v1/grants/direct body with an explicit recipient identifier kind."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    object_kind: ObjectKind
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    major: Annotated[int, Field(ge=0, le=9999)]
    recipient_kind: DirectRecipientKind
    recipient: Annotated[str, Field(min_length=1, max_length=320)]
    idempotency_key: IdempotencyKey


class GrantInvitationCreateRequest(BaseModel):
    """POST /v1/grants/invitations body."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    object_kind: ObjectKind
    stable_id: Annotated[str, Field(min_length=8, max_length=64)]
    major: Annotated[int, Field(ge=0, le=9999)]
    recipient_email: Annotated[str, Field(min_length=3, max_length=320)]
    idempotency_key: IdempotencyKey
    ttl_seconds: Annotated[int, Field(default=604_800, ge=60, le=2_592_000)] = 604_800


class GrantInvitationResponse(BaseModel):
    """Invitation create/list item. Never includes the raw token."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    invitation_id: Annotated[str, Field(min_length=8, max_length=64)]
    object_kind: ObjectKind
    stable_id: str
    major: int
    state: InvitationState
    expires_at: Timestamp
    created_at: Timestamp


class AccessGrantResponse(BaseModel):
    """One major-line access grant."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    grant_id: Annotated[str, Field(min_length=8, max_length=64)]
    object_kind: ObjectKind
    stable_id: str
    major: int
    grantee_account_id: AccountId
    owner_account_id: AccountId
    state: GrantState
    created_at: Timestamp
    revoked_at: Timestamp | None = None
    recipient_kind: DirectRecipientKind | None
    recipient: str | None


class GrantListResponse(BaseModel):
    """Owned invitations and grants for the caller."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    invitations: Annotated[list[GrantInvitationResponse], Field(default_factory=list)]
    grants: Annotated[list[AccessGrantResponse], Field(default_factory=list)]


class GrantAcceptRequest(BaseModel):
    """POST /v1/grants/invitations/{invitation_id}/accept body."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    token: Annotated[str, Field(min_length=16, max_length=256)]
    idempotency_key: IdempotencyKey


class GrantRevokeRequest(BaseModel):
    """Revoke invitation or grant with an optional reason."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    reason: Annotated[str, Field(default="", max_length=500)] = ""
    idempotency_key: IdempotencyKey


class GrantRevokeResponse(BaseModel):
    """Outcome of a revoke action."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    revoked: bool = True
    local_bytes_retained: bool = True


class CliGrantInvitationView(GrantInvitationResponse):
    """CLI view of one invitation, separate from the HTTP schema boundary."""


class CliGrantAccessView(AccessGrantResponse):
    """CLI view of one access grant, separate from the HTTP schema boundary."""


class CliGrantListView(GrantListResponse):
    """CLI view of the caller's grants, separate from the HTTP schema boundary."""


class CliGrantRevokeView(GrantRevokeResponse):
    """CLI view of a revocation, separate from the HTTP schema boundary."""
