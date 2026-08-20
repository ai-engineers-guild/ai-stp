"""Passport envelope (docs/contracts/passport-envelope.md, ADR-0025, ADR-0036).

The envelope is the single machine-readable description of an object. Five
kinds exist; developer, device and project passports are mutable through
revisions, component and setup version passports are immutable snapshots.
The revision ID is content-addressed: it is derived from the canonical
envelope content without the ``revision_id`` field itself, so equal content
seals to the same revision on every device.

Persisted passports preserve unknown optional fields within the supported
major version (``extra="allow"``); the generated schema mirrors that with an
open extension boundary and wire-required declared fields.
"""

import re
from typing import Annotated, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import JsonSchemaValue

from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import stable_id_pattern
from ai_stp_foundation.revisions import REVISION_ID_PATTERN, revision_id
from ai_stp_foundation.timestamps import TIMESTAMP_PATTERN
from ai_stp_passports.facts import Fact

type PassportKind = Literal["developer", "device", "project", "component", "setup"]

PASSPORT_KINDS: Final[frozenset[str]] = frozenset(
    {"developer", "device", "project", "component", "setup"}
)
MUTABLE_KINDS: Final[frozenset[str]] = frozenset({"developer", "device", "project"})
# Compatibility taxonomy for callers that distinguish registry drafts from the
# three identity/project passport kinds.  Immutability is enforced by the
# concrete ComponentVersionPassport and SetupVersionPassport models: a local
# component draft uses the component kind while it advances through revisions.
IMMUTABLE_KINDS: Final[frozenset[str]] = frozenset({"component", "setup"})

type RevisionId = Annotated[str, Field(pattern=REVISION_ID_PATTERN)]
type Timestamp = Annotated[str, Field(pattern=TIMESTAMP_PATTERN)]


def _open_wire_object(schema: JsonSchemaValue) -> None:
    """Passports persist: declared fields are wire-required, unknown optional
    fields are preserved rather than rejected within the supported major."""
    properties = schema.get("properties", {})
    schema["required"] = sorted(properties)
    schema["additionalProperties"] = True


class PassportEnvelope(BaseModel):
    """Common envelope of every passport kind."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=_open_wire_object)

    schema_version: Literal[1] = 1
    kind: PassportKind
    stable_id: str
    revision_id: RevisionId
    parent_revision_ids: list[RevisionId] = Field(default_factory=list)
    owner_id: Annotated[str, Field(pattern=stable_id_pattern("account"))]
    created_at: Timestamp
    visibility: Literal["private", "public"] = "private"
    facts: dict[str, Fact] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _kind_consistency(self) -> "PassportEnvelope":
        if re.fullmatch(stable_id_pattern(self.kind).strip("^$"), self.stable_id) is None:
            raise ValueError(f"stable_id prefix must match kind {self.kind!r}: {self.stable_id!r}")
        return self


def _revision_payload(data: dict[str, JsonValue]) -> JsonValue:
    return {key: value for key, value in data.items() if key != "revision_id"}


def derive_revision_id(data: dict[str, JsonValue]) -> str:
    """Derive the content-addressed revision ID of envelope data."""
    return revision_id(_revision_payload(data))


def seal_envelope(data: dict[str, JsonValue]) -> PassportEnvelope:
    """Fill ``revision_id`` from content and validate the sealed envelope."""
    sealed = dict(data)
    sealed["revision_id"] = derive_revision_id(sealed)
    return PassportEnvelope.model_validate(sealed)


def verify_revision_id(envelope: PassportEnvelope) -> bool:
    """Report whether the envelope's revision ID matches its content."""
    data = cast(dict[str, JsonValue], envelope.model_dump(mode="json"))
    return envelope.revision_id == derive_revision_id(data)
