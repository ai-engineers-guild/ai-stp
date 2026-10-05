"""Catalogue answers: search results, objects, versions, artifacts and
setup acquisition.
"""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_contracts.catalog import (
    CatalogTrust,
    ComponentSummary,
    PublicLifecycle,
    SetupSummary,
    VersionListEntry,
)
from ai_stp_contracts.http import Timestamp, open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_contracts.private_access import PrivateVersionTrust
from ai_stp_foundation.canonical import JsonValue

#: Which half of the catalogue an answer is about. Components and setups are
#: separate routes with separate cursors (`#71`), so a single call is about one
#: of them and saying which is not decoration.
type CatalogKind = Literal["component", "setup"]


#: Where an answer came from. `cache` is not a degraded `online`: it is a
#: statement about a moment in the past, and `checked_at` says which moment.
#: Presenting a cached answer as current is the failure `offline-capability.md`
#: forbids.
type AnswerSource = Literal["online", "cache"]


class CatalogSearchResult(ContractModel):
    """One page of public catalogue results, and where it came from."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    kind: CatalogKind
    source: AnswerSource

    #: When the platform actually answered. On a cached result this is in the
    #: past, and it is the field that stops the answer claiming to be current.
    checked_at: Timestamp

    items: list[ComponentSummary | SetupSummary]

    #: Results from the `experimental` lane, in their own section. `ADR-0016`
    #: keeps them out of the main list: an experimental candidate that appeared
    #: among authoritative ones would have been silently promoted.
    experimental: list[ComponentSummary | SetupSummary]

    #: Absent when there is no further page. Opaque: a client echoes it back and
    #: never constructs one.
    next_cursor: str | None


class CatalogObjectView(ContractModel):
    """One catalogue object with its published versions."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    kind: CatalogKind
    source: AnswerSource
    checked_at: Timestamp
    summary: ComponentSummary | SetupSummary

    #: Every offered version, newest first. Numbers are not contiguous by
    #: design: hiding a version does not free its number.
    versions: list[VersionListEntry]


class CatalogVersionView(ContractModel):
    """One exact published version and the passport it promises (issue #76).

    The digest travels with the passport because a client verifies one against
    the other: a passport offered under a digest that does not describe it is a
    truncated download or a substituted body, and both are refused rather than
    cached.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    distribution_visibility: Literal["public", "private"] = "public"
    kind: CatalogKind
    source: AnswerSource
    checked_at: Timestamp
    passport_digest: Annotated[str, Field(min_length=1)]
    lifecycle: PublicLifecycle
    trust: CatalogTrust | PrivateVersionTrust
    published_at: Timestamp

    #: The passport itself, exactly as the catalogue published it. Kept as the
    #: document rather than re-modelled: its shape is owned by
    #: `passport-envelope.md`, and a second model here could drift from it.
    passport: dict[str, JsonValue]


class CatalogArtifactView(ContractModel):
    """Where the verified bytes of one exact version now are (issue #76).

    Answered after the bytes have been checked against the passport, so a caller
    that receives this knows the file at `path` hashes to `digest` and is
    `size_bytes` long. `source` says whether the network was involved, which is
    what an offline caller needs to know about its own cache.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    kind: CatalogKind
    source: AnswerSource
    checked_at: Timestamp
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    digest: Annotated[str, Field(min_length=1)]
    size_bytes: Annotated[int, Field(ge=0)]

    #: Rendered with the home directory folded away, like every other path this
    #: CLI reports: `#73` keeps the account name out of output.
    path: Annotated[str, Field(min_length=1)]


class AcquiredComponentVersion(ContractModel):
    """One exact component made available to the local setup compiler."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    passport_digest: Annotated[str, Field(min_length=1)]
    artifact_digest: Annotated[str, Field(min_length=1)]


class CatalogSetupAcquisition(ContractModel):
    """An exact published setup graph materialized in the local registry."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    source: AnswerSource
    checked_at: Timestamp
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    passport_digest: Annotated[str, Field(min_length=1)]
    artifact_digest: Annotated[str, Field(min_length=1)]
    harness_id: Annotated[str, Field(min_length=1)]
    components: list[AcquiredComponentVersion]
