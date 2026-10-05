"""What `sync status`, `sync push` and `sync pull` report."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_contracts.http import open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_foundation.digests import DIGEST_PATTERN


class SyncPreview(ContractModel):
    """A read-only decision over the local heads of one syncable entity."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    state: Literal[
        "up_to_date",
        "fast_forward",
        "merge_ready",
        "conflict",
        "manual_resolution",
    ]
    head_revision_ids: Annotated[list[str], Field(min_length=1)]
    common_ancestor_revision_id: str | None
    candidate_revision_id: str | None
    #: The head the server last named in a refusal this device stored, when the
    #: device does not hold it. Null whenever local heads are the whole story.
    server_head_revision_id: str | None

    #: JSON Pointer paths only. Values remain in the owner-only registry and
    #: never enter a generic command envelope or log by accident.
    affected_fields: list[str] = Field(default_factory=list)


class SyncPushView(ContractModel):
    """Durable outcome of pushing one exact local revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    processed_events: Annotated[int, Field(ge=1)]
    local_revision_id: Annotated[str, Field(min_length=1)]
    event_id: Annotated[str, Field(min_length=8)]
    remote_revision_id: Annotated[str, Field(min_length=1)]
    state: Literal["accepted", "rejected", "conflict", "superseded"]
    server_head_revision_id: str | None
    conflict_fields: list[str] = Field(default_factory=list)
    #: The identity the account already holds, when this push was refused for
    #: carrying a second one of a kind that admits exactly one. Without it the
    #: refusal is correct and the next move is unnameable.
    conflicting_entity_id: str | None


class SyncPendingVersion(ContractModel):
    """An exact legacy version reference whose snapshot is not available yet."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    stable_id: str
    version: str
    passport_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    revision_id: str
    event_id: str


class SyncPullView(ContractModel):
    """One atomically applied page from the private account stream."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    received: Annotated[int, Field(ge=0)]
    applied: Annotated[int, Field(ge=0)]
    replayed: Annotated[int, Field(ge=0)]
    #: Events the caller named and this pull walked past without applying. An
    #: abandoned revision is not a quiet outcome, so it is counted separately
    #: from `applied` and the ids are answered back.
    skipped: Annotated[list[str], Field(max_length=64)] = Field(default_factory=list)
    state: Literal["pulling", "up_to_date", "partial"] = "pulling"
    pending_version_count: Annotated[int, Field(ge=0)] = 0
    pending_versions: Annotated[list[SyncPendingVersion], Field(max_length=128)] = Field(
        default_factory=list[SyncPendingVersion]
    )
    next_cursor: str | None
