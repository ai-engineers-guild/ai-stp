"""Read Claude metadata and observe owned startup hooks without a model prompt."""

from __future__ import annotations

import argparse
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from . import installation
from .common import binary_digest, environment, write_skill
from .rpc import Pipe

PREFIX = "ai-stp-qualification-"


class Rpc(Pipe):
    def initialize(self) -> dict[str, Any]:
        self.input.write(
            b'{"type":"control_request","request_id":"metadata-only",'
            b'"request":{"subtype":"initialize"}}\n'
        )
        self.input.flush()
        deadline = time.monotonic() + 25
        for _ in range(256):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Claude local initialization deadline")
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError("Claude local initialization deadline") from error
            if isinstance(message, Exception):
                raise message
            document = cast(dict[str, Any], json.loads(message))
            if document.get("type") == "control_response":
                response = document["response"]
                assert response["request_id"] == "metadata-only"
                assert response["subtype"] == "success", response.get("error")
                data = cast(dict[str, Any], response["response"])
                return data
            assert document.get("type") in {"keep_alive", "system"}, (
                "Unexpected output before any user message",
                document.get("type"),
            )
        raise ValueError("Claude initialization notification bound exceeded")


def child_environment(root: Path, vendor_home: Path) -> dict[str, str]:
    result = environment(root, "CLAUDE_CONFIG_DIR", vendor_home)
    result["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    return result


@contextmanager
def reader(
    executable: Path, project: Path, variables: dict[str, str], errors: Path
) -> Generator[Rpc]:
    with errors.open("wb") as error_stream:
        process = subprocess.Popen(
            [
                str(executable),
                "--print",
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--verbose",
                "--no-session-persistence",
            ],
            cwd=project,
            env=variables,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=error_stream,
        )
        rpc = Rpc(process)
        try:
            yield rpc
        finally:
            rpc.close()


def observed(data: dict[str, Any], field: str, name: str, description: str | None) -> None:
    rows = [row for row in data[field] if row["name"] == name]
    if description is None:
        assert not rows, (field, name)
    else:
        assert len(rows) == 1, (field, name, len(rows))
        # This API exposes names/descriptions, not physical source paths.
        assert rows[0]["description"].startswith(description)


def write_agent(root: Path, name: str, description: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / (name + ".md")
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n"
        "Format only caller-supplied fixture text.\n",
        encoding="utf-8",
    )
    return path


def hook_configuration(root: Path) -> tuple[dict[str, Any], Path]:
    script, receipt = root / "hook.py", root / "hook-events.jsonl"
    script.write_text(
        "import json,sys\n"
        "from pathlib import Path\n"
        "payload=sys.stdin.buffer.read(32769)\n"
        "assert len(payload)<=32768\n"
        "data=json.loads(payload)\n"
        "assert data['hook_event_name']=='SessionStart' and data['source']=='startup'\n"
        "with Path(sys.argv[1]).open('a',encoding='utf-8') as stream:\n"
        " stream.write(json.dumps({'event':'SessionStart','source':'startup'})+'\\n')\n",
        encoding="utf-8",
    )
    return (
        {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "startup",
                        "hooks": [
                            {
                                "type": "command",
                                "command": sys.executable,
                                "args": [str(script), str(receipt)],
                                "timeout": 10,
                                "onFailure": "block",
                            }
                        ],
                    }
                ]
            }
        },
        receipt,
    )


