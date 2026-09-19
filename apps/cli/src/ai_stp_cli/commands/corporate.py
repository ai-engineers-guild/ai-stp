"""`corporate assignment effective` — the winning assignment for one employee and line.

#205 exposes the shared effective-assignment read through the command surface so
operators can inspect the deterministic winner and resolved coordinates. The
install/update planning that consumes the same transport is #214.
"""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import corporate, session
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.corporate import (
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
