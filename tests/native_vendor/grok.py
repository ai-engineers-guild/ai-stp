"""Read actual Grok configuration without starting an inference session."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

from .common import binary_digest, environment, native_user_scope, write_skill

PREFIX = "ai-stp-qualification-"


def inspect(
    executable: Path, project: Path, child_environment: dict[str, str], *, trust: bool = False
) -> dict[str, Any]:
    command = [str(executable), "--cwd", str(project)]
    if trust:
        command.append("--trust")
    command.extend(["inspect", "--json"])
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        subprocess.run(
            command,
            cwd=project,
            env=child_environment,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=errors,
            check=True,
            timeout=30,
        )
        assert output.tell() <= 2 * 1024 * 1024, "Grok inspection output bound exceeded"
        output.seek(0)
        return cast(dict[str, Any], json.load(output))


def skill_paths(result: dict[str, Any], name: str) -> list[Path]:
    return [Path(skill["source"]["path"]) for skill in result["skills"] if skill["name"] == name]


def observed_skill(result: dict[str, Any], name: str, expected: Path | None) -> None:
    paths = skill_paths(result, name)
    assert len(paths) == (0 if expected is None else 1), (name, len(paths))
    if expected is not None:
        assert paths[0].samefile(expected), name


def mcp_target(result: dict[str, Any]) -> str:
    rows = [server for server in result["mcpServers"] if server["name"] == PREFIX + "mcp"]
    assert len(rows) == 1 and rows[0]["transport"] == "stdio"
    return cast(str, rows[0]["target"])


def qualify(executable: Path, root: Path, native_user_root: Path | None = None) -> dict[str, Any]:
    home, vendor_home, project = root / "h", root / "g", root / "p"
    for directory in [home, vendor_home, project, root / "t"]:
        directory.mkdir()
    subprocess.run(["git", "init", "--quiet", str(project)], check=True, timeout=10)
    roots = {
        "config": vendor_home / "skills",
        "user": native_user_root if native_user_root is not None else home / ".agents" / "skills",
        "project": project / ".grok" / "skills",
    }
    unique = {
        scope: write_skill(path, "unique", PREFIX + scope, "Controlled " + scope + " discovery")
        for scope, path in roots.items()
    }
    instructions = [vendor_home / "AGENTS.md", project / "AGENTS.md"]
    for path in instructions:
        path.write_text("Format only caller-supplied fixture text.\n", encoding="utf-8")
    global_config, project_config = vendor_home / "config.toml", project / ".grok" / "config.toml"
    for path, scope in [(global_config, "global"), (project_config, "project")]:
        path.write_text(
            f'[mcp_servers."{PREFIX}mcp"]\ncommand = "__ai_stp_fixture_{scope}__"\n',
            encoding="utf-8",
        )
    child_environment = environment(root, "GROK_HOME", vendor_home)
    child_environment["GROK_DISABLE_AUTOUPDATER"] = "1"
    controls: dict[str, bool] = {}
    initial = inspect(executable, project, child_environment)
    assert initial["projectTrusted"] is False
    observed_skill(initial, PREFIX + "project", None)
    assert not any(
        Path(row["path"]).samefile(instructions[1]) for row in initial["projectInstructions"]
    )
    controls["untrusted_project_skills_and_instructions_excluded"] = True

    trusted = inspect(executable, project, child_environment, trust=True)
    assert trusted["projectTrusted"] is True
    for scope, path in unique.items():
        observed_skill(trusted, PREFIX + scope, path)
    for path in instructions:
        assert any(Path(row["path"]).samefile(path) for row in trusted["projectInstructions"])
    assert mcp_target(trusted) == "__ai_stp_fixture_project__"
    controls["trusted_three_scopes_and_instructions"] = True

    shadow = {
        scope: write_skill(path, "shadow", PREFIX + "shadow", "Controlled shadow " + scope)
        for scope, path in roots.items()
    }
    repeated = inspect(executable, project, child_environment)
    assert repeated["projectTrusted"] is True
    observed_skill(repeated, PREFIX + "shadow", shadow["project"])
    controls["trust_persists_and_project_shadow_wins"] = True

    unique["project"].unlink()
    shadow["project"].unlink()
    project_config.unlink()
    refreshed = inspect(executable, project, child_environment)
    observed_skill(refreshed, PREFIX + "project", None)
    for scope in ["config", "user"]:
        observed_skill(refreshed, PREFIX + scope, unique[scope])
    remaining_shadow = skill_paths(refreshed, PREFIX + "shadow")
    assert len(remaining_shadow) == 2
    for scope in ["config", "user"]:
        assert sum(path.samefile(shadow[scope]) for path in remaining_shadow) == 1
    controls["fresh_read_removes_only_absent_project_skills"] = True
    assert mcp_target(refreshed) == "__ai_stp_fixture_global__"
    controls["removed_project_mcp_falls_back_to_global"] = True
    assert not any(
        path.name in {"auth.json", "credentials.json"} for path in vendor_home.rglob("*")
    )
    controls["no_login_artifact"] = True
    assert len(controls) == 6 and all(controls.values())
    return {
        "controls": controls,
        "evidence_kind": "vendor_configuration_read",
        "commands": ["inspect --json", "--trust inspect --json"],
        "inference_turns_started": 0,
        "user_scope_fixture": (
            "native_disposable_runner_profile" if native_user_root is not None else "isolated_home"
        ),
    }


def prepare(distribution: Path, root: Path) -> tuple[Path, str]:
    sdk = root / "sdk"
    sdk.mkdir()
    for name in ["package.json", "bun.lock"]:
        shutil.copyfile(distribution / name, sdk / name)
    declaration = json.loads((sdk / "package.json").read_text())
    version = cast(str, declaration["dependencies"]["@xai-official/grok"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    subprocess.run(
        ["bun", "install", "--frozen-lockfile", "--ignore-scripts", "--cwd", str(sdk)],
        check=True,
        timeout=120,
    )
    operating_system, architecture, filename = {
        "Linux": ("linux", "x64", "grok"),
        "Darwin": ("darwin", "arm64", "grok"),
        "Windows": ("win32", "x64", "grok.exe"),
    }[platform.system()]
    package_name = f"@xai-official/grok-{operating_system}-{architecture}"
    package = sdk / "node_modules" / package_name
    metadata = json.loads((package / "package.json").read_text())
    assert metadata["name"] == package_name and metadata["version"] == version
    compressed = package / "bin" / (filename + ".br")
    assert compressed.is_file() and 0 < compressed.stat().st_size < 1024 * 1024 * 1024
    executable = root / filename
    # Extract data only. Vendor installation scripts and launcher downloads never execute.
    subprocess.run(
        [
            "bun",
            "--eval",
            'const fs=require("node:fs"),z=require("node:zlib");'
            "const body=z.brotliDecompressSync(fs.readFileSync(process.env.AI_STP_SDK_INPUT),"
            "{maxOutputLength:1024*1024*1024});"
            'fs.writeFileSync(process.env.AI_STP_SDK_OUTPUT,body,{mode:0o700,flag:"wx"});',
        ],
        env={
            **os.environ,
            "AI_STP_SDK_INPUT": str(compressed),
            "AI_STP_SDK_OUTPUT": str(executable),
        },
        check=True,
        timeout=30,
    )
    assert 0 < executable.stat().st_size < 1024 * 1024 * 1024
    executable.chmod(0o700)
    reported = subprocess.check_output(
        [str(executable), "--version"],
        env={**os.environ, "GROK_DISABLE_AUTOUPDATER": "1"},
        text=True,
        timeout=15,
    )
    assert reported.strip().startswith(f"grok {version} (")
    return executable, version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    arguments = parser.parse_args()
    source = os.environ["AI_STP_NATIVE_VENDOR_SOURCE"]
    assert re.fullmatch(r"[0-9a-f]{40}", source)
    expected_architecture = {"Linux": "x86_64", "Darwin": "arm64", "Windows": "amd64"}
    assert platform.machine().lower() == expected_architecture[platform.system()]
    with (
        tempfile.TemporaryDirectory(
            prefix="stp-grok-", dir=os.environ.get("RUNNER_TEMP")
        ) as temporary,
        native_user_scope("grok") as native_user_root,
    ):
        root = Path(temporary)
        executable, version = prepare(arguments.distribution, root)
        digest = binary_digest(executable)
        result = qualify(executable.resolve(), root, native_user_root)
        assert binary_digest(executable) == digest, "Vendor binary changed during qualification"
    proof = {
        "schema_version": 1,
        "source_sha": source,
        "vendor": "grok-build",
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
