"""Read actual Pi resources over ephemeral local RPC without an inference prompt."""

from __future__ import annotations

import argparse
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from tests.support.native_pipe import Pipe

from . import installation
from .common import binary_digest, environment, write_skill

PREFIX = "ai-stp-qualification-"


class Rpc(Pipe):
    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        super().__init__(process)
        self.requests: list[str] = []

    def request(self, command: str) -> dict[str, Any]:
        assert command in {"get_commands", "get_state"}
        identifier = str(len(self.requests))
        self.requests.append(command)
        self.input.write(json.dumps({"id": identifier, "type": command}).encode() + b"\n")
        self.input.flush()
        deadline = time.monotonic() + 15
        for _ in range(256):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Pi local RPC response deadline")
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError("Pi local RPC response deadline") from error
            if isinstance(message, Exception):
                raise message
            document = cast(dict[str, Any], json.loads(message))
            if document.get("id") == identifier:
                assert document.get("type") == "response"
                assert document.get("command") == command
                assert document.get("success") is True, document.get("error")
                return cast(dict[str, Any], document["data"])
            assert "id" not in document, "Unexpected vendor RPC response or request"
        raise ValueError("Pi RPC notification bound exceeded")


def offline_environment(root: Path, vendor_home: Path) -> dict[str, str]:
    result = environment(root, "PI_CODING_AGENT_DIR", vendor_home)
    result.update(PI_OFFLINE="1", PI_TELEMETRY="0")
    return result


@contextmanager
def reader(
    entry: Path, project: Path, child_environment: dict[str, str], errors: Path, *, approved: bool
) -> Generator[Rpc]:
    with errors.open("wb") as error_stream:
        process = subprocess.Popen(
            [
                "node",
                str(entry),
                "--mode",
                "rpc",
                "--no-session",
                "--no-extensions",
                "--no-context-files",
                "--approve" if approved else "--no-approve",
            ],
            cwd=project,
            env=child_environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=error_stream,
        )
        rpc = Rpc(process)
        try:
            yield rpc
        finally:
            rpc.close()


def entries(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in result["commands"]
        if row["source"] == "skill" and row["name"].startswith("skill:" + PREFIX)
    ]


def observed(rows: list[dict[str, Any]], name: str, path: Path | None) -> None:
    selected = [row for row in rows if row["name"] == "skill:" + name]
    if path is None:
        assert not selected, name
    else:
        assert len(selected) == 1, (name, len(selected))
        assert Path(selected[0]["sourceInfo"]["path"]).samefile(path)


def ephemeral(rpc: Rpc) -> None:
    state = rpc.request("get_state")
    assert state["messageCount"] == 0 and state["pendingMessageCount"] == 0
    assert state["isStreaming"] is False and state.get("sessionFile") is None


def qualify(entry: Path, root: Path) -> dict[str, Any]:
    for name in ["h", "v", "p", "t"]:
        (root / name).mkdir()
    vendor_home, project = root / "v", root / "p"
    subprocess.run(["git", "init", "--quiet", str(project)], check=True, timeout=10)
    roots = {"user": vendor_home / "skills", "project": project / ".pi" / "skills"}
    unique = {
        scope: write_skill(path, "unique", PREFIX + scope, "Controlled " + scope + " discovery")
        for scope, path in roots.items()
    }
    shadow = {
        scope: write_skill(path, "shadow", PREFIX + "shadow", "Controlled shadow " + scope)
        for scope, path in roots.items()
    }
    malformed = vendor_home / "skills" / "malformed" / "SKILL.md"
    malformed.parent.mkdir(parents=True)
    malformed.write_text("---\nname: " + PREFIX + "malformed\ndescription: [\n---\n")
    child_environment = offline_environment(root, vendor_home)
    requests: list[str] = []
    controls: dict[str, bool] = {}

    def inspect(label: str, *, approved: bool) -> list[dict[str, Any]]:
        with reader(entry, project, child_environment, root / label, approved=approved) as rpc:
            rows = entries(rpc.request("get_commands"))
            ephemeral(rpc)
            requests.extend(rpc.requests)
            return rows

    untrusted = inspect("untrusted.log", approved=False)
    observed(untrusted, PREFIX + "user", unique["user"])
    observed(untrusted, PREFIX + "project", None)
    observed(untrusted, PREFIX + "shadow", shadow["user"])
    controls["untrusted_project_skills_excluded"] = True

    trusted = inspect("trusted.log", approved=True)
    for scope, path in unique.items():
        observed(trusted, PREFIX + scope, path)
    controls["trusted_user_and_project_discovery"] = True
    observed(trusted, PREFIX + "shadow", shadow["project"])
    controls["trusted_project_shadow_wins"] = True
    observed(trusted, PREFIX + "malformed", None)
    controls["malformed_skill_not_loaded"] = True

    shadow["project"].unlink()
    refreshed = inspect("refreshed.log", approved=True)
    for scope, path in unique.items():
        observed(refreshed, PREFIX + scope, path)
    observed(refreshed, PREFIX + "shadow", shadow["user"])
    controls["removed_project_shadow_falls_back_to_user"] = True
    controls["empty_ephemeral_sessions"] = True
    authentication = vendor_home / "auth.json"
    assert not authentication.exists() or json.loads(authentication.read_text()) == {}
    assert not list(vendor_home.rglob("*.jsonl")), "Ephemeral metadata read persisted a session"
    controls["no_login_credentials_or_session_history"] = True
    assert len(controls) == 7 and all(controls.values())
    return {
        "controls": controls,
        "evidence_kind": "vendor_configuration_read",
        "request_commands": requests,
        "inference_turns_started": 0,
        "user_scope_fixture": "isolated_home",
    }


