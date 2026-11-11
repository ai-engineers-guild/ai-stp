"""Read actual Codex configuration without starting a thread or inference turn."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

PREFIX = "ai-stp-qualification-"


class Rpc:
    """Bounded line RPC over native pipes, including Windows pipes."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stdin is not None and process.stdout is not None
        self.process = process
        self.input = process.stdin
        self.output = process.stdout
        self.messages: queue.Queue[bytes | Exception] = queue.Queue(maxsize=32)
        self.stopped = threading.Event()
        self.requests: list[str] = []
        self.identifier = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        try:
            while not self.stopped.is_set():
                line = self.output.readline(2 * 1024 * 1024 + 1)
                if not line:
                    raise EOFError("Codex closed its local RPC output")
                if len(line) > 2 * 1024 * 1024 or not line.endswith(b"\n"):
                    raise ValueError("Codex RPC line exceeds the declared bound")
                while not self.stopped.is_set():
                    try:
                        self.messages.put(line, timeout=0.5)
                        break
                    except queue.Full:
                        continue
        except (OSError, ValueError, EOFError) as error:
            if not self.stopped.is_set():
                with suppress(queue.Full):
                    self.messages.put_nowait(error)

    def request(self, method: str, parameters: dict[str, Any]) -> dict[str, Any]:
        assert method in {"initialize", "skills/list", "config/read"}
        identifier = self.identifier
        self.identifier += 1
        self.requests.append(method)
        self.input.write(
            json.dumps({"id": identifier, "method": method, "params": parameters}).encode() + b"\n"
        )
        self.input.flush()
        deadline = time.monotonic() + 15
        for _ in range(256):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Codex local RPC response deadline")
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError("Codex local RPC response deadline") from error
            if isinstance(message, Exception):
                raise message
            document = cast(dict[str, Any], json.loads(message))
            if document.get("id") == identifier and "method" not in document:
                assert "error" not in document, document.get("error")
                return cast(dict[str, Any], document["result"])
            assert "id" not in document, "Unexpected server-initiated RPC request"
        raise ValueError("Codex RPC notification bound exceeded")

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "ai_stp_native_qualification",
                    "title": "AI-STP Native Qualification",
                    "version": "0.0.0",
                }
            },
        )
        self.input.write(b'{"method":"initialized"}\n')
        self.input.flush()
        self.requests.append("initialized")

    def close(self) -> None:
        self.stopped.set()
        self.input.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.reader.join(timeout=5)
        assert not self.reader.is_alive(), "Owned RPC reader did not stop"
        self.output.close()


def write_skill(root: Path, folder: str, name: str, description: str) -> Path:
    directory = root / folder
    directory.mkdir(parents=True)
    document = directory / "SKILL.md"
    document.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n"
        "Format only caller-supplied fixture text.\n",
        encoding="utf-8",
    )
    return document


def entries(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        skill
        for entry in result["data"]
        for skill in entry["skills"]
        if skill["name"].startswith(PREFIX)
    ]


def observed_paths(rows: list[dict[str, Any]], name: str, expected: list[Path]) -> None:
    matching = [row for row in rows if row["name"] == name]
    assert len(matching) == len(expected), (name, len(matching), len(expected))
    for path in expected:
        selected = [row for row in matching if Path(row["path"]).samefile(path)]
        assert len(selected) == 1 and selected[0]["enabled"] is True


