"""Setup update, compose, recast, export and component materialization."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from ai_stp_contracts.http import open_wire_object
from ai_stp_contracts.model import ContractModel
from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_passports.versions import ComponentType


class SetupUpdatePlan(ContractModel):
    """Preview of one explicit embedded-component update. Selection is unchanged."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    setup_id: Annotated[str, Field(min_length=1)]
    from_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    to_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    component_id: Annotated[str, Field(min_length=1)]
    snapshot_coordinate: Annotated[str, Field(min_length=1, max_length=1024)]
    snapshot_identity: Annotated[str, Field(min_length=1, max_length=256)]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    selected_stable_id: str = ""
    selected_version: str = ""
    suggested_catalog_stable_id: str = ""
    suggested_catalog_version: str = ""
    suggested_catalog_dismissible: bool = False


class SetupUpdateResult(ContractModel):
    """Outcome of a confirmed exact update. A new immutable setup version."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    setup_id: Annotated[str, Field(min_length=1)]
    from_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    to_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    created: bool
    selected_stable_id: str = ""
    selected_version: str = ""
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]


class SetupComposeMember(ContractModel):
    """One exact member frozen by a setup composition plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    source: Annotated[str, Field(min_length=1, max_length=1024)]
    embedded: bool


class SetupComposePlan(ContractModel):
    """Exact preview for a new mixed catalog/Git/package/path setup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    setup_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    harness_id: Annotated[str, Field(min_length=1)]
    created_at: Annotated[str, Field(min_length=1)]
    definition_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    members: list[SetupComposeMember]


class SetupComposeResult(ContractModel):
    """A newly recorded immutable mixed setup version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    setup_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    created_at: Annotated[str, Field(min_length=1)]
    passport_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    definition_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    created: bool


class SetupRecastMember(ContractModel):
    """One source component and what recast will do with it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stable_id: Annotated[str, Field(min_length=1)]
    source_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    target_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    component_type: ComponentType
    disposition: Literal["reuse", "derive", "blocked"]
    reason: Annotated[str, Field(min_length=1, max_length=512)]


class SetupRecastPlan(ContractModel):
    """Exact preview for a new setup recast onto another harness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    setup_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    source_setup_id: Annotated[str, Field(min_length=1)]
    source_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    source_harness_id: HarnessId
    target_harness_id: HarnessId
    created_at: Annotated[str, Field(min_length=1)]
    complete: bool
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    members: list[SetupRecastMember]


class SetupRecastResult(ContractModel):
    """A newly recorded setup recast from an exact source version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    setup_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    source_setup_id: Annotated[str, Field(min_length=1)]
    source_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    created_at: Annotated[str, Field(min_length=1)]
    passport_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    created: bool


class ComponentMaterializeTarget(ContractModel):
    """One requested target harness inside a materialize plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_harness_id: HarnessId
    disposition: Literal["reuse", "derive", "blocked"]
    reason: Annotated[str, Field(min_length=1, max_length=512)]
    projection_digest: Annotated[str, Field(min_length=1)]
    semantic_losses: list[Annotated[str, Field(min_length=1, max_length=512)]] = []
    filesystem_permissions: list[Annotated[str, Field(min_length=1, max_length=1024)]] = []
    network_permissions: list[Annotated[str, Field(min_length=1, max_length=1024)]] = []
    process_permissions: list[Annotated[str, Field(min_length=1, max_length=1024)]] = []


class ComponentMaterializePlan(ContractModel):
    """Exact preview for one or more target-harness adaptations of a pinned component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    overlay_id: Annotated[str, Field(min_length=1)]
    source_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    target_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    source_harness_id: HarnessId
    target_harness_id: HarnessId
    source_passport_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    transform_id: Annotated[str, Field(min_length=1)]
    transform_version: Annotated[str, Field(min_length=1)]
    provider_profile_digest: Annotated[str, Field(min_length=1)]
    projection_digest: Annotated[str, Field(min_length=1)]
    disposition: Literal["reuse", "derive", "blocked"]
    reason: Annotated[str, Field(min_length=1, max_length=512)]
    semantic_losses: list[Annotated[str, Field(min_length=1, max_length=512)]] = []
    filesystem_permissions: list[Annotated[str, Field(min_length=1, max_length=1024)]] = []
    network_permissions: list[Annotated[str, Field(min_length=1, max_length=1024)]] = []
    process_permissions: list[Annotated[str, Field(min_length=1, max_length=1024)]] = []
    targets: Annotated[list[ComponentMaterializeTarget], Field(min_length=1)]
    local_only: bool
    complete: bool
    created_at: Annotated[str, Field(min_length=1)]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]


class ComponentMaterializeResult(ContractModel):
    """A recorded target adaptation, either on the source line or a local overlay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    source_stable_id: Annotated[str, Field(min_length=1)]
    source_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    target_harness_id: HarnessId
    target_harness_ids: list[HarnessId] = []
    created_at: Annotated[str, Field(min_length=1)]
    passport_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    local_only: bool
    created: bool


class SetupExportResult(ContractModel):
    """A review tree of one already-recorded local setup. Not a harness tree."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    setup_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    passport_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    definition_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    export_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    export_format: Literal["ai-stp-setup-export/1"] = "ai-stp-setup-export/1"
    output: Annotated[str, Field(min_length=1)]
    files_written: Annotated[int, Field(ge=1)]
    result: Literal["local_setup_definition"] = "local_setup_definition"
    storage: Literal["local_registry"] = "local_registry"
    physical_target_tree_created: Literal[False] = False
