"""Request correlation and trace surfacing (SPEC-017 REQ-1705).

Every request gets a fresh stable request_id. An inbound correlation header is
continued; the outbound request_id and correlation id are returned as headers,
and the active trace id is surfaced alongside them.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ai_stp_api.envelope import error_response
from ai_stp_api.observability import current_trace_id
from ai_stp_contracts.http import SCHEMA_VERSION, SCHEMA_VERSION_HEADER
from ai_stp_foundation.ids import new_id
from ai_stp_platform.logging import get_logger

REQUEST_ID_HEADER = "X-Request-Id"
CORRELATION_HEADER = "X-Correlation-Id"
TRACE_ID_HEADER = "X-Trace-Id"

_log = get_logger("correlation")


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Assign a request id, continue inbound correlation and surface the trace id.

    Also enforces the documented wire-major check: the client sends
    ``X-AI-STP-Schema-Version`` on every call and the contract states an
    unknown major "fails typed" — until now nothing read it, so a newer client
    got silent partial behavior instead of the refusal that names the problem.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = new_id("request")
        correlation_id = request.headers.get(CORRELATION_HEADER) or request_id
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id

        declared = request.headers.get(SCHEMA_VERSION_HEADER)
        if declared is not None:
            try:
                major = int(declared)
            except ValueError:
                major = SCHEMA_VERSION + 1
            if major < 1 or major > SCHEMA_VERSION:
                response = error_response(
                    request_id=request_id,
                    code="AI_STP_SCHEMA_UNSUPPORTED",
                    message=(
                        "the client speaks a newer contract version "
                        "than this deployment understands"
                    ),
                    retryable=False,
                    status_code=400,
                    details={
                        "found": declared[:32],
                        "supported": str(SCHEMA_VERSION),
                    },
                )
                response.headers[REQUEST_ID_HEADER] = request_id
                response.headers[CORRELATION_HEADER] = correlation_id
                return response

        try:
            response = await call_next(request)
        except Exception:
            # ExceptionMiddleware only sees route-raised errors: a fault inside
            # an inner middleware — or a second fault inside the error handlers
            # themselves — propagates through `call_next` and would reach the
            # server as a bare 500 with no correlation headers and no envelope.
            _log.exception(
                "unhandled_exception",
                request_id=request_id,
                correlation_id=correlation_id,
            )
            response = error_response(
                request_id=request_id,
                code="AI_STP_INTERNAL",
                message="internal error",
                retryable=False,
                status_code=500,
                details={},
            )

        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[CORRELATION_HEADER] = correlation_id
        trace_id = current_trace_id()
        if trace_id is not None:
            response.headers[TRACE_ID_HEADER] = trace_id
        return response