def prepare(distribution: Path, root: Path) -> tuple[Path, str]:
    sdk = root / "sdk"
    sdk.mkdir()
    for name in ["package.json", "bun.lock"]:
        shutil.copyfile(distribution / name, sdk / name)
    declaration = json.loads((sdk / "package.json").read_text())
    version = cast(str, declaration["dependencies"]["@earendil-works/pi-coding-agent"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    subprocess.run(
        ["bun", "install", "--frozen-lockfile", "--ignore-scripts", "--cwd", str(sdk)],
        check=True,
        timeout=120,
    )
    package = sdk / "node_modules" / "@earendil-works" / "pi-coding-agent"
    metadata = json.loads((package / "package.json").read_text())
    assert metadata["name"] == "@earendil-works/pi-coding-agent"
    assert metadata["version"] == version and metadata["bin"]["pi"] == "dist/bundle/cli.js"
    return package / "dist" / "bundle" / "cli.js", version


def qualify_installed(
    entry: Path, engine: Path, root: Path, engine_proof: dict[str, Any]
) -> dict[str, Any]:
    case = installation.Installation(engine, root / "i", "PI_CODING_AGENT_DIR")
    case.environment.update(PI_OFFLINE="1", PI_TELEMETRY="0")
    name = PREFIX + "installed-pi"
    (case.source / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Controlled native installation fixture\n---\n"
        "Format only caller-supplied fixture text.\n",
        encoding="utf-8",
    )
    receipt = case.install("pi", "skill", name, "global")
    path = case.vendor_home / "skills" / name / "SKILL.md"
    expected = binary_digest(path)
    with reader(
        entry, case.project, case.environment, case.root / "reader.log", approved=False
    ) as rpc:
        observed(entries(rpc.request("get_commands")), name, path)
        ephemeral(rpc)
        removal = case.remove(receipt)
        case.run(case.apply_arguments(removal), refused=True)
        assert binary_digest(path) == expected, "Active-reader refusal changed installed bytes"
    case.apply(removal)
    with reader(
        entry, case.project, case.environment, case.root / "restarted.log", approved=False
    ) as rpc:
        observed(entries(rpc.request("get_commands")), name, None)
        ephemeral(rpc)
    assert not path.exists()
    case.removed()
    return {
        "state": "passed",
        "evidence_kind": "native_engine_vendor_configuration_read",
        "engine": engine_proof,
        "install_and_remove_receipts_idempotent": True,
        "original_context_preserved_across_selected_view": True,
        "vendor_skill_observed": True,
        "active_reader_refusal_preserves_bytes": True,
        "original_removal_after_reader_exit": True,
        "skill_absent_after_reader_restart": True,
        "unowned_preserved_and_pending_cleared": True,
        "runtime_loading": "not_observed",
        "inference_turns_started": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    arguments = parser.parse_args()
    source = os.environ["AI_STP_NATIVE_VENDOR_SOURCE"]
    assert re.fullmatch(r"[0-9a-f]{40}", source)
    expected_architecture = {"Linux": "x86_64", "Darwin": "arm64", "Windows": "amd64"}
    assert platform.machine().lower() == expected_architecture[platform.system()]
    runtime_version = subprocess.check_output(["node", "--version"], text=True, timeout=10).strip()
    assert runtime_version == "v" + Path(".node-version").read_text().strip()
    with tempfile.TemporaryDirectory(
        prefix="stp-pi-", dir=os.environ.get("RUNNER_TEMP")
    ) as temporary:
        root = Path(temporary)
        entry, version = prepare(arguments.distribution, root)
        digest = binary_digest(entry)
        result = qualify(entry.resolve(), root)
        engine = installation.prepare(root, source)
        result["installed_configuration"] = (
            qualify_installed(entry.resolve(), engine[0], root, engine[1])
            if engine is not None
            else {"state": "not_selected"}
        )
        assert binary_digest(entry) == digest, "Vendor entry changed during qualification"
    proof = {
        "schema_version": 1,
        "source_sha": source,
        "vendor": "pi",
        "vendor_version": version,
        "vendor_entry_sha256": digest,
        "distribution_lock_sha256": binary_digest(arguments.distribution / "bun.lock"),
        "node_version": runtime_version,
        "platform": platform.system(),
        "architecture": platform.machine(),
        "release_authorized": False,
        **result,
    }
    arguments.proof.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
