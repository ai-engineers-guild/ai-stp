"""Actual child-process approval transport rejects malformed or foreign requests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from tests.support.native_desktop_broker import run_owner

CHILD = r"""
import json,os,pathlib,sys
request={
 "protocol":"ai-stp-native-desktop-fixture/1",
 "nonce":sys.argv[1],
 "sequence":1,
 "action":"approve_device",
 "user_code":"SYNTHETIC-CODE",
}
case=sys.argv[2]
if case=="nonce":request["nonce"]="b"*64
if case=="sequence":request["sequence"]=2
if case=="action":request["action"]="execute"
if case=="extra":request["command"]="unused"
if case=="oversize":request["user_code"]="X"*5000
print("private fixture diagnostic",flush=True)
print("AI_STP_NATIVE_DESKTOP_STAGE_V1 approval",flush=True)
print("AI_STP_NATIVE_DESKTOP_FIXTURE_V1 "+json.dumps(request),flush=True)
response=sys.stdin.readline()
if case in {"valid","exit"}:
 result=json.loads(response)
 expected={
  "protocol":request["protocol"],"nonce":request["nonce"],
  "sequence":1,"approved":True,
 }
 assert result==expected
else:
 assert response==""
pathlib.Path(sys.argv[3]).write_text("completed")
if case=="exit":
 print("AI_STP_NATIVE_DESKTOP_FAILURE_V1 123",flush=True)
 sys.exit(3)
"""


def test_native_owner_approves_once_without_publishing_child_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    codes: list[str] = []
    marker = tmp_path / "completed"
    count = run_owner(
        [sys.executable, "-u", "-c", CHILD, "a" * 64, "valid", str(marker)],
        environment=dict(os.environ),
        errors=tmp_path / "errors",
        nonce="a" * 64,
        approve=codes.append,
    )
    assert count == 1 and codes == ["SYNTHETIC-CODE"]
    assert marker.read_text() == "completed"
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("case", ["nonce", "sequence", "action", "extra", "oversize"])
def test_native_owner_refuses_bad_request_and_closes_owned_input(case: str, tmp_path: Path) -> None:
    codes: list[str] = []
    marker = tmp_path / "completed"
    with pytest.raises(ValueError, match="Native fixture request"):
        run_owner(
            [sys.executable, "-u", "-c", CHILD, "a" * 64, case, str(marker)],
            environment=dict(os.environ),
            errors=tmp_path / "errors",
            nonce="a" * 64,
            approve=codes.append,
        )
    assert codes == []
    assert marker.read_text() == "completed"


def test_native_owner_failure_reports_only_approved_checkpoint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    codes: list[str] = []
    marker = tmp_path / "completed"
    with pytest.raises(
        ValueError, match="did not complete its approval journey at approval; controller line 123"
    ):
        run_owner(
            [sys.executable, "-u", "-c", CHILD, "a" * 64, "exit", str(marker)],
            environment=dict(os.environ),
            errors=tmp_path / "errors",
            nonce="a" * 64,
            approve=codes.append,
        )
    assert codes == ["SYNTHETIC-CODE"]
    assert marker.read_text() == "completed"
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("location", "repeat"),
    [("-1", False), ("10001", False), ("PRIVATE-CANARY", False), ("12", True)],
)
def test_native_owner_refuses_content_or_repeated_failure_locations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], location: str, repeat: bool
) -> None:
    child = """
import pathlib,sys
print("AI_STP_NATIVE_DESKTOP_FAILURE_V1 "+sys.argv[1],flush=True)
if sys.argv[2]=="repeat":
 print("AI_STP_NATIVE_DESKTOP_FAILURE_V1 13",flush=True)
assert sys.stdin.readline()==""
pathlib.Path(sys.argv[3]).write_text("completed")
"""
    codes: list[str] = []
    marker = tmp_path / "completed"
    with pytest.raises(ValueError, match="Native fixture failure location") as refused:
        run_owner(
            [
                sys.executable,
                "-u",
                "-c",
                child,
                location,
                "repeat" if repeat else "once",
                str(marker),
            ],
            environment=dict(os.environ),
            errors=tmp_path / "errors",
            nonce="a" * 64,
            approve=codes.append,
        )
    assert codes == [] and marker.read_text() == "completed"
    assert "PRIVATE-CANARY" not in str(refused.value)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "checkpoint", ["discovery_unavailable", "context_connection", "organization", "PRIVATE-CANARY"]
)
def test_native_selector_diagnostic_accepts_only_closed_classification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], checkpoint: str
) -> None:
    child = """
