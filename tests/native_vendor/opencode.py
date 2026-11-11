"""Read OpenCode 2.x skills through an owned local server without model messages."""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import platform
import queue
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from . import installation
from .common import binary_digest, environment, write_skill
from .rpc import Pipe

PREFIX = "ai-stp-qualification-"


def isolated_sources(project: Path) -> None:
    """Refuse inherited sources; neither managed policy nor ancestor plugins are bypassed."""
    system = {
        "Linux": Path("/etc/opencode"),
        "Darwin": Path("/Library/Application Support/opencode"),
        "Windows": Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "opencode",
    }[platform.system()]
    assert not system.exists() and not system.is_symlink(), "Unexpected managed OpenCode source"
    if platform.system() == "Darwin":
        managed = Path("/Library/Managed Preferences")
        for path in [managed, managed / getpass.getuser()]:
            assert not (path / "ai.opencode.managed.plist").exists()
    for ancestor in project.parents:
        for name in ["opencode.json", "opencode.jsonc", ".opencode", ".agents", ".claude"]:
            candidate = ancestor / name
            assert not candidate.is_symlink(), "Unexpected ancestor source link"
            if not candidate.exists():
                continue
            # Earlier hosted readers may leave empty namespace directories.
            assert candidate.is_dir(), "Unexpected ancestor configuration"
            for index, child in enumerate(candidate.rglob("*")):
                assert index < 256 and child.is_dir() and not child.is_symlink(), (
                    "Unexpected ancestor configuration content"
                )


def variables(root: Path, vendor_home: Path) -> dict[str, str]:
    result = environment(root, "OPENCODE_CONFIG_DIR", vendor_home)
    result.update(
        {
            "XDG_STATE_HOME": str(root / "h" / ".local" / "state"),
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
            "OPENCODE_DISABLE_MODELS_FETCH": "1",
            "OPENCODE_DISABLE_PRUNE": "1",
            "DO_NOT_TRACK": "1",
            "OTEL_SDK_DISABLED": "true",
        }
    )
    return result


class Server(Pipe):
    def ready(self, project: Path, password: str, version: str) -> None:
        try:
            line = self.messages.get(timeout=30)
        except queue.Empty as error:
            raise TimeoutError("OpenCode private server startup deadline") from error
        if isinstance(line, Exception):
            raise line
        document = cast(dict[str, Any], json.loads(line))
        address = document["url"]
        assert isinstance(address, str)
        url = urllib.parse.urlparse(address)
        assert url.scheme == "http" and url.hostname == "127.0.0.1"
        assert url.port is not None and url.username is None and url.password is None
        assert url.path in {"", "/"} and not url.query and not url.fragment
        self.url = address.rstrip("/")
        self.project = project
        self.authorization = "Basic " + base64.b64encode(("opencode:" + password).encode()).decode()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        identity = self.get("/api/info")
        assert identity["version"] == version, identity["version"]
        assert identity["pid"] == self.process.pid, "Server is not the owned child"

    def get(self, endpoint: str) -> Any:
        assert endpoint in {"/api/info", "/api/skill", "/api/plugin"}
        query = (
            ""
            if endpoint == "/api/info"
            else "?" + urllib.parse.urlencode({"location[directory]": str(self.project)})
        )
        request = urllib.request.Request(
            self.url + endpoint + query,
            headers={"Authorization": self.authorization},
            method="GET",
        )
        with self.opener.open(request, timeout=10) as response:
            assert response.status == 200
            data = response.read(2 * 1024 * 1024 + 1)
        assert len(data) <= 2 * 1024 * 1024, "OpenCode metadata response bound exceeded"
        result = json.loads(data)
        if endpoint == "/api/info":
            return result
        assert Path(result["location"]["directory"]).samefile(self.project)
        return result["data"]

    def skills(self) -> list[dict[str, Any]]:
        # The vendor catalog is asynchronous; follow its documented plugin readiness.
        deadline = time.monotonic() + 10
        while True:
            plugins = self.get("/api/plugin")
            required = {"opencode.config.skill", "opencode.config.compatibility"}
            if required <= {row.get("id") for row in plugins}:
                assert all(row["state"]["status"] == "active" for row in plugins)
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("OpenCode location plugin activation deadline")
            time.sleep(0.025)
        return cast(list[dict[str, Any]], self.get("/api/skill"))


