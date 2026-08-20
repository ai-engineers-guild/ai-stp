"""Versioned selection-impact and local blast-radius contracts (issue #307)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_contracts.http import Timestamp, strict_request_object


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ExactCoordinate(_Closed):
    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+$")]
    passport_digest: Annotated[str, Field(min_length=1)]


class TokenEstimator(_Closed):
    schema_version: Literal[1] = 1
    profile: Literal["ai-stp:utf8-bytes/1", "ai-stp:unicode-chars-div4/1"]
    accuracy: Literal["exact", "estimated"]
    method: Literal["utf8_byte_count", "unicode_codepoints_div_4"]
    model: str | None = None
    local_only: Literal[True] = True


class ComponentTokenMeasurement(_Closed):
    component: ExactCoordinate
    component_type: Literal["instruction", "skill", "agent", "command"]
    loading: Literal["always", "conditional"]
    status: Literal["exact", "estimated", "unavailable"]
    tokens: Annotated[int, Field(ge=0)] | None
    utf8_bytes: Annotated[int, Field(ge=0)]
    reason: str | None = None

    @model_validator(mode="after")
    def _status_matches_value(self) -> "ComponentTokenMeasurement":
        if (self.status == "unavailable") != (self.tokens is None):
            raise ValueError("unavailable measurements alone omit tokens")
        return self


class ContextBudget(_Closed):
    always_tokens: Annotated[int, Field(ge=0)]
    conditional_tokens: Annotated[int, Field(ge=0)]
    unavailable_components: Annotated[int, Field(ge=0)]
    components: list[ComponentTokenMeasurement]


class ContextDelta(_Closed):
    always_tokens: int
    conditional_tokens: int


class PriceProfile(_Closed):
    schema_version: Literal[1] = 1
    profile_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")]
    tokenizer_profile: Literal["ai-stp:utf8-bytes/1", "ai-stp:unicode-chars-div4/1"]
    model: Annotated[str, Field(min_length=1)]
    currency: Literal["USD"] = "USD"
    input_per_million: Annotated[str, Field(pattern=r"^[0-9]+(\.[0-9]+)?$")]
    source: Annotated[str, Field(pattern=r"^https://[^\s]+$")]
    fetched_at: Timestamp
    expires_at: Timestamp

    @model_validator(mode="after")
    def _ordered_window(self) -> "PriceProfile":
        if self.expires_at <= self.fetched_at:
            raise ValueError("price profile expiry must follow its fetch time")
        return self


class TokenCost(_Closed):
    status: Literal["available", "stale", "unavailable"]
    amount: str | None
    currency: Literal["USD"] | None
    profile_id: str | None
    source: str | None
    fetched_at: Timestamp | None
    reason: str | None


class CapabilitySnapshot(_Closed):
    tools: list[str]
    mcp_servers: list[str]
    hooks: list[str]
    network_requirements: list[str]
    credential_requirements: list[str]
    filesystem_permissions: list[str]
    network_permissions: list[str]
    process_permissions: list[str]


class CapabilityDelta(_Closed):
    added: CapabilitySnapshot
    removed: CapabilitySnapshot


class SelectionImpactReport(_Closed):
    schema_version: Literal[1] = 1
    generated_at: Timestamp
    freshness: Literal["local_snapshot"] = "local_snapshot"
    candidate_setup: ExactCoordinate
    baseline_setup: ExactCoordinate | None
    baseline_source: Literal["explicit", "installed", "selected", "none"]
    estimator: TokenEstimator
    candidate_context: ContextBudget
    baseline_context: ContextBudget | None
    context_delta: ContextDelta | None
    candidate_capabilities: CapabilitySnapshot
    baseline_capabilities: CapabilitySnapshot | None
    capability_delta: CapabilityDelta | None
    token_cost: TokenCost


class BlastRadiusReport(_Closed):
    schema_version: Literal[1] = 1
    generated_at: Timestamp
    freshness: Literal["local_snapshot"] = "local_snapshot"
    authority_boundary: Literal["local_registry"] = "local_registry"
    scenario: Literal["update", "deprecation", "blocked", "expired_evidence", "advisory"]
    component: ExactCoordinate
    setup_versions: list[ExactCoordinate]
    projects: list[str]
    devices: list[str]
    installed_targets: list[str]
    action: Literal["none"] = "none"


type ImpactScenario = Literal["update", "deprecation", "blocked", "expired_evidence", "advisory"]
type AccountFreshness = Literal["account_snapshot", "stale", "unavailable"]
type AccountImpactStatus = Literal["ready", "partial", "stale", "invalid_graph"]
type EstimatorProfile = Literal["ai-stp:utf8-bytes/1", "ai-stp:unicode-chars-div4/1"]


class AccountSelectionImpactQuery(BaseModel):
    """Authenticated query for one account-scoped selection impact report."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    candidate_id: Annotated[str, Field(min_length=1)]
    candidate_version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+$")]
    baseline_id: Annotated[str, Field(min_length=1)] | None = None
    baseline_version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+$")] | None = None
    project_id: Annotated[str, Field(min_length=1)] | None = None
    estimator_profile: EstimatorProfile = "ai-stp:utf8-bytes/1"

    @model_validator(mode="after")
    def _baseline_pair_is_complete(self) -> "AccountSelectionImpactQuery":
        if (self.baseline_id is None) != (self.baseline_version is None):
            raise ValueError("baseline id and version must be supplied together")
        return self


class AccountBlastRadiusQuery(BaseModel):
    """Authenticated query for one account-scoped blast-radius report."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=strict_request_object)

    schema_version: Literal[1] = 1
    component_id: Annotated[str, Field(min_length=1)]
    component_version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+$")]
    scenario: ImpactScenario


class AccountSelectionImpactReport(_Closed):
    """Server-owned account projection. Local v1 ``SelectionImpactReport`` stays unchanged."""

    schema_version: Literal[1] = 1
    generated_at: Timestamp
    authority_boundary: Literal["account"] = "account"
    freshness: AccountFreshness
    source_revision: Annotated[str, Field(min_length=1)] | None
    action: Literal["none"] = "none"
    status: AccountImpactStatus
    unavailable_reason: Annotated[str, Field(min_length=1)] | None = None
    candidate_setup: ExactCoordinate
    baseline_setup: ExactCoordinate | None
    baseline_source: Literal["explicit", "installed", "selected", "none"]
    estimator: TokenEstimator
    candidate_context: ContextBudget
    baseline_context: ContextBudget | None
    context_delta: ContextDelta | None
    candidate_capabilities: CapabilitySnapshot
    baseline_capabilities: CapabilitySnapshot | None
    capability_delta: CapabilityDelta | None
    token_cost: TokenCost


class AccountBlastRadiusReport(_Closed):
    """Server-owned account reverse-reference report. Local v1 stays unchanged."""

    schema_version: Literal[1] = 1
    generated_at: Timestamp
    authority_boundary: Literal["account"] = "account"
    freshness: AccountFreshness
    source_revision: Annotated[str, Field(min_length=1)] | None
    action: Literal["none"] = "none"
    status: AccountImpactStatus
    unavailable_reason: Annotated[str, Field(min_length=1)] | None = None
    scenario: ImpactScenario
    component: ExactCoordinate
    setup_versions: list[ExactCoordinate]
    projects: list[str]
    devices: list[str]
    installed_targets: list[str]
