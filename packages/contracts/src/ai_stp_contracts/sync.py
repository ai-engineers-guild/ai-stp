"""Private revision-sync wire payloads (SPEC-025, docs/contracts/sync-event.md).

Push and pull are the only server surfaces for the account-scoped revision
ledger. Receipt state lives in the response body; a typed conflict is not a
silent overwrite. Cursor is opaque and account-bound — the client may only
echo it. Forbidden document classes are unrepresentable through the allowlist
and payload policy enforced by the server application layer.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.auth import AccountId, DeviceId
from ai_stp_contracts.http import (
    PAGE_SIZE_DEFAULT,
    PAGE_SIZE_MAX,
    Cursor,
    IdempotencyKey,
    PageInfo,
    PageSize,
    Timestamp,
    open_wire_object,
    strict_request_object,
)
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.revisions import REVISION_ID_PATTERN

#: Closed allowlist for #179 (SPEC-025 REQ-2501, sync-event.md).
type SyncEntityKind = Literal[
    "developer_passport",
    "device_summary",
    "component_private",
    "setup_private",
    "unverified_consent",
]

type SyncOperation = Literal["upsert", "tombstone"]
type SyncReceiptState = Literal["accepted", "rejected", "conflict", "superseded"]

type RevisionId = Annotated[str, Field(pattern=REVISION_ID_PATTERN)]
type ContentDigest = Annotated[str, Field(pattern=DIGEST_PATTERN)]

#: Client-chosen event identity. Opaque to the server beyond uniqueness in the
#: request; bounded so it cannot become an unbounded storage key.
type EventId = Annotated[str, Field(pattern=r"^[A-Za-z0-9._~-]{8,128}$")]

#: Entity identity string. Prefix checks against entity_kind are application
#: policy, not a second wire enum: a mistyped id is a validation failure, not a
#: schema evolution of kinds.
type EntityId = Annotated[str, Field(min_length=1, max_length=128)]


class SyncEvent(BaseModel):
    """One push event: a candidate revision and its idempotency key.

    ``device_id`` must match the session-bound active device; the server never
    trusts a different device claim (REQ-2508). ``payload`` is the allowlisted
    revision document body; tombstone may send an empty object.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    event_id: EventId
    entity_id: EntityId
    entity_kind: SyncEntityKind
    revision_id: RevisionId
    parent_revision_ids: Annotated[list[RevisionId], Field(max_length=8)]
    device_id: DeviceId
    actor_id: AccountId
    operation: SyncOperation
    content_digest: ContentDigest
    created_at: Timestamp
    idempotency_key: IdempotencyKey
    #: Null only for the first revision of an entity (no prior server head).
    expected_head_revision_id: RevisionId | None
    payload: dict[str, object]


class SyncPushRequest(BaseModel):
    """POST /v1/sync/push body. Events are applied in the listed order."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    events: Annotated[list[SyncEvent], Field(min_length=1, max_length=PAGE_SIZE_MAX)]


class SyncConflictInfo(BaseModel):
    """Enough graph material for the client to locate a common ancestor."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    server_head_revision_id: RevisionId
    client_head_revision_id: RevisionId
    common_ancestor_revision_id: RevisionId | None
    affected_fields: Annotated[list[str], Field(max_length=64)]


class SyncEventReceipt(BaseModel):
    """Durable outcome of one event (SPEC-009 receipt states)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    event_id: EventId
    state: SyncReceiptState
    revision_id: RevisionId | None
    server_head_revision_id: RevisionId | None
    #: Present on accepted events: position after this accept in the outbox.
    cursor: Cursor | None
    conflict: SyncConflictInfo | None
    #: Stable code when state is rejected; null otherwise.
    error_code: str | None


class SyncPushResponse(BaseModel):
    """Per-event receipts for one push request, in request order."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    receipts: Annotated[list[SyncEventReceipt], Field(min_length=1, max_length=PAGE_SIZE_MAX)]


class SyncPullQuery(BaseModel):
    """GET /v1/sync/pull query parameters."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    cursor: Cursor | None = None
    page_size: PageSize = PAGE_SIZE_DEFAULT


class SyncStreamEvent(BaseModel):
    """One accepted event as delivered on pull from the server outbox."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    event_id: EventId
    entity_id: EntityId
    entity_kind: SyncEntityKind
    revision_id: RevisionId
    parent_revision_ids: Annotated[list[RevisionId], Field(max_length=8)]
    device_id: DeviceId
    actor_id: AccountId
    operation: SyncOperation
    content_digest: ContentDigest
    created_at: Timestamp
    payload: dict[str, object]
    sequence: Annotated[int, Field(ge=1)]


class SyncPullResponse(BaseModel):
    """Bounded ordered packet from the account outbox."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    items: Annotated[list[SyncStreamEvent], Field(max_length=PAGE_SIZE_MAX)]
    page: PageInfo