@contextmanager
def reader(
    executable: Path, project: Path, child_environment: dict[str, str], errors: Path, version: str
) -> Generator[Server]:
    isolated_sources(project)
    password = secrets.token_urlsafe(32)
    with errors.open("wb") as error_stream:
        process = subprocess.Popen(
            [str(executable), "serve", "--stdio", "--hostname", "127.0.0.1", "--port", "0"],
            cwd=project,
            env={**child_environment, "OPENCODE_PASSWORD": password},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=error_stream,
        )
        server = Server(process)
        try:
            server.ready(project, password, version)
            yield server
        finally:
            server.close()


def observed(rows: list[dict[str, Any]], identifier: str, path: Path | None) -> None:
    selected = [row for row in rows if row["id"] == identifier]
    assert len(selected) == (0 if path is None else 1), (identifier, len(selected))
    if path is not None:
        assert Path(selected[0]["path"]).samefile(path), identifier


def qualify(executable: Path, root: Path, version: str) -> dict[str, Any]:
    home, vendor_home, project = root / "h", root / "v", root / "p"
    for directory in [home, vendor_home, project, root / "t"]:
        directory.mkdir()
    subprocess.run(["git", "init", "--quiet", str(project)], check=True, timeout=10)
    roots = {
        "config": vendor_home / "skills",
        "user": home / ".agents" / "skills",
        "project": project / ".opencode" / "skills",
    }
    unique = {
        scope: write_skill(path, PREFIX + scope, PREFIX + "display-" + scope, "Controlled " + scope)
        for scope, path in roots.items()
    }
    shadow = {
        scope: write_skill(path, PREFIX + "shadow", PREFIX + "display-" + scope, "Shadow " + scope)
        for scope, path in roots.items()
    }
    malformed = write_skill(roots["config"], PREFIX + "malformed", PREFIX + "malformed", "Invalid")
    malformed.write_text("---\nname: 123\n---\nControlled malformed fixture.\n", encoding="utf-8")
    child_environment = variables(root, vendor_home)
    isolated_sources(project)
    controls: dict[str, bool] = {}

    def inspect(label: str, extra: dict[str, str] | None = None) -> list[dict[str, Any]]:
        with reader(
            executable, project, {**child_environment, **(extra or {})}, root / label, version
        ) as server:
            return server.skills()

    first = inspect("initial.log")
    controls["exact_version_and_owned_server_pid"] = True
    for scope, path in unique.items():
        observed(first, PREFIX + scope, path)
        row = next(row for row in first if row["id"] == PREFIX + scope)
        assert row["name"] == PREFIX + "display-" + scope
    controls["three_scopes_and_path_identity"] = True
    observed(first, PREFIX + "shadow", shadow["project"])
    controls["project_shadow_wins"] = True
    observed(first, PREFIX + "malformed", None)
    controls["malformed_frontmatter_not_loaded"] = True

    restricted = inspect("project-disabled.log", {"OPENCODE_CONFIG_PROJECT_DISABLE": "1"})
    observed(restricted, PREFIX + "project", None)
    observed(restricted, PREFIX + "config", unique["config"])
    observed(restricted, PREFIX + "user", unique["user"])
    observed(restricted, PREFIX + "shadow", shadow["config"])
    controls["disabled_project_sources_excluded"] = True

    shadow["project"].unlink()
    fallback = inspect("global-fallback.log")
    observed(fallback, PREFIX + "shadow", shadow["config"])
    controls["removed_project_shadow_falls_back_to_config"] = True
    shadow["config"].unlink()
    unique["project"].unlink()
    refreshed = inspect("user-fallback.log")
    observed(refreshed, PREFIX + "shadow", shadow["user"])
    observed(refreshed, PREFIX + "project", None)
    for scope in ["config", "user"]:
        observed(refreshed, PREFIX + scope, unique[scope])
    controls["removed_config_shadow_falls_back_to_user"] = True
    assert not any(path.name in {"auth.json", "credentials.json"} for path in root.rglob("*"))
    controls["no_login_artifact"] = True
    return {
        "controls": controls,
        "evidence_kind": "vendor_configuration_read",
        "commands": ["serve --stdio --hostname 127.0.0.1 --port 0"],
        "read_only_endpoints": ["/api/info", "/api/plugin", "/api/skill"],
        "user_scope_fixture": "disposable_hosted_user",
        "user_messages_sent": 0,
        "inference_turns_started": 0,
    }


