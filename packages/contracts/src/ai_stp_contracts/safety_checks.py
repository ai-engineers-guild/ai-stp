"""Public wire shapes for safety check audit and catalog percent (#270)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_stp_contracts.http import open_wire_object

type CheckResult = Literal[
    "passed", "warning", "failed", "degraded", "not_run", "not_applicable", "skipped", "running"
]
# incomplete: optional/external engines planned but not_run (honest coverage).
type ChecksStatus = Literal["pending", "available", "empty", "incomplete"]
type FindingSeverity = Literal["info", "low", "medium", "high", "critical"]


class SafetyFindingSummary(BaseModel):
    """Bounded public identifiers for findings; never scanned content."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    count: Annotated[int, Field(ge=1)]
    severity_max: FindingSeverity
    rule_ids: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=128)]], Field(max_length=16)
    ] = Field(default_factory=list)
    paths: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=240)]], Field(max_length=16)
    ] = Field(default_factory=list)
    truncated: bool = False


class SafetyCheckEntry(BaseModel):
    """One check line on an audit list."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    check_id: Annotated[str, Field(min_length=1, max_length=64)]
    result: CheckResult
    mandatory: bool = True
    source: Annotated[str, Field(min_length=1, max_length=64)] = "platform_safety_scan"
    family: Annotated[str, Field(max_length=64)] = ""
    reason: Annotated[str, Field(max_length=200)] | None = None
    finding_summary: SafetyFindingSummary | None = None


class SafetyChecksSummary(BaseModel):
    """Card/detail projection for checks percent and status."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    status: ChecksStatus
    checks_passed_percent: Annotated[int, Field(ge=0, le=100)] | None = None
    coverage_complete: bool = True
    passed: Annotated[int, Field(ge=0)] = 0
    failed: Annotated[int, Field(ge=0)] = 0
    warning: Annotated[int, Field(ge=0)] = 0
    not_run: Annotated[int, Field(ge=0)] = 0
    total_countable: Annotated[int, Field(ge=0)] = 0
    checks: Annotated[list[SafetyCheckEntry], Field(max_length=128)] = Field(
        default_factory=list[SafetyCheckEntry]
    )
