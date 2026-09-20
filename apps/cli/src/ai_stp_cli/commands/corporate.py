"""`corporate assignment` commands — effective reads and bulk distribution.

#205 exposes the shared effective-assignment read; #206 exposes bulk
assign/revoke preview+apply and the per-target distribution state. Both use the
same generated contract the Web and CI consume — the CLI never reimplements
scope precedence, expansion, or lifecycle derivation locally.
"""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import corporate, session
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.corporate import (
    CorporateDistributionRequest,
    CorporateDistributionResult,
    CorporateDistributionStateList,
    CorporateDistributionStateQuery,
    CorporateEffectiveAssignment,
    CorporateEffectiveAssignmentQuery,
)


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = str(parameters.get(name) or "")
    if not value:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option was not supplied",
            details={"option": f"--{name}"},
        )
    return value


def _optional(parameters: Mapping[str, object], name: str) -> str | None:
    return str(parameters.get(name) or "") or None


def _integer(parameters: Mapping[str, object], name: str, default: int) -> int:
    value = parameters.get(name)
    try:
        return default if value is None else int(str(value))
    except ValueError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option must be an integer",
            details={"option": f"--{name}"},
        ) from error


def _required_integer(parameters: Mapping[str, object], name: str) -> int:
    try:
        return int(_required(parameters, name))
    except ValueError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option must be an integer",
            details={"option": f"--{name}"},
        ) from error


def _distribution_preview(parameters: Mapping[str, object]) -> str:
    command = ["corporate", "assignment", "distribute"]
    for name in (
        "organization",
        "source",
        "action",
        "expected-revision",
        "authorization-revision",
        "idempotency-key",
    ):
        value = parameters.get(name)
        if value is not None:
            command.extend((f"--{name}", str(value)))
    command.extend(("--dry-run", "--json"))
    return " ".join(command)


def _session(purpose: str) -> session.Session:
    return cloud_auth.required(purpose)


def effective(parameters: Mapping[str, object]) -> Answer[CorporateEffectiveAssignment]:
    held = _session("effective corporate assignment")
    request = CorporateEffectiveAssignmentQuery(
        account_id=_required(parameters, "account"),
        object_kind=_required(parameters, "kind"),  # pyright: ignore[reportArgumentType]
        stable_id=_required(parameters, "id"),
        project_id=_optional(parameters, "project"),
        technology_id=_optional(parameters, "technology"),
        harness=_optional(parameters, "harness"),  # pyright: ignore[reportArgumentType]
    )
    return Answer(
        corporate.effective_assignment(
            endpoint(), held.access_token, _required(parameters, "organization"), request
        )
    )


def distribute(parameters: Mapping[str, object]) -> Answer[CorporateDistributionResult]:
    dry_run = parameters.get("dry-run") is True
    if not dry_run and parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "applying a bulk distribution requires explicit confirmation",
            details={"action": "corporate assignment distribute"},
            next_actions=[_distribution_preview(parameters)],
        )
    held = _session("corporate assignment distribution")
    request = CorporateDistributionRequest(
        source_assignment_id=_required(parameters, "source"),
        action=_required(parameters, "action"),  # pyright: ignore[reportArgumentType]
        dry_run=dry_run,
        expected_revision=_required_integer(parameters, "expected-revision"),
        authorization_revision=_required_integer(parameters, "authorization-revision"),
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    return Answer(
        corporate.distribute_assignment(
            endpoint(), held.access_token, _required(parameters, "organization"), request
        )
    )


def distribution(parameters: Mapping[str, object]) -> Answer[CorporateDistributionStateList]:
    held = _session("corporate assignment distribution state")
    request = CorporateDistributionStateQuery(
        source_assignment_id=_required(parameters, "source"),
        offset=_integer(parameters, "offset", 0),
        limit=_integer(parameters, "limit", 128),
    )
    return Answer(
        corporate.assignment_distribution(
            endpoint(), held.access_token, _required(parameters, "organization"), request
        )
    )