def prepare(distribution: Path, root: Path) -> tuple[Path, str]:
    sdk = root / "sdk"
    sdk.mkdir()
    for name in ["package.json", "bun.lock"]:
        shutil.copyfile(distribution / name, sdk / name)
    declaration = json.loads((sdk / "package.json").read_text())
    version = cast(str, declaration["dependencies"]["@opencode/cli"])
    assert re.fullmatch(r"2\.\d+\.\d+", version)
    subprocess.run(
        ["bun", "install", "--frozen-lockfile", "--ignore-scripts", "--cwd", str(sdk)],
        check=True,
        timeout=180,
    )
    system, architecture, filename = {
        "Linux": ("linux", "x64", "opencode"),
        "Darwin": ("darwin", "arm64", "opencode"),
        "Windows": ("windows", "x64", "opencode.exe"),
    }[platform.system()]
    name = f"@opencode/cli-{system}-{architecture}"
    package = sdk / "node_modules" / name
    metadata = json.loads((package / "package.json").read_text())
    assert metadata["name"] == name and metadata["version"] == version
    executable = package / "bin" / filename
    assert executable.is_file() and 0 < executable.stat().st_size < 1024 * 1024 * 1024
    executable.chmod(0o700)
    return executable, version


def qualify_installed(
    executable: Path, engine: Path, root: Path, engine_proof: dict[str, Any], version: str
) -> dict[str, Any]:
    case = installation.Installation(engine, root / "i", "OPENCODE_CONFIG_DIR")
    case.environment.update(variables(case.root, case.vendor_home))
    name = PREFIX + "installed-opencode"
    (case.source / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Controlled native installation fixture\n---\n"
        "Format only caller-supplied fixture text.\n",
        encoding="utf-8",
    )
    receipt = case.install("opencode", "skill", name, "global")
    path = case.vendor_home / "skills" / name / "SKILL.md"
    expected = binary_digest(path)
    with reader(
        executable, case.project, case.environment, case.root / "reader.log", version
    ) as server:
        observed(server.skills(), name, path)
        removal = case.remove(receipt)
        case.run(case.apply_arguments(removal), refused=True)
        assert binary_digest(path) == expected, "Active-reader refusal changed installed bytes"
    case.apply(removal)
    with reader(
        executable, case.project, case.environment, case.root / "restarted.log", version
    ) as server:
        observed(server.skills(), name, None)
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
        "user_messages_sent": 0,
        "inference_turns_started": 0,
    }


def main() -> None:
    installation.disposable_runner()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    arguments = parser.parse_args()
    source = os.environ["AI_STP_NATIVE_VENDOR_SOURCE"]
    assert re.fullmatch(r"[0-9a-f]{40}", source)
    architectures = {"Linux": "x86_64", "Darwin": "arm64", "Windows": "amd64"}
    assert platform.machine().lower() == architectures[platform.system()]
    with tempfile.TemporaryDirectory(prefix="stp-opencode-", dir=os.environ["RUNNER_TEMP"]) as raw:
        root = Path(raw)
        executable, version = prepare(arguments.distribution, root)
        digest = binary_digest(executable)
        result = qualify(executable.resolve(), root, version)
        engine = installation.prepare(root, source)
        result["installed_configuration"] = (
            qualify_installed(executable.resolve(), engine[0], root, engine[1], version)
            if engine is not None
            else {"state": "not_selected"}
        )
        assert binary_digest(executable) == digest, "Vendor binary changed during qualification"
    proof = {
        "schema_version": 1,
        "source_sha": source,
        "vendor": "opencode",
        "vendor_version": version,
        "vendor_binary_sha256": digest,
        "distribution_lock_sha256": binary_digest(arguments.distribution / "bun.lock"),
        "platform": platform.system(),
        "architecture": platform.machine(),
        "release_authorized": False,
        **result,
    }
    arguments.proof.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
