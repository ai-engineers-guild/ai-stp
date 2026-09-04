"""Explicit, idempotent access grant commands for exact major lines."""

import os
from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import grants, session
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.grants import (
    CliGrantAccessView,
    CliGrantInvitationView,
    CliGrantListView,
    CliGrantRevokeView,
    DirectGrantCreateRequest,
    GrantAcceptRequest,
    GrantInvitationCreateRequest,
    GrantRevokeRequest,
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


def _major(parameters: Mapping[str, object]) -> int:
    try:
        return int(_required(parameters, "major"))
    except ValueError as error:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "--major must be an integer") from error


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


def _session(purpose: str) -> session.Session:
    return cloud_auth.required(purpose)


def _confirmed(parameters: Mapping[str, object], action: str) -> None:
    if parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "this action requires explicit confirmation",
            details={"action": action},
            next_actions=[f"{action} --confirm --json"],
        )


def invite(parameters: Mapping[str, object]) -> Answer[CliGrantInvitationView]:
    _confirmed(parameters, "grant invite")
    held = _session("grant invitation")
    request = GrantInvitationCreateRequest(
        object_kind=_required(parameters, "kind"),  # pyright: ignore[reportArgumentType]
        stable_id=_required(parameters, "id"),
        major=_major(parameters),
        recipient_email=_required(parameters, "email"),
        ttl_seconds=_integer(parameters, "ttl-seconds", 604_800),
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    result = grants.invite(endpoint(), held.access_token, request)
    return Answer(CliGrantInvitationView.model_validate(result.model_dump(mode="json")))


def direct(parameters: Mapping[str, object]) -> Answer[CliGrantAccessView]:
    _confirmed(parameters, "grant direct")
    held = _session("direct grant")
    request = DirectGrantCreateRequest(
        object_kind=_required(parameters, "kind"),  # pyright: ignore[reportArgumentType]
        stable_id=_required(parameters, "id"),
        major=_major(parameters),
        recipient_kind=_required(parameters, "recipient-kind"),  # pyright: ignore[reportArgumentType]
        recipient=_required(parameters, "recipient"),
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    result = grants.direct(endpoint(), held.access_token, request)
    return Answer(CliGrantAccessView.model_validate(result.model_dump(mode="json")))


def list_all(_parameters: Mapping[str, object]) -> Answer[CliGrantListView]:
    held = _session("grant listing")
    result = grants.list_all(endpoint(), held.access_token)
    return Answer(CliGrantListView.model_validate(result.model_dump(mode="json")))


def accept(parameters: Mapping[str, object]) -> Answer[CliGrantAccessView]:
    _confirmed(parameters, "grant accept")
    variable = _required(parameters, "token-env")
    token = os.environ.get(variable, "")
    if not token:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the invitation token environment variable is absent or empty",
            details={"variable": variable},
        )
    held = _session("grant acceptance")
    request = GrantAcceptRequest(
        token=token,
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    return Answer(
        CliGrantAccessView.model_validate(
            grants.accept(
                endpoint(), held.access_token, _required(parameters, "invitation-id"), request
            ).model_dump(mode="json")
        )
    )


def revoke_invitation(parameters: Mapping[str, object]) -> Answer[CliGrantRevokeView]:
    return _revoke(parameters, invitation=True)


def revoke(parameters: Mapping[str, object]) -> Answer[CliGrantRevokeView]:
    return _revoke(parameters, invitation=False)


def _revoke(parameters: Mapping[str, object], *, invitation: bool) -> Answer[CliGrantRevokeView]:
    action = "grant invitation revoke" if invitation else "grant revoke"
    _confirmed(parameters, action)
    held = _session("grant revocation")
    request = GrantRevokeRequest(
        reason=str(parameters.get("reason") or ""),
        idempotency_key=_required(parameters, "idempotency-key"),
    )
    identifier = _required(parameters, "invitation-id" if invitation else "grant-id")
    result = (
        grants.revoke_invitation(endpoint(), held.access_token, identifier, request)
        if invitation
        else grants.revoke_grant(endpoint(), held.access_token, identifier, request)
    )
    return Answer(CliGrantRevokeView.model_validate(result.model_dump(mode="json")))