import pathlib,sys
print("private diagnostic PRIVATE-CANARY",flush=True)
print("AI_STP_NATIVE_DESKTOP_STAGE_V1 "+sys.argv[1],flush=True)
print("AI_STP_NATIVE_DESKTOP_FAILURE_V1 123",flush=True)
if sys.argv[1] != "PRIVATE-CANARY":
 pathlib.Path(sys.argv[2]).write_text("completed")
 sys.exit(3)
assert sys.stdin.readline()==""
pathlib.Path(sys.argv[2]).write_text("completed")
"""
    codes: list[str] = []
    marker = tmp_path / "completed"
    expected = (
        f"at {checkpoint}; controller line 123"
        if checkpoint != "PRIVATE-CANARY"
        else "Native fixture checkpoint refused"
    )
    with pytest.raises(ValueError, match=expected) as refused:
        run_owner(
            [sys.executable, "-u", "-c", child, checkpoint, str(marker)],
            environment=dict(os.environ),
            errors=tmp_path / "errors",
            nonce="a" * 64,
            approve=codes.append,
        )
    assert codes == [] and marker.read_text() == "completed"
    assert "PRIVATE-CANARY" not in str(refused.value)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "nullable",
        "extra",
        "missing",
        "role_low",
        "role_high",
        "integer_bool",
        "flag",
        "hresult",
        "malformed",
        "not_object",
        "oversize",
        "repeated",
    ],
)
def test_native_option_failure_accepts_only_bounded_codes_and_capabilities(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    child = r"""
import pathlib,sys
print("private UI PRIVATE-CANARY",flush=True)
print("AI_STP_NATIVE_DESKTOP_STAGE_V1 context_connection",flush=True)
print("AI_STP_NATIVE_DESKTOP_OPTION_V1 "+sys.argv[1],flush=True)
if sys.argv[2]=="repeated":
 print("AI_STP_NATIVE_DESKTOP_OPTION_V1 "+sys.argv[1],flush=True)
if sys.argv[2] in {"valid","nullable"}:
 pathlib.Path(sys.argv[3]).write_text("completed")
 print("AI_STP_NATIVE_DESKTOP_FAILURE_V1 123",flush=True)
 sys.exit(3)
assert sys.stdin.readline()==""
pathlib.Path(sys.argv[3]).write_text("completed")
"""
    payload: dict[str, object] = {
        "hresult": "80040201",
        "missing_pattern": False,
        "control_type": 50007,
        "enabled": True,
        "offscreen": False,
        "selection_item": False,
        "invoke": True,
        "selected_after": None,
    }
    if case == "nullable":
        for key in ["control_type", "enabled", "offscreen", "selection_item", "invoke"]:
            payload[key] = None
    if case == "extra":
        payload["ui_text"] = "PRIVATE-CANARY"
    if case == "missing":
        del payload["hresult"]
    if case == "role_low":
        payload["control_type"] = 49999
    if case == "role_high":
        payload["control_type"] = 50041
    if case == "integer_bool":
        payload["control_type"] = True
    if case == "flag":
        payload["selected_after"] = "PRIVATE-CANARY"
    if case == "hresult":
        payload["hresult"] = "PRIVATE-CANARY"
    encoded = (
        "{PRIVATE-CANARY"
        if case == "malformed"
        else "[]"
        if case == "not_object"
        else " " * 1025 + json.dumps(payload)
        if case == "oversize"
        else json.dumps(payload)
    )
    marker = tmp_path / "completed"
    expected = (
        "at context_connection; controller line 123"
        if case in {"valid", "nullable"}
        else "Native fixture option diagnostic"
    )
    with pytest.raises(ValueError, match=expected) as refused:
        run_owner(
            [sys.executable, "-u", "-c", child, encoded, case, str(marker)],
            environment=dict(os.environ),
            errors=tmp_path / "errors",
            nonce="a" * 64,
            approve=lambda _: pytest.fail("A native option failure cannot request approval"),
        )
    if case in {"valid", "nullable"}:
        observed = str(refused.value).split("; option diagnostic=", 1)[1]
        assert json.loads(observed) == payload
    assert marker.read_text() == "completed"
    assert "PRIVATE-CANARY" not in str(refused.value)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "nullable",
        "extra",
        "missing",
        "expected_bool",
        "expected_zero",
        "expected_high",
        "observed_bool",
        "observed_high",
        "flag",
        "modifiers_bool",
        "modifiers_high",
        "focused_text",
        "malformed",
        "not_object",
        "oversize",
        "repeated",
        "success_claim",
    ],
)
def test_native_input_failure_keeps_field_text_private_and_cannot_claim_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    child = r"""
import json,pathlib,sys
print("private UI PRIVATE-CANARY",flush=True)
if sys.argv[2]=="success_claim":
 print("AI_STP_NATIVE_DESKTOP_FIXTURE_V1 "+json.dumps({
  "protocol":"ai-stp-native-desktop-fixture/1","nonce":"a"*64,
  "sequence":1,"action":"approve_device","user_code":"PRIVATE-CANARY"}),flush=True)
 assert json.loads(sys.stdin.readline())["approved"] is True
