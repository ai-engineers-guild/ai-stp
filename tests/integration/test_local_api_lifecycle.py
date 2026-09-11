"""A real child process must need no cloud and leave no resident process/state."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import pytest


@pytest.mark.parametrize("end", ["csrf_stop", "owner_pipe_closed"])
async def test_local_api_lifecycle_without_remote_network(tmp_path: Path, end: str) -> None:
    # The child is denied every non-loopback connection, including accidental
    # database/cloud calls. Run from an empty directory with no account settings.
    bootstrap = """
import ipaddress, runpy, sys
def network_guard(event, args):
    if event in ('socket.connect', 'socket.bind'):
        address = args[1]
        if not isinstance(address, tuple) or not ipaddress.ip_address(address[0]).is_loopback:
            raise RuntimeError('non-loopback network disabled')
sys.addaudithook(network_guard)
runpy.run_module('ai_stp_api.local_process', run_name='__main__')
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-B",
        "-c",
        bootstrap,
        cwd=tmp_path,
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
        assert process.stdout is not None and process.stdin is not None
        raw = await asyncio.wait_for(process.stdout.readline(), timeout=30)
        session = json.loads(raw)
        async with httpx.AsyncClient(
            base_url=session["api_base_url"], timeout=0.5, trust_env=False
        ) as client:
            for _ in range(100):
                try:
                    context = await client.get(
                        "/v1/context",
                        headers={
                            "X-AI-STP-Local-Session": session["session"],
                        },
                    )
                    break
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    await asyncio.sleep(0.05)
            else:
                pytest.fail("local process did not accept requests")
            assert context.status_code == 200 and context.json()["mode"] == "local"
            assert process.pid != os.getpid() and process.returncode is None
            denied = await client.delete(
                "/v1/local/session",
                headers={
                    "X-AI-STP-Local-Session": session["session"],
                    "X-AI-STP-Local-CSRF": "wrong",
                },
            )
            assert denied.status_code == 403 and process.returncode is None
            if end == "csrf_stop":
                stopped = await client.delete(
                    "/v1/local/session",
                    headers={
                        "X-AI-STP-Local-Session": session["session"],
                        "X-AI-STP-Local-CSRF": session["csrf"],
                    },
                )
                assert stopped.status_code == 200
            else:
                process.stdin.close()
            assert await asyncio.wait_for(process.wait(), timeout=5) == 0
            with pytest.raises((httpx.ConnectError, httpx.ConnectTimeout)):
                await client.get("/v1/context")
        assert list(tmp_path.iterdir()) == []
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
