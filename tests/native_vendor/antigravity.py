"""Read actual Antigravity skill discovery through its ACP server without a model turn."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import queue
import re
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, cast

from . import installation
from .common import binary_digest, environment, write_skill

PREFIX = "ai-stp-qualification-"


def prepare(distribution: Path, root: Path) -> tuple[Path, str]:
    manifest = json.loads((distribution / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1 and manifest["vendor"] == "antigravity"
    version = cast(str, manifest["version"])
    package = manifest["packages"][platform.system()]
    url = cast(str, package["url"])
    assert url.startswith("https://storage.googleapis.com/antigravity-public/antigravity-cli/")
    download = root / url.rsplit("/", 1)[1]
    digest = hashlib.sha512()
    request = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(request, timeout=120) as response, download.open("xb") as output:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
            assert output.tell() <= package["size"], "Antigravity package exceeded its size"
    assert download.stat().st_size == package["size"], "Antigravity package size differs"
    assert digest.hexdigest() == package["sha512"], "Antigravity package digest differs"
    if download.suffix == ".exe":
        return download, version
    extracted = root / "package"
    extracted.mkdir()
    # Data extraction only; the vendor's installer script never runs.
    with tarfile.open(download) as bundle:
        bundle.extractall(extracted, filter="data")
    executable = extracted / "antigravity"
    executable.chmod(executable.stat().st_mode | 0o100)
    return executable, version


class Acp:
    """One Agent Client Protocol session: initialize and session/new, never a prompt."""

    def __init__(self, executable: Path, project: Path, child_environment: dict[str, str]):
        self.process = subprocess.Popen(
            [str(executable), "acp"],
            cwd=project,
            env=child_environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self.messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            if len(line) > 4 * 1024 * 1024:
                break
            self.messages.put(cast(dict[str, Any], json.loads(line)))
        self.messages.put(None)

    def request(self, identifier: int, method: str, parameters: dict[str, Any]) -> dict[str, Any]:
        assert self.process.stdin is not None
        message = {"jsonrpc": "2.0", "id": identifier, "method": method, "params": parameters}
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        self.process.stdin.flush()
        while True:
            reply = self.messages.get(timeout=60)
            assert reply is not None, "Antigravity ACP closed"
            if reply.get("id") == identifier:
                assert "error" not in reply, reply.get("error")
                return cast(dict[str, Any], reply["result"])

    def commands(self, session: str) -> dict[str, str]:
        deadline = time.monotonic() + 30
        while (remaining := deadline - time.monotonic()) > 0:
            message = self.messages.get(timeout=remaining)
            assert message is not None, "Antigravity ACP closed"
            parameters = message.get("params", {})
            update = parameters.get("update", {})
            if (
                message.get("method") == "session/update"
                and parameters.get("sessionId") == session
                and update.get("sessionUpdate") == "available_commands_update"
            ):
                return {
                    command["name"]: command.get("description", "")
                    for command in update["availableCommands"]
                    if command["name"].startswith(PREFIX)
                }
        raise TimeoutError("Antigravity did not announce its commands")

    def close(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=15)


def session_commands(
    executable: Path, project: Path, child_environment: dict[str, str]
) -> dict[str, str]:
    acp = Acp(executable, project, child_environment)
    try:
        initialized = acp.request(
            1,
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                },
            },
        )
        assert initialized["protocolVersion"] == 1
        session = acp.request(2, "session/new", {"cwd": str(project), "mcpServers": []})
        return acp.commands(cast(str, session["sessionId"]))
    finally:
        acp.close()


def qualify(executable: Path, root: Path) -> dict[str, Any]:
    home, project = root / "h", root / "p"
    for directory in [home, project, root / "t"]:
        directory.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet", str(project)], check=True, timeout=10)
    roots = {
        "global": home / ".gemini" / "config" / "skills",
        "project": project / ".agents" / "skills",
    }
    for scope, path in roots.items():
        write_skill(path, PREFIX + scope, PREFIX + scope, "Controlled " + scope + " discovery")
        write_skill(path, PREFIX + "shadow", PREFIX + "shadow", "Controlled shadow " + scope)
    child_environment = environment(root, "ANTIGRAVITY_HOME", home / ".gemini")
    child_environment["NO_COLOR"] = "1"
    controls: dict[str, bool] = {}

    both = session_commands(executable, project, child_environment)
    assert both == {
        PREFIX + "global": "Controlled global discovery",
        PREFIX + "project": "Controlled project discovery",
        PREFIX + "shadow": "Controlled shadow project",
    }, both
    controls["global_and_project_skills_announced"] = True
    controls["project_shadows_global_by_name"] = True

    for path in [roots["project"] / (PREFIX + "project"), roots["project"] / (PREFIX + "shadow")]:
        (path / "SKILL.md").unlink()
        path.rmdir()
    remaining = session_commands(executable, project, child_environment)
    assert remaining == {
        PREFIX + "global": "Controlled global discovery",
        PREFIX + "shadow": "Controlled shadow global",
    }, remaining
    controls["removed_project_skill_falls_back_to_global"] = True
    assert all(controls.values())
    return {
        "state": "passed",
        "controls": controls,
        "evidence_kind": "vendor_configuration_read",
        "commands": ["acp initialize", "acp session/new"],
        "scopes": ["global:~/.gemini/config/skills", "project:.agents/skills"],
        "account": "none",
        "vendor_updates_and_telemetry": "vendor_default_owner_decision_2026_11_13",
        "inference_turns_started": 0,
        "user_scope_fixture": "isolated_home",
    }


def qualify_installed(
    executable: Path, engine: Path, root: Path, engine_proof: dict[str, Any]
) -> dict[str, Any]:
    case = installation.Installation(
        engine, root / "i", "ANTIGRAVITY_HOME", home_relative_vendor_root=".gemini"
    )
    case.environment["NO_COLOR"] = "1"
    name = PREFIX + "installed-antigravity"
    (case.source / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Controlled native installation fixture\n---\n"
        "Format only caller-supplied fixture text.\n",
        encoding="utf-8",
    )
    receipt = case.install("antigravity", "skill", name, "global")
    announced = session_commands(executable, case.project, case.environment)
    assert announced.get(name) == "Controlled native installation fixture", announced
    removal = case.remove(receipt)
    case.apply(removal)
    assert name not in session_commands(executable, case.project, case.environment)
    case.removed()
    return {
        "state": "passed",
        "evidence_kind": "native_engine_vendor_configuration_read",
        "engine": engine_proof,
        "install_and_remove_receipts_idempotent": True,
        "original_context_preserved_across_selected_view": True,
        "vendor_announced_installed_skill": True,
        "skill_absent_after_removal_in_fresh_session": True,
        "unowned_preserved_and_pending_cleared": True,
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
    # The vendor's own background updater may still hold files at cleanup.
    with tempfile.TemporaryDirectory(
        prefix="stp-antigravity-", dir=os.environ.get("RUNNER_TEMP"), ignore_cleanup_errors=True
    ) as temporary:
        root = Path(temporary)
        executable, version = prepare(arguments.distribution, root)
        digest = binary_digest(executable)
        result = qualify(executable.resolve(), root / "q")
        engine = installation.prepare(root, source)
        result["installed_configuration"] = (
            qualify_installed(executable.resolve(), engine[0], root, engine[1])
            if engine is not None
            else {"state": "not_selected"}
        )
    proof = {
        "schema_version": 1,
        "source_sha": source,
        "vendor": "antigravity",
        "vendor_version": version,
        "vendor_binary_sha256": digest,
        "platform": platform.system(),
        "architecture": platform.machine(),
        "release_authorized": False,
        **result,
    }
    arguments.proof.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
