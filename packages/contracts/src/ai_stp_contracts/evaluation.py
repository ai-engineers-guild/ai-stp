"""Versioned setup evaluation profiles, plans, and immutable local evidence."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_stp_foundation.digests import DIGEST_PATTERN
from ai_stp_passports.versions import ComponentType, Permissions

EvaluationMethod = Literal["deterministic", "model_assisted", "human_review"]
EvaluationStatus = Literal["passed", "failed", "not_run", "degraded"]
EvaluationScope = Literal["component", "subset", "setup"]


class EvaluationBudget(BaseModel):
    """Closed resource ceiling for one evaluation check."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    timeout_seconds: Annotated[int, Field(ge=1, le=3600)]
    max_output_bytes: Annotated[int, Field(ge=1, le=16 * 1024 * 1024)]
    max_network_requests: Annotated[int, Field(ge=0, le=1024)] = 0


class EvaluationCheck(BaseModel):
    """One declared assertion and the runner class allowed to evaluate it."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    check_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{2,95}$")]
    component_type: ComponentType | None = None
    method: EvaluationMethod
    runner: Literal["local_static", "isolated_process", "model", "human"]
    assertion: Annotated[str, Field(min_length=1, max_length=500)]
    tolerance: Annotated[str, Field(min_length=1, max_length=500)]
    budget: EvaluationBudget
    isolation_requirements: list[Annotated[str, Field(min_length=1, max_length=120)]] = []

    @model_validator(mode="after")
    def runner_matches_method(self) -> Self:
        allowed = {
            "deterministic": {"local_static", "isolated_process"},
            "model_assisted": {"model"},
            "human_review": {"human"},
        }
        if self.runner not in allowed[self.method]:
            raise ValueError("evaluation runner does not match the declared method")
        return self


class SetupEvalProfile(BaseModel):
    """Reusable evaluation intent, independent from one setup version."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    profile_version: Literal["setup-eval/1"] = "setup-eval/1"
    profile_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.-]{2,95}$")]
    scope: EvaluationScope
    component_types: Annotated[list[ComponentType], Field(min_length=1, max_length=8)]
    preconditions: list[Annotated[str, Field(min_length=1, max_length=240)]]
    checks: Annotated[list[EvaluationCheck], Field(min_length=1, max_length=256)]
    eval_permissions: Permissions

    @model_validator(mode="after")
    def profile_is_closed(self) -> Self:
        if len(set(self.component_types)) != len(self.component_types):
            raise ValueError("component types must be unique")
        if len({item.check_id for item in self.checks}) != len(self.checks):
            raise ValueError("evaluation check ids must be unique")
        declared = set(self.component_types)
        if any(
            item.component_type is not None and item.component_type not in declared
            for item in self.checks
        ):
            raise ValueError("a type-specific check names an undeclared component type")
        return self


class EvalComponentCoordinate(BaseModel):
    """Exact component identity inside the evaluated setup graph."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    stable_id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+$")]
    passport_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    artifact_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    component_type: ComponentType


class SetupEvalPlan(BaseModel):
    """Content-addressed evaluation plan bound to exact setup coordinates."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    plan_id: Annotated[str, Field(pattern=r"^eval_plan_[0-9a-f]{24}$")]
    plan_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    profile: SetupEvalProfile
    setup_id: Annotated[str, Field(min_length=1)]
    setup_version: Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+$")]
    setup_passport_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    setup_artifact_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    harness_id: Annotated[str, Field(min_length=1)]
    harness_version: Annotated[str, Field(min_length=1)]
    provider_version: Annotated[str, Field(min_length=1)]
    runner_version: Annotated[str, Field(min_length=1)]
    components: Annotated[list[EvalComponentCoordinate], Field(min_length=1)]
    planned_at: Annotated[str, Field(min_length=1)]


class EvaluationCheckResult(BaseModel):
    """Observed result of one check without promotion of unavailable runners."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    check_id: Annotated[str, Field(min_length=1)]
    method: EvaluationMethod
    runner: Annotated[str, Field(min_length=1)]
    status: EvaluationStatus
    message: Annotated[str, Field(min_length=1, max_length=1000)]
    component_ids: list[str] = []


class SetupEvalResult(BaseModel):
    """Immutable local evaluation evidence for one exact plan."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    run_id: Annotated[str, Field(pattern=r"^eval_run_[0-9a-f]{24}$")]
    result_digest: Annotated[str, Field(pattern=DIGEST_PATTERN)]
    plan: SetupEvalPlan
    status: EvaluationStatus
    executed_at: Annotated[str, Field(min_length=1)]
    checks: Annotated[list[EvaluationCheckResult], Field(min_length=1)]
    immutable_published_bytes_changed: Literal[False] = False
    provider_permissions_used: Literal[False] = False

    @model_validator(mode="after")
    def aggregate_matches_checks(self) -> Self:
        statuses = {item.status for item in self.checks}
        expected: EvaluationStatus
        if "failed" in statuses:
            expected = "failed"
        elif "degraded" in statuses or "not_run" in statuses:
            expected = "degraded"
        else:
            expected = "passed"
        if self.status != expected:
            raise ValueError("evaluation result status disagrees with check results")
        return self
