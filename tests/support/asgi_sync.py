"""Synchronous transport that serves a real ASGI app on a dedicated loop.

The CLI's cloud layer is synchronous (`open_client` takes an
`httpx.BaseTransport`), and `httpx.ASGITransport` is async-only, so a real
FastAPI app could not be driven from CLI tests without either a subprocess or
this bridge. The bridge runs the app on an `anyio` blocking portal: lifespan
and every request execute on the same loop, which is what keeps asyncpg
connections and the app's `sessionmaker` consistent.

One server instance owns one portal for its whole lifetime. Request bodies are
read eagerly — every CLI call is a small JSON document — and responses are
collected likewise, so the exchange is a single `portal.call`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from types import TracebackType
from typing import Any, TypeVar

import anyio.from_thread
import httpx
from anyio.abc import BlockingPortal

_T = TypeVar("_T")


class SyncAsgiTransport(httpx.BaseTransport):
    """`httpx.BaseTransport` that answers requests by calling an ASGI app."""

    def __init__(self, portal: BlockingPortal, app: Any) -> None:
        self._portal = portal
        self._app = app

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self._portal.call(self._handle, request)

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        body = request.read()
        sent = False

        async def receive() -> dict[str, Any]:
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }

        status = 500
        headers: list[tuple[bytes, bytes]] = []
        chunks: list[bytes] = []

        async def send(message: dict[str, Any]) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers.extend(message.get("headers", []))
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": request.method,
            "scheme": request.url.scheme,
            "path": request.url.path,
            "raw_path": request.url.raw_path,
            "query_string": request.url.query,
            "root_path": "",
            # ASGI requires lowercased header names; httpx preserves the
            # caller's case, and Starlette compares bytes exactly, so a
            # title-cased `Authorization` is invisible to `request.headers`.
            "headers": [(k.lower(), v) for k, v in request.headers.raw],
            "client": ("127.0.0.1", 12345),
            "server": (request.url.host, request.url.port or 443),
        }
        await self._app(scope, receive, send)
        return httpx.Response(
            status,
            headers=httpx.Headers(headers),
            content=b"".join(chunks),
            request=request,
        )


class SyncAsgiServer:
    """Owns the portal, the app's lifespan, and the transport together."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self._app = app
        self._portal_cm: AbstractContextManager[BlockingPortal] | None = None
        self._portal: BlockingPortal | None = None
        self._lifespan: AbstractAsyncContextManager[Any] | None = None
        self.transport: SyncAsgiTransport | None = None

    def __enter__(self) -> SyncAsgiServer:
        portal_cm = anyio.from_thread.start_blocking_portal()
        self._portal_cm = portal_cm
        portal = self._portal = portal_cm.__enter__()
        router = getattr(self._app, "router", None)
        lifespan = getattr(router, "lifespan_context", None)
        if lifespan is not None:
            entered: AbstractAsyncContextManager[Any] = lifespan(self._app)
            self._lifespan = entered
            portal.call(entered.__aenter__)
        self.transport = SyncAsgiTransport(portal, self._app)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._portal is not None
        try:
            if self._lifespan is not None:
                self._portal.call(self._lifespan.__aexit__, exc_type, exc, tb)
        finally:
            assert self._portal_cm is not None
            self._portal_cm.__exit__(exc_type, exc, tb)

    def call(self, func: Callable[..., Awaitable[_T]], *args: Any) -> _T:
        """Run an async callable on the app's loop — for seeding via ORM."""
        assert self._portal is not None
        return self._portal.call(func, *args)
