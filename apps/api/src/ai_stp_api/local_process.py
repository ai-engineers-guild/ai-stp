"""Disposable local API: no database, account, cloud settings or durable session."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import secrets
import socket
import sys
import threading
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response

from ai_stp_api.local_session import (
    LOCAL_CSRF_HEADER,
    LOCAL_SESSION_HEADER,
    LOCAL_SESSION_TTL,
    LocalSession,
)
from ai_stp_api.slices.context import service
from ai_stp_contracts.context import ActiveContext
from ai_stp_foundation.timestamps import format_timestamp


def create_local_app(session: LocalSession, shutdown: Callable[[], None]) -> FastAPI:
    app = FastAPI(title="ai-stp local loopback API")

    async def context() -> dict[str, object]:
        projection = service.projection_for(mode="local", organization_id=None)
        return ActiveContext(
            mode="local", organization_id=None, capabilities=projection
        ).model_dump(mode="json")

    async def stop_session() -> dict[str, bool]:
        asyncio.get_running_loop().call_later(0.05, shutdown)
        return {"ok": True}

    async def protect(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        host = request.client.host if request.client is not None else ""
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        authenticated = secrets.compare_digest(
            session.token, request.headers.get(LOCAL_SESSION_HEADER, "")
        )
        mutation = request.method not in {"GET", "HEAD", "OPTIONS"}
        csrf_valid = secrets.compare_digest(
            session.csrf_token, request.headers.get(LOCAL_CSRF_HEADER, "")
        )
        if not loopback or not authenticated or session.expires_at <= datetime.now(UTC):
            return JSONResponse({"error": "local session required"}, status_code=401)
        if mutation and not csrf_valid:
            return JSONResponse({"error": "local csrf validation failed"}, status_code=403)
        if request.headers.get("X-AI-STP-Organization-Id"):
            return JSONResponse(
                {"error": "local context cannot name an organization"}, status_code=400
            )
        response = await call_next(request)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    app.add_api_route("/v1/context", context, methods=["GET"])
    app.add_api_route("/v1/local/session", stop_session, methods=["DELETE"])
    app.middleware("http")(protect)
    return app


def main() -> None:
    # Bind once: the OS selects a free port without a probe/rebind race.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        session = LocalSession(
            token=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            expires_at=datetime.now(UTC) + LOCAL_SESSION_TTL,
            api_base_url=f"http://127.0.0.1:{listener.getsockname()[1]}",
        )

        def shutdown() -> None:
            server.should_exit = True

        server = uvicorn.Server(
            uvicorn.Config(
                create_local_app(session, shutdown),
                log_config=None,
                access_log=False,
            )
        )

        def parent_closed() -> None:
            while os.read(sys.stdin.fileno(), 1):
                pass
            shutdown()

        # The owning Web/API process holds stdin open. An abrupt owner exit
        # closes the pipe; expiry also bounds abandoned browser sessions.
        threading.Thread(target=parent_closed, daemon=True).start()
        expiry = threading.Timer(LOCAL_SESSION_TTL.total_seconds(), shutdown)
        expiry.daemon = True
        expiry.start()
        print(
            json.dumps(
                {
                    "session": session.token,
                    "csrf": session.csrf_token,
                    "expires_at": format_timestamp(session.expires_at),
                    "api_base_url": session.api_base_url,
                }
            ),
            flush=True,
        )
        try:
            server.run(sockets=[listener])
        finally:
            expiry.cancel()


if __name__ == "__main__":
    main()
