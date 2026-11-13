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
FAILURE_PREFIX = b"AI_STP_NATIVE_DESKTOP_FAILURE_V1 "
STAGE_PREFIX = b"AI_STP_NATIVE_DESKTOP_STAGE_V1 "
INPUT_PREFIX = b"AI_STP_NATIVE_DESKTOP_INPUT_V1 "
OPTION_PREFIX = b"AI_STP_NATIVE_DESKTOP_OPTION_V1 "
ERRORS_PREFIX = b"AI_STP_NATIVE_DESKTOP_ERRORS_V1 "
_ERROR_CODE = (
    rb"(?:[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|(?:check|state|window|process|event):[a-z][a-z0-9_]{0,39})"
)
ERROR_CODES = re.compile(_ERROR_CODE + rb"(?:," + _ERROR_CODE + rb"){0,15}")
STAGES = frozenset(
    {
        b"owner",
        b"installed",
        b"personal",
        b"connection",
        b"profile_selector_absent",
        b"profile_selector_disabled",
        b"profile_selector_role",
        b"discovery_ipc",
        b"discovery_validation",
        b"discovery_not_found",
        b"discovery_precondition",
        b"discovery_conflict",
        b"discovery_unavailable",
        b"discovery_internal",
        b"discovery_no_provider",
        b"connection_reviewed",
        b"connection_saved",
        b"pending",
        b"approval",
        b"context_connection",
        b"organization",
        b"context",
        b"selection",
        b"restart",
        b"checkout_preview",
        b"checkout_request",
        b"checkout_confirmation",
        b"checkout_restart",
        b"checkout_reconciliation",
        b"checkout_binding",
        b"complete",
    }
)
PROTOCOL = "ai-stp-native-desktop-fixture/1"
MAX_REQUEST_BYTES = 4096
MAX_OUTPUT_BYTES = 2 * 1024 * 1024


def _option_diagnostic(payload: bytes) -> dict[str, Any]:
    """Accept only bounded native numeric codes and nullable capability flags."""
    refused = "Native fixture option diagnostic refused"
    if len(payload) > 1024:
        raise ValueError(refused)
    try:
        value = json.loads(payload)
    except (ValueError, UnicodeError):
        raise ValueError(refused) from None
    if not isinstance(value, dict):
        raise ValueError(refused)
    result = cast(dict[str, Any], value)
    if set(result) != {
        "hresult",
        "missing_pattern",
        "control_type",
        "enabled",
        "offscreen",
        "selection_item",
        "invoke",
        "selected_after",
    }:
        raise ValueError(refused)
    if (
        not isinstance(result["hresult"], str)
        or re.fullmatch(r"[0-9A-F]{8}", result["hresult"]) is None
        or type(result["missing_pattern"]) is not bool
    ):
        raise ValueError(refused)
    role = result["control_type"]
    if role is not None and (type(role) is not int or not 50000 <= role <= 50040):
        raise ValueError(refused)
    for key in ["enabled", "offscreen", "selection_item", "invoke", "selected_after"]:
        if result[key] is not None and type(result[key]) is not bool:
            raise ValueError(refused)
    return result


def _input_diagnostic(payload: bytes) -> dict[str, Any]:
    """Accept only input lengths, nullable native focus state and the focused control's
    UI Automation type, never field text or element names."""
    refused = "Native fixture input diagnostic refused"
    if len(payload) > 512:
        raise ValueError(refused)
    try:
        value = json.loads(payload)
    except (ValueError, UnicodeError):
        raise ValueError(refused) from None
    if not isinstance(value, dict):
        raise ValueError(refused)
    result = cast(dict[str, Any], value)
    if set(result) != {
        "expected_length",
        "observed_length",
        "unchanged",
        "automation_focused",
        "foreground_owned",
        "keyboard_focus_owned",
        "keyboard_focus_is_root",
        "pressed_modifiers",
        "element_available",
        "element_enabled",
        "focused_control_type",
    }:
        raise ValueError(refused)
    focused = result["focused_control_type"]
    if focused is not None and (
        type(focused) is not str or not re.fullmatch(r"ControlType\.[A-Za-z]{1,32}", focused)
    ):
        raise ValueError(refused)
    expected, observed, modifiers = (
        result["expected_length"],
        result["observed_length"],
        result["pressed_modifiers"],
    )
    if type(expected) is not int or not 1 <= expected <= 120:
        raise ValueError(refused)
    if observed is not None and (type(observed) is not int or not 0 <= observed <= 65536):
        raise ValueError(refused)
    if modifiers is not None and (type(modifiers) is not int or not 0 <= modifiers <= 31):
        raise ValueError(refused)
    for key in [
        "unchanged",
        "automation_focused",
        "foreground_owned",
        "keyboard_focus_owned",
        "keyboard_focus_is_root",
        "element_available",
        "element_enabled",
    ]:
        if result[key] is not None and type(result[key]) is not bool:
            raise ValueError(refused)
    return result


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
    return request["user_code"]


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
    stage = "startup"
    failure_line: int | None = None
    option_diagnostic: dict[str, Any] | None = None
    input_diagnostic: dict[str, Any] | None = None
    error_codes: str | None = None
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
                    raise ValueError(f"Native Desktop fixture output refused at {stage}") from None
                output_bytes += len(record)
                if output_bytes > MAX_OUTPUT_BYTES:
                    raise ValueError("Native Desktop fixture output exceeded its bound")
                if record.startswith(INPUT_PREFIX):
                    if input_diagnostic is not None:
                        raise ValueError("Native fixture input diagnostic repeated")
                    input_diagnostic = _input_diagnostic(record.removeprefix(INPUT_PREFIX))
                    continue
                if record.startswith(OPTION_PREFIX):
                    if option_diagnostic is not None:
                        raise ValueError("Native fixture option diagnostic repeated")
                    option_diagnostic = _option_diagnostic(record.removeprefix(OPTION_PREFIX))
                    continue
                if record.startswith(ERRORS_PREFIX):
                    codes = record.removeprefix(ERRORS_PREFIX).strip()
                    if error_codes is not None or ERROR_CODES.fullmatch(codes) is None:
                        raise ValueError("Native fixture error codes refused")
                    error_codes = codes.decode("ascii")
                    continue
                if record.startswith(FAILURE_PREFIX):
                    location = record.removeprefix(FAILURE_PREFIX).strip()
                    if failure_line is not None or re.fullmatch(rb"[0-9]{1,5}", location) is None:
                        raise ValueError("Native fixture failure location refused")
                    failure_line = int(location)
                    if failure_line > 10000:
                        raise ValueError("Native fixture failure location exceeded its bound")
                    continue
                if record.startswith(STAGE_PREFIX):
                    name = record.removeprefix(STAGE_PREFIX).strip()
                    if name not in STAGES:
                        raise ValueError("Native fixture checkpoint refused")
                    stage = name.decode("ascii")
                    continue
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
            if (
                result != 0
                or approved != 1
                or failure_line is not None
                or option_diagnostic is not None
                or input_diagnostic is not None
                or error_codes is not None
            ):
                details = (
                    "; option diagnostic=" + json.dumps(option_diagnostic, sort_keys=True)
                    if option_diagnostic is not None
                    else ""
                )
                if input_diagnostic is not None:
                    details += "; input diagnostic=" + json.dumps(input_diagnostic, sort_keys=True)
                if error_codes is not None:
                    details += "; visible error codes=" + error_codes
                raise ValueError(
                    f"Native Desktop owner did not complete its approval journey at {stage}; "
                    f"controller line {failure_line}{details}"
                )
            return approved
        finally:
            pipe.close()