print("AI_STP_NATIVE_DESKTOP_STAGE_V1 approval",flush=True)
print("AI_STP_NATIVE_DESKTOP_INPUT_V1 "+sys.argv[1],flush=True)
if sys.argv[2]=="repeated":
 print("AI_STP_NATIVE_DESKTOP_INPUT_V1 "+sys.argv[1],flush=True)
if sys.argv[2] in {"valid","nullable","success_claim"}:
 pathlib.Path(sys.argv[3]).write_text("completed")
 if sys.argv[2]!="success_claim":
  print("AI_STP_NATIVE_DESKTOP_FAILURE_V1 454",flush=True)
 sys.exit(0 if sys.argv[2]=="success_claim" else 3)
assert sys.stdin.readline()==""
pathlib.Path(sys.argv[3]).write_text("completed")
"""
    payload: dict[str, object] = {
        "expected_length": 24,
        "observed_length": 0,
        "unchanged": True,
        "automation_focused": False,
        "foreground_owned": False,
        "keyboard_focus_owned": False,
        "keyboard_focus_is_root": False,
        "pressed_modifiers": 0,
        "element_available": True,
        "element_enabled": True,
        "focused_control_type": "ControlType.Document",
    }
    if case == "nullable":
        for key in payload:
            if key != "expected_length":
                payload[key] = None
    if case == "extra":
        payload["field_text"] = "PRIVATE-CANARY"
    if case == "missing":
        del payload["unchanged"]
    if case == "expected_bool":
        payload["expected_length"] = True
    if case == "expected_zero":
        payload["expected_length"] = 0
    if case == "expected_high":
        payload["expected_length"] = 121
    if case == "observed_bool":
        payload["observed_length"] = False
    if case == "observed_high":
        payload["observed_length"] = 65537
    if case == "flag":
        payload["automation_focused"] = "PRIVATE-CANARY"
    if case == "modifiers_bool":
        payload["pressed_modifiers"] = True
    if case == "modifiers_high":
        payload["pressed_modifiers"] = 32
    if case == "focused_text":
        payload["focused_control_type"] = "PRIVATE-CANARY"
    encoded = (
        "{PRIVATE-CANARY"
        if case == "malformed"
        else "[]"
        if case == "not_object"
        else " " * 513 + json.dumps(payload)
        if case == "oversize"
        else json.dumps(payload)
    )
    marker = tmp_path / "completed"
    valid = case in {"valid", "nullable", "success_claim"}
    expected = (
        "at approval; controller line " + ("None" if case == "success_claim" else "454")
        if valid
        else "Native fixture input diagnostic"
    )
    codes: list[str] = []
    with pytest.raises(ValueError, match=expected) as refused:
        run_owner(
            [sys.executable, "-u", "-c", child, encoded, case, str(marker)],
            environment=dict(os.environ),
            errors=tmp_path / "errors",
            nonce="a" * 64,
            approve=codes.append,
        )
    if valid:
        observed = str(refused.value).split("; input diagnostic=", 1)[1]
        assert json.loads(observed) == payload
    assert codes == (["PRIVATE-CANARY"] if case == "success_claim" else [])
    assert marker.read_text() == "completed"
    assert "PRIVATE-CANARY" not in str(refused.value)
    assert capsys.readouterr().out == ""
