"""Lifecycle for the on-demand loopback API used by local Web mode."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import secrets
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import Request

from ai_stp_api.errors import ApiError, ErrorCategory

LOCAL_SESSION_HEADER = "X-AI-STP-Local-Session"
LOCAL_CSRF_HEADER = "X-AI-STP-Local-CSRF"
LOCAL_SESSION_TTL = timedelta(hours=1)
_STARTUP_TIMEOUT = 10.0


@dataclass(frozen=True)
class LocalSession:
    token: str
    csrf_token: str
    expires_at: datetime
    api_base_url: str


@dataclass
class _LocalProcess:
    process: asyncio.subprocess.Process
    session: LocalSession


def _require_loopback(request: Request) -> None:
    host = request.client.host if request.client is not None else None
    try:
        allowed = host is not None and ipaddress.ip_address(host).is_loopback
    except ValueError:
        allowed = False
    if not allowed:
        raise ApiError(ErrorCategory.PERMISSION, "local session requires a loopback client")


async def _stop_process(entry: _LocalProcess) -> None:
    if entry.process.returncode is None:
        if entry.process.stdin is not None:
            entry.process.stdin.close()
        try:
            await asyncio.wait_for(entry.process.wait(), timeout=2)
        except TimeoutError:
            entry.process.kill()
            await entry.process.wait()


async def start(request: Request) -> LocalSession:
    """Launch one disposable loopback process and create its session there."""
    _require_loopback(request)
    processes: dict[str, _LocalProcess] = request.app.state.local_processes
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-B",
        "-m",
        "ai_stp_api.local_process",
        env={
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "PYTHONPATH"}
        },
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        assert process.stdout is not None
        payload = json.loads(await asyncio.wait_for(process.stdout.readline(), _STARTUP_TIMEOUT))
        base_url = payload["api_base_url"]
        async with httpx.AsyncClient(base_url=base_url, timeout=0.5) as client:
            deadline = asyncio.get_running_loop().time() + _STARTUP_TIMEOUT
            while True:
                if process.returncode is not None:
                    raise ApiError(ErrorCategory.DEPENDENCY, "local API process stopped")
                try:
                    response = await client.get(
                        "/v1/context", headers={LOCAL_SESSION_HEADER: payload["session"]}
                    )
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if asyncio.get_running_loop().time() >= deadline:
                    raise ApiError(ErrorCategory.DEPENDENCY, "local API process did not start")
                await asyncio.sleep(0.05)
        session = LocalSession(
            token=str(payload["session"]),
            csrf_token=str(payload["csrf"]),
            expires_at=datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00")),
            api_base_url=base_url,
        )
    except BaseException:
        await _stop_process(
            _LocalProcess(
                process=process,
                session=LocalSession("", "", datetime.now(UTC), ""),
            )
        )
        raise
    processes[session.token] = _LocalProcess(process=process, session=session)
    return session


def require(request: Request, *, mutation: bool = False) -> LocalSession:
    """Validate the parent-side handle; the child is the data-plane authority."""
    _require_loopback(request)
    token = request.headers.get(LOCAL_SESSION_HEADER, "")
    entry = request.app.state.local_processes.get(token)
    if entry is None or entry.session.expires_at <= datetime.now(UTC):
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "local session required")
    if mutation and not secrets.compare_digest(
        entry.session.csrf_token, request.headers.get(LOCAL_CSRF_HEADER, "")
    ):
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "local csrf validation failed")
    return entry.session


async def stop(request: Request) -> None:
    """End the child session and terminate its process; no durable state is kept."""
    session = require(request, mutation=True)
    processes: dict[str, _LocalProcess] = request.app.state.local_processes
    entry = processes.pop(session.token)
    try:
        async with httpx.AsyncClient(base_url=session.api_base_url, timeout=1.0) as client:
            await client.delete(
                "/v1/local/session",
                headers={
                    LOCAL_SESSION_HEADER: session.token,
                    LOCAL_CSRF_HEADER: session.csrf_token,
                },
            )
    except httpx.HTTPError:
        pass
    await _stop_process(entry)


async def close_all(app: Any) -> None:
    """Terminate every child during API shutdown."""
    processes = app.state.local_processes
    entries = tuple(processes.values())
    processes.clear()
    for entry in entries:
        await _stop_process(entry)
