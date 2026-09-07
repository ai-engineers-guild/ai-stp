"""Explicit owner-controlled distribution visibility; no passport rewriting."""

from collections.abc import Mapping
from typing import Literal, cast

from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud import client, login
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.private_access import VisibilityPlanCreateRequest, VisibilityPlanResponse
from ai_stp_contracts.publication import PublicationConfirmRequest


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = str(parameters.get(name) or "")
    if not value:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option was not supplied",
            details={"option": name},
        )
    return value


def plan(parameters: Mapping[str, object]) -> Answer[VisibilityPlanResponse]:
    held = cloud_auth.required("distribution visibility")
    kind, visibility = _required(parameters, "kind"), _required(parameters, "visibility")
    if kind not in {"component", "setup"} or visibility not in {"public", "private"}:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "invalid distribution visibility request")
    request = VisibilityPlanCreateRequest(
        object_kind=cast(Literal["component", "setup"], kind),
        stable_id=_required(parameters, "id"),
        version=_required(parameters, "version"),
        visibility=cast(Literal["public", "private"], visibility),
        device_id=held.device_id,
        idempotency_key=login.new_idempotency_key(),
    )
    where = endpoint()
    with client.open_client(where, access_token=held.access_token) as http:
        response = client.call(
            http,
            "POST",
            "/access/visibility/plans",
            VisibilityPlanResponse,
            body=request,
            attempts=where.max_attempts,
        )
    if (
        any(
            getattr(response, name) != getattr(request, name)
            for name in ("object_kind", "stable_id", "version", "visibility", "device_id")
        )
        or response.actor_id != held.account_id
    ):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the visibility plan does not match the requested owner effect",
        )
    return Answer(response)


def status(parameters: Mapping[str, object]) -> Answer[VisibilityPlanResponse]:
    held = cloud_auth.required("distribution visibility")
    where = endpoint()
    plan_id = _required(parameters, "plan-id")
    with client.open_client(where, access_token=held.access_token) as http:
        response = client.call(
            http,
            "GET",
            f"/access/visibility/plans/{plan_id}",
            VisibilityPlanResponse,
            attempts=where.max_attempts,
        )
    if response.plan_id != plan_id or response.actor_id != held.account_id:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the visibility plan does not match the requested owner effect",
        )
    return Answer(response)


def confirm(parameters: Mapping[str, object]) -> Answer[VisibilityPlanResponse]:
    plan_id = _required(parameters, "plan-id")
    plan_hash = _required(parameters, "plan-hash")
    if parameters.get("confirm") is not True:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "changing distribution visibility requires explicit confirmation",
        )
    current = status(parameters).payload
    held = cloud_auth.required("distribution visibility")
    if current.plan_hash != plan_hash or current.device_id != held.device_id:
        raise CliFailure("AI_STP_PRECONDITION_FAILED", "the visibility plan changed after review")
    if current.state == "applied":
        return Answer(current)
    if current.state != "planned":
        raise CliFailure("AI_STP_PRECONDITION_FAILED", "the visibility plan cannot be applied")
    where = endpoint()
    with client.open_client(where, access_token=held.access_token) as http:
        response = client.call(
            http,
            "POST",
            f"/access/visibility/plans/{plan_id}/confirm",
            VisibilityPlanResponse,
            body=PublicationConfirmRequest(
                plan_hash=plan_hash, confirmed=True, idempotency_key=login.new_idempotency_key()
            ),
            attempts=where.max_attempts,
        )
    if current.model_dump(exclude={"state"}) != response.model_dump(exclude={"state"}):
        raise CliFailure("AI_STP_PRECONDITION_FAILED", "the visibility plan changed after review")
    return Answer(response)
