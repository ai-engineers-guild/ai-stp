"""Project technology scans, findings, reviews and mappings."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_contracts.http import open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_contracts.technology import TechnologyScanHandoff
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.ids import stable_id_pattern


class CliTechnologyEvidence(ContractModel):
    """One evidence trace of a local technology finding (issue #222)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    source: Literal["declared", "configured", "observed"]
    path: Annotated[str, Field(min_length=1)]
    reference: str | None = None
    confidence: Annotated[float, Field(ge=0, le=1)]


class CliTechnologyClaim(ContractModel):
    """One version claim inside a finding, with its evidence."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    version: str | None = None
    version_kind: Literal["unknown", "declared_range", "observed_version"]
    evidence: list[CliTechnologyEvidence]


class CliTechnologyFinding(ContractModel):
    """One stored technology finding and its review state (issue #222).

    `technology_id` is the resolved canonical identity when the mapping in
    effect covers the coordinate, else `null` — an unmapped finding is a fact
    to report, not an identity to invent.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    key: Annotated[str, Field(min_length=1)]
    kind: Literal["package", "image", "executable", "configuration", "alias"]
    coordinate: Annotated[str, Field(min_length=1)]
    context: Literal["production", "development", "testing", "browser_support"]
    technology_id: str | None = None
    effective_technology_id: str | None = None
    version: str | None = None
    version_kind: Literal["unknown", "declared_range", "observed_version"]
    review: Literal["proposed", "confirmed", "rejected", "overridden", "retired"]
    freshness: Literal["current", "stale", "absent", "unknown"]
    claims: list[CliTechnologyClaim]
    override_technology_id: str | None = None
    override_version: str | None = None
    first_seen_scan: Annotated[str, Field(min_length=1)]
    last_seen_scan: Annotated[str, Field(min_length=1)]
    source_revision: Annotated[str | None, Field(pattern=r"^[0-9a-f]{64}$")] = None
    reviewed_at: str | None = None


class CliTechnologyScan(ContractModel):
    """The result of `project detect`: one stored scan over one root.

    `handoff` resolves findings the way publication does — against the
    fetched organization snapshot when one is cached, else the bundled
    table — so an agent can inspect what would travel before anything does.
    `unmapped` names the coordinates that resolution cannot carry.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    scan_id: Annotated[str, Field(pattern=stable_id_pattern("scan"))]
    project_id: Annotated[str, Field(pattern=stable_id_pattern("project"))]
    root: Annotated[str, Field(min_length=1)]
    scope: Annotated[str, Field(min_length=1)]
    state: Literal["complete", "partial"]
    stopped_by: str | None = None
    detector_version: Annotated[str, Field(min_length=1)]
    mapping_version: Annotated[str, Field(min_length=1)]
    source_revision: Annotated[str | None, Field(pattern=r"^[0-9a-f]{64}$")] = None
    findings: list[CliTechnologyFinding]
    unmapped: list[str]
    observations: Annotated[int, Field(ge=0)]
    handoff: TechnologyScanHandoff


class CliTechnologyFindings(ContractModel):
    """Every stored finding for one local project (`project technologies`)."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    project_id: Annotated[str, Field(pattern=stable_id_pattern("project"))]
    findings: list[CliTechnologyFinding]


class CliTechnologyReview(ContractModel):
    """The finding after one confirm, reject, override or retire decision."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    finding: CliTechnologyFinding


class CliTechnologyMapping(ContractModel):
    """One cached organization mapping snapshot, summarized."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    organization_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    entries: Annotated[int, Field(ge=0)]


class CliTechnologyMappings(ContractModel):
    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    organization_id: Annotated[str, Field(min_length=1)]
    items: list[CliTechnologyMapping]


class CliTechnologyUnmappedItem(ContractModel):
    """One coordinate the effective mapping cannot resolve, with its contexts."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    kind: Literal["package", "image", "executable", "configuration", "alias"]
    coordinate: Annotated[str, Field(min_length=1)]
    contexts: Annotated[
        list[Literal["production", "development", "testing", "browser_support"]],
        Field(min_length=1),
    ]
    project_ids: list[Annotated[str, Field(min_length=1)]] = []


class CliTechnologyUnmapped(ContractModel):
    """The unmapped-coordinate queue for one project, or for one organization.

    Locally this is what `project detect` observed but could not resolve;
    remotely (`--organization`) it is every coordinate published scans left
    unresolved — the queue a registry operator works through when extending
    the mapping.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    project_id: str | None = None
    organization_id: str | None = None
    scope: str | None = None
    coordinates: list[CliTechnologyUnmappedItem]
