"""Typed authenticated publication-plan transport."""

import json
import time
from collections.abc import Callable
from typing import cast
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from ai_stp_cli.cloud.client import (
    BACKOFF_SECONDS,
    NEVER_RETRIED,
    RETRYABLE_STATUSES,
    Endpoint,
    call,
    failure_from,
    open_client,
)
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.http import API_BASE_PATH, REQUEST_ID_HEADER, SCHEMA_VERSION
from ai_stp_contracts.publication import (
    PublicationConfirmRequest,
    PublicationPlanCreateRequest,
    PublicationPlanResponse,
)


def create(
    endpoint: Endpoint, access_token: str, request: PublicationPlanCreateRequest
) -> PublicationPlanResponse:
    with open_client(endpoint, access_token=access_token) as client:
        response = call(
            client,
            "POST",
            "/publications/plans",
            PublicationPlanResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )
    if (
        response.visibility != request.visibility
        or response.object_kind != request.object_kind
        or response.stable_id != request.stable_id
        or response.version != request.version
        or response.content_digest != request.content_digest
        or response.device_id != request.device_id
    ):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the platform did not bind the requested distribution identity and visibility",
        )
    return response


def require_same_plan(expected: PublicationPlanResponse, observed: PublicationPlanResponse) -> None:
    """State may progress, but approval coordinates and exposure cannot change."""
    fields = (
        "plan_id",
        "plan_hash",
        "visibility",
        "object_kind",
        "stable_id",
        "version",
        "content_digest",
        "actor_id",
        "device_id",
    )
    if any(getattr(expected, name) != getattr(observed, name) for name in fields):
        raise CliFailure("AI_STP_PRECONDITION_FAILED", "the distribution plan changed after review")


def status(endpoint: Endpoint, access_token: str, plan_id: str) -> PublicationPlanResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/publications/plans/{plan_id}",
            PublicationPlanResponse,
            attempts=endpoint.max_attempts,
        )


def confirm(
    endpoint: Endpoint,
    access_token: str,
    plan_id: str,
    request: PublicationConfirmRequest,
) -> PublicationPlanResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/publications/plans/{plan_id}/confirm",
            PublicationPlanResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )


def bind(
    endpoint: Endpoint,
    access_token: str,
    plan_id: str,
    payload: bytes,
    *,
    pause: Callable[[float], None] = time.sleep,
) -> PublicationPlanResponse:
    """PUT exact artifact bytes to one plan. Digest and size come from the plan."""
    return _bind_payload(
        endpoint,
        access_token,
        f"{API_BASE_PATH}/publications/plans/{plan_id}/artifact",
        payload,
        pause=pause,
    )


def bind_projection(
    endpoint: Endpoint,
    access_token: str,
    plan_id: str,
    projection_digest: str,
    payload: bytes,
    *,
    pause: Callable[[float], None] = time.sleep,
) -> PublicationPlanResponse:
    """PUT one declared exact projection artifact to a plan."""
    encoded_digest = quote(projection_digest, safe="")
    return _bind_payload(
        endpoint,
        access_token,
        f"{API_BASE_PATH}/publications/plans/{plan_id}/artifacts/{encoded_digest}",
        payload,
        pause=pause,
    )


def _bind_payload(
    endpoint: Endpoint,
    access_token: str,
    path: str,
    payload: bytes,
    *,
    pause: Callable[[float], None],
) -> PublicationPlanResponse:
    with open_client(endpoint, access_token=access_token) as client:
        total = max(1, endpoint.max_attempts)
        delay = BACKOFF_SECONDS
        last: CliFailure | None = None
        for attempt in range(1, total + 1):
            response: httpx.Response | None = None
            try:
                response = client.request(
                    "PUT",
                    path,
                    content=payload,
                    headers={"Content-Type": "application/octet-stream"},
                )
            except httpx.HTTPError as error:
                last = CliFailure(
                    "AI_STP_DEPENDENCY_UNAVAILABLE",
                    "the platform could not be reached",
                    retryable=True,
                    details={"exception": type(error).__name__},
                    next_actions=["doctor --json"],
                )
            else:
                if response.status_code < 400:
                    return _decode_plan(response)
                last = failure_from(response)
                if last.code in NEVER_RETRIED or response.status_code not in RETRYABLE_STATUSES:
                    raise last
            if attempt >= total:
                break
            pause(_retry_after(response) or delay)
            delay *= 2
        assert last is not None
        raise last


def _decode_plan(response: httpx.Response) -> PublicationPlanResponse:
    try:
        document: object = json.loads(response.text)
    except ValueError as error:
        raise _malformed_plan(response, error) from error
    reported = (
        cast(dict[str, object], document).get("schema_version")
        if isinstance(document, dict)
        else None
    )
    if isinstance(reported, int) and not isinstance(reported, bool) and reported > SCHEMA_VERSION:
        raise CliFailure(
            "AI_STP_SCHEMA_UNSUPPORTED",
            "the platform answered with a newer contract version than this build understands",
            details={
                "found": str(reported),
                "supported": str(SCHEMA_VERSION),
                "request_id": response.headers.get(REQUEST_ID_HEADER, ""),
            },
            next_actions=["version --json"],
        )
    try:
        return PublicationPlanResponse.model_validate(document)
    except ValidationError as error:
        raise _malformed_plan(response, error) from error


def _retry_after(response: httpx.Response | None) -> float | None:
    if response is None:
        return None
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return min(max(float(raw), 0.0), 60.0)
    except ValueError:
        return None


def _malformed_plan(response: httpx.Response, error: BaseException) -> CliFailure:
    return CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "the platform answered with a body that does not match the published contract",
        details={
            "status": str(response.status_code),
            "exception": type(error).__name__,
            "request_id": response.headers.get(REQUEST_ID_HEADER, ""),
        },
    )