def hook_events(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    data = path.read_bytes()
    assert len(data) <= 32768 and data.endswith(b"\n")
    rows = [json.loads(line) for line in data.split(b"\n") if line]
    assert rows and all(row == {"event": "SessionStart", "source": "startup"} for row in rows)
    return rows


def wait_hook_events(path: Path, minimum: int) -> list[dict[str, str]]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if path.exists():
            data = path.read_bytes()
            assert len(data) <= 32768
            if data and data.endswith(b"\n"):
                rows = hook_events(path)
                if len(rows) >= minimum:
                    return rows
        time.sleep(0.05)
    raise TimeoutError("Owned SessionStart hook observation deadline")


def no_credentials_or_history(vendor_home: Path) -> None:
    assert not any(
        path.name in {".credentials.json", "credentials.json", "auth.json"}
        for path in vendor_home.rglob("*")
    )
    assert not list((vendor_home / "projects").rglob("*.jsonl"))


def qualify(executable: Path, root: Path, version: str) -> dict[str, Any]:
    for name in ["h", "v", "p", "t"]:
        (root / name).mkdir()
    vendor_home, project = root / "v", root / "p"
    subprocess.run(["git", "init", "--quiet", str(project)], check=True, timeout=10)
    variables = child_environment(root, vendor_home)
    reported = subprocess.check_output(
        [str(executable), "--version"], cwd=project, env=variables, text=True, timeout=15
    )
    assert reported.strip() == version + " (Claude Code)"
    skills = {"user": vendor_home / "skills", "project": project / ".claude" / "skills"}
    agents = {"user": vendor_home / "agents", "project": project / ".claude" / "agents"}
    shadow_skill: dict[str, Path] = {}
    shadow_agent: dict[str, Path] = {}
    for scope in skills:
        write_skill(skills[scope], "unique", PREFIX + scope, "Controlled skill " + scope)
        write_agent(agents[scope], PREFIX + scope, "Controlled agent " + scope)
        shadow_skill[scope] = write_skill(
            skills[scope], "shadow", PREFIX + "shadow", "Controlled shadow skill " + scope
        )
        shadow_agent[scope] = write_agent(
            agents[scope], PREFIX + "shadow", "Controlled shadow agent " + scope
        )
    configuration, events = hook_configuration(root)
    (vendor_home / "settings.json").write_text(json.dumps(configuration), encoding="utf-8")
    controls: dict[str, bool] = {}

    def inspect(label: str, *, expect_hook: bool = True) -> dict[str, Any]:
        previous = len(hook_events(events))
        with reader(executable, project, variables, root / label) as rpc:
            data = rpc.initialize()
            if expect_hook:
                wait_hook_events(events, previous + 1)
            return data

    first = inspect("first.log")
    for scope in skills:
        observed(first, "commands", PREFIX + scope, "Controlled skill " + scope)
        observed(first, "agents", PREFIX + scope, "Controlled agent " + scope)
    controls["user_and_project_skill_discovery"] = True
    controls["user_and_project_agent_discovery"] = True
    observed(first, "commands", PREFIX + "shadow", "Controlled shadow skill project")
    observed(first, "agents", PREFIX + "shadow", "Controlled shadow agent project")
    controls["project_skill_and_agent_shadow_wins"] = True

    shadow_skill["project"].unlink()
    shadow_agent["project"].unlink()
    second = inspect("refreshed.log")
    observed(second, "commands", PREFIX + "shadow", "Controlled shadow skill user")
    observed(second, "agents", PREFIX + "shadow", "Controlled shadow agent user")
    for scope in skills:
        observed(second, "commands", PREFIX + scope, "Controlled skill " + scope)
        observed(second, "agents", PREFIX + scope, "Controlled agent " + scope)
    controls["removed_project_layers_fall_back_to_user"] = True
    observations = hook_events(events)
    assert observations, "Actual SessionStart hook did not execute"
    controls["configured_startup_hook_executes_without_prompt"] = True

    (vendor_home / "settings.json").unlink()
    inspect("hook-removed.log", expect_hook=False)
    assert hook_events(events) == observations, "Removed hook executed again"
    controls["removed_hook_does_not_execute_after_restart"] = True
    no_credentials_or_history(vendor_home)
    controls["no_login_credentials_or_session_history"] = True
    assert len(controls) == 7 and all(controls.values())
    return {
        "controls": controls,
        "evidence_kind": "vendor_configuration_read",
        "request_types": ["initialize"],
        "user_messages_sent": 0,
        "inference_turns_started": 0,
        "user_scope_fixture": "disposable_hosted_user",
        "hook_dispatch": {
            "state": "observed",
            "evidence_kind": "vendor_hook_dispatch",
            "event": "SessionStart",
            "source": "startup",
            "observations": len(observations),
            "removed_hook_does_not_execute": True,
        },
    }


def prepare(distribution: Path, root: Path) -> tuple[Path, str]:
    sdk = root / "sdk"
    sdk.mkdir()
    for name in ["package.json", "bun.lock"]:
        shutil.copyfile(distribution / name, sdk / name)
    declaration = json.loads((sdk / "package.json").read_text())
    version = cast(str, declaration["dependencies"]["@anthropic-ai/claude-code"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    subprocess.run(
        ["bun", "install", "--frozen-lockfile", "--ignore-scripts", "--cwd", str(sdk)],
        check=True,
        timeout=180,
    )
    system, architecture, filename = {
        "Linux": ("linux", "x64", "claude"),
        "Darwin": ("darwin", "arm64", "claude"),
        "Windows": ("win32", "x64", "claude.exe"),
    }[platform.system()]
    name = f"@anthropic-ai/claude-code-{system}-{architecture}"
    package = sdk / "node_modules" / name
    metadata = json.loads((package / "package.json").read_text())
    assert metadata["name"] == name and metadata["version"] == version
    executable = package / filename
    assert executable.is_file() and 0 < executable.stat().st_size < 1024 * 1024 * 1024
    executable.chmod(0o700)
    return executable, version


def qualify_installed_skill(
    executable: Path, engine: Path, root: Path, engine_proof: dict[str, Any]
) -> dict[str, Any]:
    case = installation.Installation(engine, root / "i-skill", "CLAUDE_CONFIG_DIR")
    case.environment["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    name = PREFIX + "installed-claude"
    description = "Controlled native installation fixture"
    (case.source / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n"
        "Format only caller-supplied fixture text.\n",
        encoding="utf-8",
    )
    receipt = case.install("claude-code", "skill", name, "global")
    path = case.vendor_home / "skills" / name / "SKILL.md"
    expected = binary_digest(path)
    with reader(executable, case.project, case.environment, case.root / "reader.log") as rpc:
        observed(rpc.initialize(), "commands", name, description)
        removal = case.remove(receipt)
        case.run(case.apply_arguments(removal), refused=True)
        assert binary_digest(path) == expected, "Active-reader refusal changed installed bytes"
    case.apply(removal)
    with reader(executable, case.project, case.environment, case.root / "restarted.log") as rpc:
        observed(rpc.initialize(), "commands", name, None)
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


def qualify_installed_hook(
    executable: Path, engine: Path, root: Path, engine_proof: dict[str, Any]
) -> dict[str, Any]:
    case = installation.Installation(engine, root / "i-hook", "CLAUDE_CONFIG_DIR")
    case.environment["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    configuration, events = hook_configuration(case.root)
    (case.source / "settings.json").write_text(json.dumps(configuration), encoding="utf-8")
    receipt = case.install("claude-code", "hook", PREFIX + "installed-hook", "global")
    path = case.vendor_home / "settings.json"
    expected = binary_digest(path)
    with reader(executable, case.project, case.environment, case.root / "reader.log") as rpc:
        rpc.initialize()
        observations = wait_hook_events(events, 1)
        removal = case.remove(receipt)
        case.run(case.apply_arguments(removal), refused=True)
        assert binary_digest(path) == expected
    case.apply(removal)
    with reader(executable, case.project, case.environment, case.root / "restarted.log") as rpc:
        rpc.initialize()
    assert not path.exists() and hook_events(events) == observations
    case.removed()
    return {
        "state": "passed",
        "evidence_kind": "native_engine_vendor_hook_dispatch",
        "engine": engine_proof,
        "install_and_remove_receipts_idempotent": True,
        "original_context_preserved_across_selected_view": True,
        "hook_event": "SessionStart",
        "hook_source": "startup",
        "observations": len(observations),
        "active_reader_refusal_preserves_bytes": True,
        "original_removal_after_reader_exit": True,
        "removed_hook_does_not_execute_after_restart": True,
        "unowned_preserved_and_pending_cleared": True,
        "user_messages_sent": 0,
        "inference_turns_started": 0,
        "usage_ingestion": "not_selected",
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
    with tempfile.TemporaryDirectory(
        prefix="stp-claude-", dir=os.environ["RUNNER_TEMP"]
    ) as temporary:
        root = Path(temporary)
        executable, version = prepare(arguments.distribution, root)
        digest = binary_digest(executable)
        result = qualify(executable.resolve(), root, version)
        engine = installation.prepare(root, source)
        result["installed_configuration"] = (
            qualify_installed_skill(executable.resolve(), engine[0], root, engine[1])
            if engine is not None
            else {"state": "not_selected"}
        )
        result["installed_hook"] = (
            qualify_installed_hook(executable.resolve(), engine[0], root, engine[1])
            if engine is not None
            else {"state": "not_selected"}
        )
        assert binary_digest(executable) == digest, "Vendor binary changed during qualification"
    proof = {
        "schema_version": 1,
        "source_sha": source,
        "vendor": "claude-code",
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
