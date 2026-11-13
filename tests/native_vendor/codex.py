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
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from tests.support.native_pipe import Pipe

from . import installation
from .common import binary_digest, environment, write_skill

PREFIX = "ai-stp-qualification-"


class Rpc(Pipe):
    """Codex JSON-RPC methods over owned bounded native pipes."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        super().__init__(process)
        self.requests: list[str] = []
        self.identifier = 0

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


@contextmanager
def native_user_scope() -> Generator[Path | None]:
    """Windows known-folder APIs require an owned child of the native CI profile."""
    if os.name != "nt":
        yield None
        return
    assert os.environ.get("GITHUB_ACTIONS") == "true"
    assert os.environ.get("RUNNER_OS") == "Windows"
    profile_home = Path.home().resolve()
    parent = profile_home / ".agents" / "skills"
    assert parent.resolve().is_relative_to(profile_home)
    parent.mkdir(parents=True, exist_ok=True)
    assert parent.resolve().is_relative_to(profile_home)
    with tempfile.TemporaryDirectory(prefix="stp-codex-", dir=parent) as temporary:
        yield Path(temporary)


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


def qualify(executable: Path, root: Path, native_user_root: Path | None = None) -> dict[str, Any]:
    case_home, vendor_home, project = root / "h", root / "c", root / "p"
    for directory in [case_home, vendor_home, project, root / "t"]:
        directory.mkdir()
    subprocess.run(["git", "init", "--quiet", str(project)], check=True, timeout=10)
    roots = {
        "config": vendor_home / "skills",
        "user": native_user_root
        if native_user_root is not None
        else case_home / ".agents" / "skills",
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
    child_environment = environment(root, "CODEX_HOME", vendor_home)
    requests: list[str] = []
    controls: dict[str, bool] = {}
    with (root / "stderr.log").open("wb") as errors:
        process = subprocess.Popen(
            [str(executable), "app-server", "--listen", "stdio://"],
            cwd=project,
            env=child_environment,
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
        "user_scope_fixture": (
            "native_disposable_runner_profile" if native_user_root is not None else "isolated_home"
        ),
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


@contextmanager
def installed_reader(
    executable: Path, case: installation.Installation, label: str
) -> Generator[Rpc]:
    with (case.root / label).open("wb") as errors:
        process = subprocess.Popen(
            [str(executable), "app-server", "--listen", "stdio://"],
            cwd=case.project,
            env=case.environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errors,
        )
        rpc = Rpc(process)
        try:
            rpc.initialize()
            yield rpc
        finally:
            rpc.close()


def qualify_installed(
    executable: Path, engine: Path, root: Path, engine_proof: dict[str, Any]
) -> dict[str, Any]:
    case = installation.Installation(engine, root / "i", "CODEX_HOME")
    (case.vendor_home / "config.toml").write_text(
        'cli_auth_credentials_store = "file"\n[analytics]\nenabled = false\n',
        encoding="utf-8",
    )
    name = PREFIX + "installed-codex"
    (case.source / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Controlled native installation fixture\n---\n"
        "Format only caller-supplied fixture text.\n",
        encoding="utf-8",
    )
    receipt = case.install("codex", "skill", name, "user_root")
    path = case.vendor_home / "skills" / name / "SKILL.md"
    expected = binary_digest(path)
    with installed_reader(executable, case, "reader.log") as rpc:
        data = rpc.request("skills/list", {"cwds": [str(case.project)], "forceReload": True})
        observed_paths(entries(data), name, [path])
        removal = case.remove(receipt)
        case.run(case.apply_arguments(removal), refused=True)
        assert binary_digest(path) == expected, "Active-reader refusal changed installed bytes"
    case.apply(removal)
    with installed_reader(executable, case, "restarted-reader.log") as rpc:
        data = rpc.request("skills/list", {"cwds": [str(case.project)], "forceReload": True})
        observed_paths(entries(data), name, [])
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
    with (
        tempfile.TemporaryDirectory(
            prefix="stp-codex-", dir=os.environ.get("RUNNER_TEMP")
        ) as temporary,
        native_user_scope() as native_user_root,
    ):
        root = Path(temporary)
        executable, declaration = prepare(arguments.manifest, arguments.tools, root)
        digest = binary_digest(executable)
        result = qualify(executable.resolve(), root, native_user_root)
        engine = installation.prepare(root, source)
        result["installed_configuration"] = (
            qualify_installed(executable.resolve(), engine[0], root, engine[1])
            if engine is not None
            else {"state": "not_selected"}
        )
        assert binary_digest(executable) == digest, "Vendor binary changed during qualification"
    proof = {
        "schema_version": 1,
        "source_sha": source,
        "vendor": "codex",
        "vendor_version": declaration["version"],
        "vendor_binary_sha256": digest,
        "platform": platform.system(),
        "architecture": platform.machine(),
        "release_authorized": False,
        **result,
    }
    arguments.proof.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
