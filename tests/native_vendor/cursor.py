"""Read actual Cursor MCP discovery and loading without an account or a model turn."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, cast

from . import installation
from .common import binary_digest, environment

PREFIX = "ai-stp-qualification-"
EXECUTABLES = ("cursor-agent", "cursor-agent.exe", "cursor-agent.cmd")
LINE = re.compile(r"^(?P<name>[A-Za-z0-9._-]+): (?P<status>.+)$")

# A minimal stdio MCP server: its single tool names the scope it was started for.
SERVER = """import json, sys
scope = sys.argv[1]
for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    method = message.get("method")
    if method == "initialize":
        result = {"protocolVersion": message["params"].get("protocolVersion", "2025-06-18"),
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "ai-stp-probe", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "probe_" + scope, "description": "Fixture tool",
                             "inputSchema": {"type": "object", "properties": {}}}]}
    else:
        result = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}) + "\\n")
    sys.stdout.flush()
"""


def prepare(distribution: Path, root: Path) -> tuple[Path, str]:
    manifest = json.loads((distribution / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1 and manifest["vendor"] == "cursor"
    version = cast(str, manifest["version"])
    package = manifest["packages"][platform.system()]
    url = cast(str, package["url"])
    assert url.startswith("https://downloads.cursor.com/lab/" + version + "/")
    archive = root / ("package.zip" if url.endswith(".zip") else "package.tar.gz")
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(request, timeout=120) as response, archive.open("xb") as output:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
            assert output.tell() <= package["size"], "Cursor package exceeded its pinned size"
    assert archive.stat().st_size == package["size"], "Cursor package size differs"
    assert digest.hexdigest() == package["sha256"], "Cursor package digest differs"
    extracted = root / "package"
    extracted.mkdir()
    # Data extraction only; the vendor's installer script never runs.
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extracted)
    else:
        with tarfile.open(archive) as bundle:
            bundle.extractall(extracted, filter="data")
    candidates = [path for path in extracted.rglob("*") if path.name in EXECUTABLES]
    executable = min(candidates, key=lambda path: (len(path.parts), path.name))
    if os.name != "nt":
        executable.chmod(executable.stat().st_mode | 0o100)
    return executable, version


def cursor(
    executable: Path, project: Path, child_environment: dict[str, str], *arguments: str
) -> str:
    completed = subprocess.run(
        [str(executable), *arguments],
        cwd=project,
        env=child_environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
        timeout=90,
    )
    assert len(completed.stdout) <= 256 * 1024, "Cursor output bound exceeded"
    return completed.stdout.decode("utf-8", "replace")


def listed(output: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in output.splitlines():
        match = LINE.match(line.strip())
        if match and match["name"].startswith(PREFIX):
            assert match["name"] not in rows, "Cursor listed one MCP name twice"
            rows[match["name"]] = match["status"]
    return rows


def tools(
    executable: Path, project: Path, child_environment: dict[str, str], name: str
) -> set[str]:
    output = cursor(executable, project, child_environment, "mcp", "list-tools", name)
    return {match[1] for match in re.finditer(r"^- (probe_[a-z-]+) \(", output, re.MULTILINE)}


def server(scope: str, script: Path) -> dict[str, Any]:
    return {"command": sys.executable, "args": [str(script), scope]}


def qualify(executable: Path, root: Path) -> dict[str, Any]:
    home, project = root / "h", root / "p"
    for directory in [home / ".cursor", project / ".cursor", root / "t"]:
        directory.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet", str(project)], check=True, timeout=10)
    script = root / "probe.py"
    script.write_text(SERVER, encoding="utf-8")
    child_environment = environment(root, "CURSOR_CONFIG_DIR", home / ".cursor")
    child_environment.update(NO_COLOR="1", DO_NOT_TRACK="1", DISABLE_TELEMETRY="1")
    global_config, project_config = home / ".cursor" / "mcp.json", project / ".cursor" / "mcp.json"
    global_config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    PREFIX + "global": server("global", script),
                    PREFIX + "shadow": server("shadow-global", script),
                }
            }
        ),
        encoding="utf-8",
    )
    project_config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    PREFIX + "project": server("project", script),
                    PREFIX + "shadow": server("shadow-project", script),
                }
            }
        ),
        encoding="utf-8",
    )
    controls: dict[str, bool] = {}
    status = cursor(executable, project, child_environment, "status")
    assert "Not logged in" in status
    controls["no_account"] = True

    initial = listed(cursor(executable, project, child_environment, "mcp", "list"))
    assert set(initial) == {PREFIX + "global", PREFIX + "project", PREFIX + "shadow"}
    assert initial[PREFIX + "project"] == "not loaded (needs approval)"
    assert initial[PREFIX + "shadow"] == "not loaded (needs approval)"
    controls["project_and_global_discovered_once_each"] = True
    controls["project_servers_wait_for_approval"] = True

    assert tools(executable, project, child_environment, PREFIX + "global") == {"probe_global"}
    controls["global_server_loaded_and_listed_its_tool"] = True
    for name in [PREFIX + "project", PREFIX + "shadow"]:
        cursor(executable, project, child_environment, "mcp", "enable", name)
    assert tools(executable, project, child_environment, PREFIX + "project") == {"probe_project"}
    controls["approved_project_server_loaded_and_listed_its_tool"] = True
    assert tools(executable, project, child_environment, PREFIX + "shadow") == {
        "probe_shadow-project"
    }
    controls["project_shadows_global_by_name"] = True
    approved = listed(cursor(executable, project, child_environment, "mcp", "list"))
    assert set(approved.values()) == {"ready"}

    project_config.unlink()
    remaining = listed(cursor(executable, project, child_environment, "mcp", "list"))
    assert set(remaining) == {PREFIX + "global", PREFIX + "shadow"}
    assert tools(executable, project, child_environment, PREFIX + "shadow") == {
        "probe_shadow-global"
    }
    controls["removed_project_server_falls_back_to_global"] = True
    assert not any(
        path.name in {"auth.json", "credentials.json", "session.json"}
        for path in (home / ".cursor").rglob("*")
    )
    controls["no_login_artifact"] = True
    assert all(controls.values())
    return {
        "state": "passed",
        "controls": controls,
        "evidence_kind": "vendor_configuration_read",
        "commands": ["status", "mcp list", "mcp enable", "mcp list-tools"],
        "scopes": ["global:~/.cursor/mcp.json", "project:.cursor/mcp.json"],
        "rules_skills_and_agents": "unknown_without_account_session",
        "inference_turns_started": 0,
        "user_scope_fixture": "isolated_home",
    }


def qualify_installed(
    executable: Path, engine: Path, root: Path, engine_proof: dict[str, Any]
) -> dict[str, Any]:
    """Install a global MCP server through the engine and observe Cursor load it."""
    # Cursor reads its MCP configuration from ~/.cursor whatever its config root.
    case = installation.Installation(
        engine, root / "i", "CURSOR_CONFIG_DIR", home_relative_vendor_root=".cursor"
    )
    case.environment.update(NO_COLOR="1", DO_NOT_TRACK="1", DISABLE_TELEMETRY="1")
    subprocess.run(["git", "init", "--quiet", str(case.project)], check=True, timeout=10)
    script = case.root / "probe.py"
    script.write_text(SERVER, encoding="utf-8")
    name = PREFIX + "installed-cursor"
    (case.source / "mcp.json").write_text(
        json.dumps({"mcpServers": {name: server("installed", script)}}), encoding="utf-8"
    )
    receipt = case.install("cursor", "mcp", name, "global")
    path = case.vendor_home / "mcp.json"
    assert name in json.loads(path.read_bytes())["mcpServers"]
    listed_after_install = listed(cursor(executable, case.project, case.environment, "mcp", "list"))
    assert name in listed_after_install, listed_after_install
    assert tools(executable, case.project, case.environment, name) == {"probe_installed"}
    removal = case.remove(receipt)
    case.apply(removal)
    remaining = listed(cursor(executable, case.project, case.environment, "mcp", "list"))
    assert name not in remaining, remaining
    case.removed()
    return {
        "state": "passed",
        "evidence_kind": "native_engine_vendor_configuration_read",
        "engine": engine_proof,
        "install_and_remove_receipts_idempotent": True,
        "original_context_preserved_across_selected_view": True,
        "vendor_loaded_installed_mcp_server_and_listed_its_tool": True,
        "server_absent_after_removal": True,
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
    with tempfile.TemporaryDirectory(
        prefix="stp-cursor-", dir=os.environ.get("RUNNER_TEMP")
    ) as temporary:
        root = Path(temporary)
        executable, version = prepare(arguments.distribution, root)
        digest = binary_digest(executable)
        reported = cursor(executable, root, {**os.environ, "NO_COLOR": "1"}, "--version")
        assert reported.strip() == version, "Cursor reported another version"
        result = qualify(executable.resolve(), root / "q")
        engine = installation.prepare(root, source)
        result["installed_configuration"] = (
            qualify_installed(executable.resolve(), engine[0], root, engine[1])
            if engine is not None
            else {"state": "not_selected"}
        )
        assert binary_digest(executable) == digest, "Vendor binary changed during qualification"
        shutil.rmtree(root / "package")
    proof = {
        "schema_version": 1,
        "source_sha": source,
        "vendor": "cursor",
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
