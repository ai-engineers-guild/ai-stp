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

from ai_stp_api.observability import current_trace_id
from ai_stp_foundation.ids import new_id

REQUEST_ID_HEADER = "X-Request-Id"
CORRELATION_HEADER = "X-Correlation-Id"
TRACE_ID_HEADER = "X-Trace-Id"


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Assign a request id, continue inbound correlation and surface the trace id."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = new_id("request")
        correlation_id = request.headers.get(CORRELATION_HEADER) or request_id
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id

        response = await call_next(request)

        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[CORRELATION_HEADER] = correlation_id
        trace_id = current_trace_id()
        if trace_id is not None:
            response.headers[TRACE_ID_HEADER] = trace_id
        return response
