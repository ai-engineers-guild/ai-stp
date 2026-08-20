"""Bounded in-memory request limiter for the single-node MVP (SPEC-010 REQ-1015)."""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from time import monotonic

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

from ai_stp_api.envelope import error_response
from ai_stp_api.errors import CATEGORY_CODE, CATEGORY_STATUS, ErrorCategory
from ai_stp_foundation.ids import new_id

_UNMATCHED_ROUTE = "unmatched"


class SlidingWindowLimiter:
    """Keep a bounded request history per key without a shared overflow bucket."""

    def __init__(self, *, maximum: int, window_seconds: int, max_keys: int) -> None:
        self.maximum = maximum
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._entries: OrderedDict[str, deque[float]] = OrderedDict()

    def allow(self, key: str, *, now: float | None = None) -> bool:
        """Return whether ``key`` may proceed and record an accepted request."""
        if self.maximum == 0:
            return True
        moment = monotonic() if now is None else now
        threshold = moment - self.window_seconds
        self._drop_idle(threshold)
        if key not in self._entries and len(self._entries) >= self.max_keys:
            self._entries.popitem(last=False)
        entries = self._entries.setdefault(key, deque())
        while entries and entries[0] <= threshold:
            entries.popleft()
        self._entries.move_to_end(key)
        if len(entries) >= self.maximum:
            return False
        entries.append(moment)
        return True

    def slot_count(self, *, now: float | None = None) -> int:
        """Return occupied keys after dropping those whose window is empty."""
        moment = monotonic() if now is None else now
        self._drop_idle(moment - self.window_seconds)
        return len(self._entries)

    def holds(self, key: str, *, now: float | None = None) -> bool:
        """Return whether ``key`` still occupies a slot at ``now``."""
        moment = monotonic() if now is None else now
        self._drop_idle(moment - self.window_seconds)
        return key in self._entries

    def _drop_idle(self, threshold: float) -> None:
        idle = [
            key for key, entries in self._entries.items() if not entries or entries[-1] <= threshold
        ]
        for key in idle:
            del self._entries[key]


def route_template_of(request: Request) -> str:
    """Return the matched route template, or a single unmatched sentinel."""
    attached = request.scope.get("route")
    attached_path = getattr(attached, "path", None)
    if isinstance(attached_path, str) and attached_path:
        return attached_path
    router = getattr(request.app, "router", None)
    routes = getattr(router, "routes", None) if router is not None else None
    if routes is None:
        return _UNMATCHED_ROUTE
    for candidate in routes:
        matches = getattr(candidate, "matches", None)
        if matches is None:
            continue
        match, _child = matches(request.scope)
        if match == Match.FULL:
            template = getattr(candidate, "path", None)
            if isinstance(template, str) and template:
                return template
    return _UNMATCHED_ROUTE


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject excessive requests before a route performs application work."""

    def __init__(self, app: object, *, limiter: SlidingWindowLimiter) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.limiter = limiter

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # ``Request.client`` is transport-derived. Forwarded headers are deliberately
        # ignored until a separately reviewed trusted-proxy policy exists.
        origin = request.client.host if request.client is not None else "unknown"
        key = f"{request.method}:{route_template_of(request)}:{origin}"
        if self.limiter.allow(key):
            return await call_next(request)
        request_id = getattr(request.state, "request_id", "") or new_id("request")
        response = error_response(
            request_id=request_id,
            code=CATEGORY_CODE[ErrorCategory.RATE_LIMITED],
            message="request rate limit exceeded",
            retryable=True,
            status_code=int(CATEGORY_STATUS[ErrorCategory.RATE_LIMITED]),
            details={},
        )
        response.headers["Retry-After"] = str(self.limiter.window_seconds)
        return response
