"""Bounded in-memory request limiter for the single-node MVP (SPEC-010 REQ-1015)."""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from ipaddress import ip_address
from time import monotonic

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ai_stp_api.envelope import error_response
from ai_stp_api.errors import CATEGORY_CODE, CATEGORY_STATUS, ErrorCategory
from ai_stp_foundation.ids import new_id

OVERALL_WINDOW_KEY = "overall"
UNKNOWN_PEER = "unknown"

#: The client address the edge proxy states. `deploy/nginx/ai-stp.conf.template`
#: sets it with `proxy_set_header`, which replaces whatever the client sent, so a
#: visitor cannot choose the value that describes them.
CLIENT_ADDRESS_HEADER = "x-ai-stp-client-ip"


def client_key(request: Request) -> str:
    """Name the caller a per-address budget should be charged to.

    The transport peer alone was the whole key until now, and behind a proxy that
    is the proxy: every anonymous reader shared one bucket, so one busy caller
    rate-limited everyone and a 429 said nothing about the caller who got it.
    `ADR-0128` recorded that as the cost of having no trusted address, which was
    true while nothing stated one.

    The edge states one now. It is read only when it parses as an IP address:
    that keeps a malformed or invented value from opening a key of its own
    choosing, and an unparseable one falls back rather than failing, because a
    limiter that refuses traffic it cannot classify is a worse failure than a
    limiter that charges it to the peer.

    Reaching the API without passing the proxy means reaching a loopback port on
    the deployment host, which is not a position this defends against, and in
    local development nothing sets the header and the peer is the caller anyway.
    """
    stated = request.headers.get(CLIENT_ADDRESS_HEADER, "").strip()
    if stated:
        try:
            return str(ip_address(stated))
        except ValueError:
            pass
    return request.client.host if request.client is not None else UNKNOWN_PEER


class SlidingWindowLimiter:
    """Keep a bounded request history per key without a shared overflow bucket."""

    def __init__(self, *, maximum: int, window_seconds: int, max_keys: int) -> None:
        self.maximum = maximum
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._entries: OrderedDict[str, deque[float]] = OrderedDict()

    def would_allow(self, key: str, *, now: float | None = None) -> bool:
        """Return whether ``key`` has budget left without recording the request."""
        if self.maximum == 0:
            return True
        moment = monotonic() if now is None else now
        threshold = moment - self.window_seconds
        entries = self._entries.get(key)
        if not entries:
            return True
        live = 0
        for stamp in entries:
            if stamp > threshold:
                live += 1
        return live < self.maximum

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


class HttpRateGate:
    """Two independent sliding windows: process-wide overall and per transport peer."""

    def __init__(
        self,
        *,
        overall: SlidingWindowLimiter,
        per_peer: SlidingWindowLimiter,
    ) -> None:
        self.overall = overall
        self.per_peer = per_peer
        self.retry_after_seconds = overall.window_seconds

    def allow(self, origin: str, *, now: float | None = None) -> bool:
        """Admit only when both windows have budget; a rejection records neither."""
        if not self.overall.would_allow(OVERALL_WINDOW_KEY, now=now):
            self.retry_after_seconds = self.overall.window_seconds
            return False
        if not self.per_peer.would_allow(origin, now=now):
            self.retry_after_seconds = self.per_peer.window_seconds
            return False
        self.overall.allow(OVERALL_WINDOW_KEY, now=now)
        self.per_peer.allow(origin, now=now)
        return True


def build_http_rate_gate(
    *,
    overall_requests: int,
    overall_window_seconds: int,
    ip_requests: int,
    ip_window_seconds: int,
    max_keys: int,
) -> HttpRateGate:
    """Compose the two in-process windows the API factory installs."""
    return HttpRateGate(
        overall=SlidingWindowLimiter(
            maximum=overall_requests,
            window_seconds=overall_window_seconds,
            max_keys=1,
        ),
        per_peer=SlidingWindowLimiter(
            maximum=ip_requests,
            window_seconds=ip_window_seconds,
            max_keys=max_keys,
        ),
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject excessive requests before a route performs application work."""

    def __init__(self, app: object, *, gate: HttpRateGate) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.gate = gate

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        origin = client_key(request)
        if self.gate.allow(origin):
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
        response.headers["Retry-After"] = str(self.gate.retry_after_seconds)
        return response
