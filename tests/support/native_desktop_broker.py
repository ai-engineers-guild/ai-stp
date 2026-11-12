"""A private bounded approval channel for installed native Desktop fixtures."""

from __future__ import annotations

import json
import queue
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from tests.support.native_pipe import Pipe

PREFIX = b"AI_STP_NATIVE_DESKTOP_FIXTURE_V1 "
PROTOCOL = "ai-stp-native-desktop-fixture/1"
MAX_REQUEST_BYTES = 4096
MAX_OUTPUT_BYTES = 2 * 1024 * 1024


def _approval(line: bytes, nonce: str, sequence: int) -> str:
    if len(line) > MAX_REQUEST_BYTES:
        raise ValueError("Native fixture request exceeded its bound")
    try:
        value = json.loads(line.removeprefix(PREFIX))
    except (ValueError, UnicodeError):
        raise ValueError("Native fixture request is not valid JSON") from None
    if not isinstance(value, dict):
        raise ValueError("Native fixture request must be an object")
    request = cast(dict[str, Any], value)
    if (
        set(request) != {"protocol", "nonce", "sequence", "action", "user_code"}
        or request["protocol"] != PROTOCOL
        or request["nonce"] != nonce
        or type(request["sequence"]) is not int
        or request["sequence"] != sequence
        or request["action"] != "approve_device"
        or not isinstance(request["user_code"], str)
        or not 1 <= len(request["user_code"]) <= 128
    ):
        raise ValueError("Native fixture request refused")
    return cast(str, request["user_code"])


def run_owner(
    arguments: list[str],
    *,
    environment: dict[str, str],
    errors: Path,
    nonce: str,
    approve: Callable[[str], None],
) -> int:
    """Approve one owned device flow; never publish child output or private values."""
    assert re.fullmatch(r"[a-f0-9]{64}", nonce)
    approved = 0
    output_bytes = 0
    with errors.open("xb") as error_stream:
        process = subprocess.Popen(
            arguments,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=error_stream,
        )
        pipe = Pipe(process)
        try:
            deadline = time.monotonic() + 600
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Native Desktop fixture exceeded its deadline")
                try:
                    record = pipe.messages.get(timeout=min(0.2, remaining))
                except queue.Empty:
                    if process.poll() is not None and not pipe.reader.is_alive():
                        break
                    continue
                if isinstance(record, EOFError):
                    break
                if isinstance(record, Exception):
                    raise ValueError("Native Desktop fixture output refused") from None
                output_bytes += len(record)
                if output_bytes > MAX_OUTPUT_BYTES:
                    raise ValueError("Native Desktop fixture output exceeded its bound")
                if not record.startswith(PREFIX):
                    continue
                if approved:
                    raise ValueError("Native fixture repeated device approval")
                code = _approval(record, nonce, 1)
                try:
                    approve(code)
                except Exception:
                    raise ValueError("Native fixture approval failed") from None
                response = {
                    "protocol": PROTOCOL,
                    "nonce": nonce,
                    "sequence": 1,
                    "approved": True,
                }
                pipe.input.write(json.dumps(response).encode() + b"\n")
                pipe.input.flush()
                approved += 1
            result = process.wait(timeout=15)
            if result != 0 or approved != 1:
                raise ValueError("Native Desktop owner did not complete its approval journey")
            return approved
        finally:
            pipe.close()
