"""Liveness and readiness payloads (SPEC-010 REQ-1001, states section).

Liveness says only that the process answers. Readiness is the stricter claim
and stays ``not_ready`` until migrations are applied and every required
dependency answers, so a half-migrated deployment cannot advertise itself as
serving. Neither payload carries a version string, a host name, a path or a
dependency address: an unauthenticated probe must not become reconnaissance.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from ai_stp_contracts.http import Timestamp, open_wire_object

#: A check either demonstrably passes or it does not. There is no third
#: "unknown" value: an unproven dependency is not ready.
type CheckStatus = Literal["pass", "fail"]


class LivenessResponse(BaseModel):
    """The process is running and able to answer."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    status: Literal["alive"] = "alive"


class ReadinessChecks(BaseModel):
    """The closed set of dependencies readiness depends on.

    Closed on purpose: a new dependency arrives as an additional optional
    field, which keeps an older reader working inside the same major.
    """

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    database: CheckStatus
    migrations: CheckStatus
    object_storage: CheckStatus


class ReadinessResponse(BaseModel):
    """Whether the deployment may take traffic."""

    model_config = ConfigDict(extra="allow", frozen=True, json_schema_extra=open_wire_object)

    schema_version: Literal[1] = 1
    status: Literal["ready", "not_ready"]
    checks: ReadinessChecks
    checked_at: Timestamp

    @model_validator(mode="after")
    def _status_follows_the_checks(self) -> "ReadinessResponse":
        """`ready` may not coexist with a failing check.

        SPEC-010 states readiness is not successful until migrations are applied
        and every required dependency answers. Without this, a handler computing
        `status` from a stale value advertises a half-migrated deployment as
        serving, and every probe that reads only `status` — the field named for
        that purpose — routes traffic to it.
        """
        failed = sorted(
            name for name, result in self.checks.model_dump().items() if result == "fail"
        )
        if self.status == "ready" and failed:
            raise ValueError(f"status 'ready' contradicts failing checks: {', '.join(failed)}")
        return self
