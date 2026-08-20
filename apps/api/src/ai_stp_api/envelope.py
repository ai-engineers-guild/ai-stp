"""HTTP helpers for the shared error envelope (and rare legacy success wrap).

Success responses on the frozen `/v1` surface carry the **resource body** from
`packages/contracts` (see `docs/contracts/http-api.md` and SPEC-017 REQ-1704).
Errors use `ErrorEnvelope` / `CliError` so CLI and web share one failure wire.

`success_response` remains for narrow web/OAuth JSON paths that still wrap a
payload; new resource routes must return the model body directly, not this helper.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from fastapi.responses import JSONResponse
from pydantic import JsonValue

from ai_stp_foundation.envelope import CliError, ErrorEnvelope, SuccessEnvelope


def _json_object(value: Mapping[str, object] | None) -> dict[str, JsonValue]:
    """Narrow a plain mapping to the envelope's JSON value type.

    Pydantic validates and serialises the contents on construction, so the cast
    only satisfies the static type of the wire model.
    """
    return cast("dict[str, JsonValue]", dict(value or {}))


def success_response(
    *,
    request_id: str,
    data: Mapping[str, object] | None = None,
    operation_id: str | None = None,
    warnings: Sequence[str] | None = None,
    next_actions: Sequence[str] | None = None,
    status_code: int = 200,
) -> JSONResponse:
    """Build an HTTP response carrying a success envelope."""
    envelope = SuccessEnvelope(
        request_id=request_id,
        operation_id=operation_id,
        data=_json_object(data),
        warnings=list(warnings or []),
        next_actions=list(next_actions or []),
    )
    return JSONResponse(content=envelope.model_dump(mode="json"), status_code=status_code)


def error_response(
    *,
    request_id: str,
    code: str,
    message: str,
    retryable: bool,
    status_code: int,
    details: Mapping[str, object] | None = None,
    operation_id: str | None = None,
    next_actions: Sequence[str] | None = None,
) -> JSONResponse:
    """Build an HTTP response carrying an error envelope."""
    envelope = ErrorEnvelope(
        request_id=request_id,
        operation_id=operation_id,
        error=CliError(
            code=code,
            message=message,
            retryable=retryable,
            details=_json_object(details),
        ),
        next_actions=list(next_actions or []),
    )
    return JSONResponse(content=envelope.model_dump(mode="json"), status_code=status_code)
