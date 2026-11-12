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
print("AI_STP_NATIVE_DESKTOP_FIXTURE_V1 "+json.dumps(request),flush=True)
response=sys.stdin.readline()
if case=="valid":
 result=json.loads(response)
 expected={
  "protocol":request["protocol"],"nonce":request["nonce"],
  "sequence":1,"approved":True,
 }
 assert result==expected
else:
 assert response==""
pathlib.Path(sys.argv[3]).write_text("completed")
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
