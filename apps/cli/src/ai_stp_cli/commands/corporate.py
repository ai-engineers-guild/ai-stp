"""`corporate assignment` commands — effective reads, distribution, planning.

#205 exposes the shared effective-assignment read; #206 exposes bulk
assign/revoke preview+apply and the per-target distribution state; #214 exposes
the deterministic install/update plan over the caller's context and reported
materialized state. All use the same generated contract the Web and CI consume
- the CLI never reimplements scope precedence, expansion, lifecycle derivation,
or plan classification locally.
"""

import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import closing
from typing import cast

from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import corporate, session
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import targets, versions
from ai_stp_cli.local.database import configured_path, open_readonly
from ai_stp_contracts.corporate import (
    CorporateAssignmentPlan,
    CorporateAssignmentPlanRequest,
    CorporateDistributionRequest,
    CorporateDistributionResult,
    CorporateDistributionStateList,
    CorporateDistributionStateQuery,
    CorporateEffectiveAssignment,
    CorporateEffectiveAssignmentQuery,
    CorporatePlanMaterializedItem,
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


def _materialized_option(parameters: Mapping[str, object]) -> list[CorporatePlanMaterializedItem]:
    """Explicit `<kind>:<stable_id>@<version>` entries supplied by the caller."""
    raw = parameters.get("materialized")
    # A repeatable option reaches the handler as Click's `multiple=True` tuple.
    entries: tuple[str, ...]
    if raw is None:
        entries = ()
    elif isinstance(raw, str):
        entries = (raw,)
    elif isinstance(raw, list | tuple):
        entries = tuple(str(item) for item in cast(Iterable[object], raw))
    else:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "materialized must be repeated strings")
    items: list[CorporatePlanMaterializedItem] = []
    for entry in entries:
        kind, separator, rest = entry.partition(":")
        stable_id, at, version = rest.partition("@")
        if not separator or not at or not stable_id or not version:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a materialized coordinate is written as <kind>:<stable_id>@<version>",
                details={"materialized": entry},
            )
        try:
            items.append(
                CorporatePlanMaterializedItem(
                    object_kind=kind,  # pyright: ignore[reportArgumentType]
                    stable_id=stable_id,
                    version=version,
                )
            )
        except ValueError as error:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a materialized coordinate is not a valid catalog identity",
                details={"materialized": entry},
            ) from error
    return items


def _target_materialized(
    connection: sqlite3.Connection, *, project_id: str, harness: str
) -> CorporatePlanMaterializedItem | None:
    """The last provider-verified setup on the (project, harness) target."""
    history = targets.verified(connection, project_id=project_id, harness_id=harness)
    if not history:
        return None
    last = history[-1]
    held = versions.held(connection, last.setup_stable_id, last.setup_version)
    return CorporatePlanMaterializedItem(
        object_kind="setup",
        stable_id=last.setup_stable_id,
        version=last.setup_version,
        passport_digest=None if held is None else held.passport_digest,
    )


def plan(parameters: Mapping[str, object]) -> Answer[CorporateAssignmentPlan]:
    """Evaluate the corporate install/update plan for the caller's context.

    Materialized state is reported, never probed: explicit `--materialized`
    entries plus, when `--local-project` names a linked local project, the last
    provider-verified setup on that (project, harness) target. The plan itself
    writes nothing; the returned exact coordinates feed `install plan`.
    """
    held = _session("corporate assignment plan")
    harness = _required(parameters, "harness")
    materialized = _materialized_option(parameters)
    local_project = _optional(parameters, "local-project")
    if local_project is not None:
        with closing(open_readonly(configured_path())) as connection:
            target_item = _target_materialized(
                connection, project_id=local_project, harness=harness
            )
        if target_item is not None:
            materialized.append(target_item)
    request = CorporateAssignmentPlanRequest(
        account_id=_optional(parameters, "account") or held.account_id,
        harness=harness,  # pyright: ignore[reportArgumentType]
        project_id=_optional(parameters, "project"),
        technology_id=_optional(parameters, "technology"),
        materialized=materialized,
    )
    return Answer(
        corporate.assignment_plan(
            endpoint(), held.access_token, _required(parameters, "organization"), request
        )
    )
