"""Actual child-process approval transport rejects malformed or foreign requests."""

from __future__ import annotations

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
