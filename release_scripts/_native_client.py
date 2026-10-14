"""Shared optimized CLI/device-flow boundary for native API evidence."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from release_scripts._evidence import EvidenceError, without_credentials


class NativeClient:
    def __init__(self, binary: Path) -> None:
        self.binary = binary
        self.calls = 0
        self.scenarios: dict[str, str] = {}

    def invoke(self, root: Path, *args: str | Path, ok: bool = True) -> dict[str, Any]:
        environment = dict(
            os.environ,
            HOME=str(root / "home"),
            USERPROFILE=str(root / "home"),
            XDG_DATA_HOME=str(root / "data"),
            XDG_CONFIG_HOME=str(root / "config"),
            XDG_CACHE_HOME=str(root / "cache"),
            AI_STP_TELEMETRY_SUPPRESS="1",
        )
        result = subprocess.run(
            [str(self.binary), *map(str, args), "--json"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=50,
            check=False,
        )
        self.calls += 1
        if result.stderr:
            raise EvidenceError("native stderr is not empty")
        envelope = json.loads(result.stdout)
        # Identity/session replies must not carry credentials. Full authoring
        # plans also contain legitimate requires_authorization contract fields;
        # callers export only sanitized reports, checked at that boundary.
        if args and args[0] in {"account", "device", "sync", "github"}:
            without_credentials(envelope)
        if envelope["ok"] != ok or (result.returncode == 0) != ok:
            error = envelope.get("error", {})
            raise EvidenceError(
                f"unexpected native outcome for {' '.join(map(str, args[:3]))}: "
                f"{error.get('code', 'success')} — {error.get('message', 'no error message')}"
            )
        return envelope["data"] if ok else envelope

    def apply(
        self,
        root: Path,
        prepared: dict[str, Any],
        prefix: tuple[str, ...],
        *,
        extra: tuple[str | Path, ...] = (),
        ok: bool = True,
    ) -> dict[str, Any]:
        path = root / "plan.json"
        path.write_text(json.dumps(prepared["plan"]), encoding="utf-8")
        path.chmod(0o600)
        args: list[str | Path] = [
            *prefix,
            "--plan",
            path,
            "--plan-digest",
            prepared["plan_digest"],
        ]
        args.extend(extra)
        return self.invoke(root, *args, ok=ok)

    def account(self, root: Path, action: str, origin: str | None = None) -> dict[str, Any]:
        args: list[str | Path] = ["account", "plan", "--state-dir", root, "--action", action]
        if origin:
            args += ["--api-url", origin]
        return self.apply(root, self.invoke(root, *args), ("account", "apply"))

    def local(self, state: Path, command_path: str, **flags: str | Path) -> dict[str, Any]:
        args: list[str | Path] = [*command_path.split(), "--state-dir", state]
        for key, value in flags.items():
            args += ["--" + key.replace("_", "-"), value]
        return self.apply(state, self.invoke(state, *args), ("local", "apply"))

    def login(self, root: Path, origin: str, web: httpx.Client) -> dict[str, Any]:
        assert self.account(root, "start", origin)["outcome"] == "pending"
        pending = self.invoke(root, "account", "status", "--state-dir", root)
        response = web.post(
            "/v1/auth/device/approve",
            json={
                "schema_version": 1,
                "user_code": pending["session"]["user_code"],
            },
        )
        assert response.status_code == 200
        deadline = datetime.fromisoformat(pending["session"]["next_poll_at"].replace("Z", "+00:00"))
        seconds = max(0, (deadline - datetime.now(UTC)).total_seconds())
        assert seconds < 15
        time.sleep(seconds + 0.08)
        authorized = self.account(root, "poll")
        assert authorized["outcome"] == "authorized"
        return authorized
