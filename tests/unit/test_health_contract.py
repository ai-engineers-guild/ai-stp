"""Liveness and readiness payloads (issue #71, SPEC-010 REQ-1001)."""

import pytest
from pydantic import ValidationError

from ai_stp_contracts.health import (
    LivenessResponse,
    ReadinessChecks,
    ReadinessResponse,
)

PASSING = ReadinessChecks(database="pass", migrations="pass", object_storage="pass")


def test_liveness_states_only_that_the_process_answers() -> None:
    live = LivenessResponse()
    assert live.status == "alive"
    assert set(LivenessResponse.model_fields) == {"schema_version", "status"}


def test_liveness_leaks_no_deployment_detail() -> None:
    # An unauthenticated probe must not become reconnaissance.
    forbidden = {"version", "host", "hostname", "commit", "build", "environment"}
    assert forbidden.isdisjoint(LivenessResponse.model_fields)


def test_readiness_reports_the_closed_dependency_set() -> None:
    ready = ReadinessResponse(status="ready", checks=PASSING, checked_at="2026-08-05T00:00:00.000Z")
    assert ready.checks == PASSING
    assert set(ReadinessChecks.model_fields) == {"database", "migrations", "object_storage"}


def test_readiness_can_report_not_ready_before_migrations_apply() -> None:
    half_migrated = ReadinessChecks(database="pass", migrations="fail", object_storage="pass")
    response = ReadinessResponse(
        status="not_ready", checks=half_migrated, checked_at="2026-08-05T00:00:00.000Z"
    )
    assert response.status == "not_ready"


def test_a_check_has_no_unknown_third_state() -> None:
    # An unproven dependency is not ready; there is no "unknown" that could be
    # read as success.
    with pytest.raises(ValidationError):
        ReadinessChecks(database="unknown", migrations="pass", object_storage="pass")  # type: ignore[arg-type]


def test_readiness_rejects_a_non_canonical_timestamp() -> None:
    with pytest.raises(ValidationError):
        ReadinessResponse(status="ready", checks=PASSING, checked_at="2026-08-05T00:00:00Z")


def test_readiness_rejects_an_unknown_status() -> None:
    with pytest.raises(ValidationError):
        ReadinessResponse(
            status="degraded",  # type: ignore[arg-type]
            checks=PASSING,
            checked_at="2026-08-05T00:00:00.000Z",
        )


def test_ready_cannot_coexist_with_a_failing_check() -> None:
    # SPEC-010: readiness is not successful until migrations are applied and
    # every required dependency answers. Without this, a handler computing
    # status from a stale value advertises a half-migrated deployment as
    # serving, and probes that read only `status` route traffic to it.
    for broken in (
        ReadinessChecks(database="fail", migrations="pass", object_storage="pass"),
        ReadinessChecks(database="pass", migrations="fail", object_storage="pass"),
        ReadinessChecks(database="pass", migrations="pass", object_storage="fail"),
    ):
        with pytest.raises(ValidationError):
            ReadinessResponse(status="ready", checks=broken, checked_at="2026-08-05T00:00:00.000Z")


def test_not_ready_may_report_any_check_combination() -> None:
    # The implication runs one way only: not_ready with everything passing is a
    # legitimate transient state, not a contradiction.
    response = ReadinessResponse(
        status="not_ready", checks=PASSING, checked_at="2026-08-05T00:00:00.000Z"
    )
    assert response.status == "not_ready"


def test_readiness_rejects_an_impossible_moment() -> None:
    # Pattern-valid but not a real date; a consumer parsing it later would crash
    # after validation already reported success.
    with pytest.raises(ValidationError):
        ReadinessResponse(status="ready", checks=PASSING, checked_at="2026-13-40T25:61:61.999Z")


def test_an_additive_field_is_accepted_and_preserved() -> None:
    payload = {
        "status": "ready",
        "checks": PASSING.model_dump(),
        "checked_at": "2026-08-05T00:00:00.000Z",
        "region": "eu-central",
    }
    assert ReadinessResponse.model_validate(payload).model_dump()["region"] == "eu-central"