def qualify(executable: Path, root: Path) -> dict[str, Any]:
    case_home, vendor_home, project = root / "h", root / "c", root / "p"
    for directory in [case_home, vendor_home, project, root / "t"]:
        directory.mkdir()
    subprocess.run(["git", "init", "--quiet", str(project)], check=True, timeout=10)
    roots = {
        "config": vendor_home / "skills",
        "user": case_home / ".agents" / "skills",
        "project": project / ".agents" / "skills",
    }
    unique = {
        scope: write_skill(path, "unique", PREFIX + scope, "Controlled " + scope + " discovery")
        for scope, path in roots.items()
    }
    (vendor_home / "config.toml").write_text(
        'cli_auth_credentials_store = "file"\nmodel_verbosity = "low"\n'
        "[analytics]\nenabled = false\n[projects."
        + json.dumps(str(project))
        + ']\ntrust_level = "trusted"\n',
        encoding="utf-8",
    )
    project_configuration = project / ".codex" / "config.toml"
    project_configuration.parent.mkdir()
    project_configuration.write_text('model_verbosity = "high"\n', encoding="utf-8")
    environment = {
        name: value
        for name, value in os.environ.items()
        if name in {"PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"}
    }
    environment.update(
        {
            "HOME": str(case_home),
            "USERPROFILE": str(case_home),
            "CODEX_HOME": str(vendor_home),
            "TMPDIR": str(root / "t"),
            "TMP": str(root / "t"),
            "TEMP": str(root / "t"),
            "LANG": "C.UTF-8",
            "XDG_CONFIG_HOME": str(case_home / ".config"),
            "XDG_CACHE_HOME": str(case_home / ".cache"),
            "XDG_DATA_HOME": str(case_home / ".local" / "share"),
        }
    )
    requests: list[str] = []
    controls: dict[str, bool] = {}
    with (root / "stderr.log").open("wb") as errors:
        process = subprocess.Popen(
            [str(executable), "app-server", "--listen", "stdio://"],
            cwd=project,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errors,
        )
        rpc = Rpc(process)
        try:
            rpc.initialize()

            def read_skills() -> dict[str, Any]:
                return rpc.request("skills/list", {"cwds": [str(project)], "forceReload": True})

            initial = entries(read_skills())
            for scope, path in unique.items():
                observed_paths(initial, PREFIX + scope, [path])
            controls["three_scope_discovery"] = True
            shadow = [
                write_skill(path, "shadow", PREFIX + "shadow", "Controlled shadow " + scope)
                for scope, path in roots.items()
            ]
            observed_paths(entries(read_skills()), PREFIX + "shadow", shadow)
            controls["same_name_skills_remain_distinct"] = True
            unique["project"].unlink()
            refreshed = entries(read_skills())
            observed_paths(refreshed, PREFIX + "project", [])
            observed_paths(refreshed, PREFIX + "config", [unique["config"]])
            observed_paths(refreshed, PREFIX + "user", [unique["user"]])
            controls["force_reload_removes_only_absent_skill"] = True
            malformed = roots["project"] / "malformed" / "SKILL.md"
            malformed.parent.mkdir()
            malformed.write_text("---\nname: [broken\n---\nControlled bad fixture.\n")
            refused = read_skills()
            assert any(
                Path(error["path"]).samefile(malformed)
                for entry in refused["data"]
                for error in entry["errors"]
            )
            assert not any(Path(row["path"]).samefile(malformed) for row in entries(refused))
            controls["malformed_skill_reported"] = True

            def verbosity() -> Any:
                result = rpc.request("config/read", {"cwd": str(project), "includeLayers": True})
                return result["config"]["model_verbosity"]

            assert verbosity() == "high"
            project_configuration.unlink()
            assert verbosity() == "low"
            controls["project_setting_and_removed_layer"] = True
            assert not (vendor_home / "auth.json").exists()
            controls["no_login_artifact"] = True
            requests = rpc.requests.copy()
        finally:
            rpc.close()
    assert all(controls.values()) and len(controls) == 6
    assert not any(method.startswith(("turn/", "thread/")) for method in requests)
    return {
        "controls": controls,
        "request_methods": requests,
        "evidence_kind": "vendor_configuration_read",
        "inference_turns_started": 0,
    }


def prepare(manifest: Path, tools: Path, root: Path) -> tuple[Path, dict[str, Any]]:
    declaration = cast(dict[str, Any], json.loads(manifest.read_text()))
    assert declaration["schema_version"] == 1 and declaration["tool"] == "codex"
    assets = declaration["assets"]
    assert len(assets) == 1 and assets[0]["repository"] == "openai/codex"
    archive = tools / assets[0]["file"]
    assert archive.stat().st_size == assets[0]["size"]
    with archive.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == assets[0]["sha256"]
    member_name = Path(urlparse(cast(str, declaration["source"])).path).name.removesuffix(".tar.gz")
    executable = root / ("codex.exe" if os.name == "nt" else "codex")
    with tarfile.open(archive, "r:gz") as bundle:
        member = bundle.getmember(member_name)
        assert member.isfile() and 0 < member.size < 1024 * 1024 * 1024
        stream = bundle.extractfile(member)
        assert stream is not None
        with stream, executable.open("xb") as destination:
            shutil.copyfileobj(stream, destination)
    executable.chmod(0o700)
    version = subprocess.check_output([str(executable), "--version"], text=True, timeout=15)
    assert version.strip() == "codex-cli " + declaration["version"]
    return executable, declaration


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    arguments = parser.parse_args()
    source = os.environ["AI_STP_NATIVE_VENDOR_SOURCE"]
    assert re.fullmatch(r"[0-9a-f]{40}", source)
    operating_system, architecture = {
        "Linux": ("Linux", "x86_64"),
        "Darwin": ("macOS", "arm64"),
        "Windows": ("Windows", "amd64"),
    }[platform.system()]
    assert arguments.manifest.name == f"codex-{operating_system}.json"
    assert platform.machine().lower() == architecture
    with tempfile.TemporaryDirectory(
        prefix="stp-codex-", dir=os.environ.get("RUNNER_TEMP")
    ) as temporary:
        root = Path(temporary)
        executable, declaration = prepare(arguments.manifest, arguments.tools, root)
        result = qualify(executable.resolve(), root)
        with executable.open("rb") as stream:
            binary_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    proof = {
        "schema_version": 1,
        "source_sha": source,
        "vendor": "codex",
        "vendor_version": declaration["version"],
        "vendor_binary_sha256": binary_digest,
        "platform": platform.system(),
        "architecture": platform.machine(),
        "release_authorized": False,
        **result,
    }
    arguments.proof.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
