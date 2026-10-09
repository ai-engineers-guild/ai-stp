"""Real native identity CLI envelopes and Python-owned device/plan contracts."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_stp_contracts.cli.identity import DeviceIdentity
from ai_stp_foundation.digests import digest_canonical

Runner = Callable[[Path, Path, list[str], int], dict[str, Any]]


def prove(binary: Path, home: Path, temporary: Path, run: Runner) -> None:
    state = temporary / "identity-state"
    state.mkdir()
    show = ["device", "show", "--state-dir", str(state)]
    run(binary, home, show, 2)
    prefix = ["device", "initialize", "plan", "--state-dir", str(state), "--credential-store"]
    planned = run(binary, home, [*prefix, "os_keyring"], 0)["data"]
    assert planned["plan"]["credential_store"] == "os_keyring"
    assert not list(state.iterdir()), "planning opened credentials or created state"
    if os.name == "nt":
        run(binary, home, [*prefix, "file"], 4)
        assert not list(state.iterdir())
        return
    planned = run(binary, home, [*prefix, "file"], 0)["data"]
    plan, digest = planned["plan"], planned["plan_digest"]
    assert digest_canonical("ai-stp:plan:v1", plan) == digest
    path = temporary / "identity-plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    args = ["device", "initialize", "apply", "--plan", str(path), "--plan-digest"]
    run(binary, home, [*args, "sha256:" + "0" * 64], 4)
    assert not list(state.iterdir())
    report = run(binary, home, [*args, digest], 0)["data"]
    DeviceIdentity.model_validate(report)
    assert report["device_id"] == plan["device_id"]
    assert report["credential_store"] == "file"
    assert run(binary, home, [*args, digest], 0)["data"] == report
    assert run(binary, home, show, 0)["data"] == report
    owned = state / "ai-stp-v2-identity"
    assert {item.name for item in owned.iterdir()} == {
        "owner",
        "lock",
        "pending.json",
        "identity.json",
        f"device-key.{plan['device_id']}",
    }
    assert (owned / f"device-key.{plan['device_id']}").stat().st_mode & 0o777 == 0o600
    assert owned.stat().st_mode & 0o777 == 0o700
    run(binary, home, [*prefix, "file"], 4)
