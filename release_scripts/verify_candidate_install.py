"""Install and execute only the exact internal wheels from a release candidate.

The public index remains available for third-party dependencies, as it will be
for a real user install. Every ``ai-stp-*`` distribution is passed as a direct
wheel source and its PEP 610 provenance is checked after installation; a
same-version package from an index therefore cannot make this smoke test green.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlparse

from release_scripts import build_candidate


class InstallVerificationError(RuntimeError):
    """The candidate did not install or execute as the exact verified bytes."""


def _run(arguments: Sequence[str], *, cwd: Path, environment: dict[str, str]) -> str:
    result = subprocess.run(
        arguments,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        suffix = detail[-1] if detail else "command failed without stderr"
        raise InstallVerificationError(f"{arguments[0]} failed: {suffix}")
    return result.stdout


def _artifact_rows(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    held = manifest.get("artifacts")
    if not isinstance(held, list):
        raise InstallVerificationError("candidate manifest has no artifact rows")
    rows: dict[str, dict[str, object]] = {}
    for raw in held:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            raise InstallVerificationError("candidate manifest has an invalid artifact row")
        row = cast(dict[str, object], raw)
        name = cast(str, row["name"])
        if name in rows:
            raise InstallVerificationError(f"candidate manifest repeats artifact: {name}")
        rows[name] = row
    return rows


def _candidate_wheels(
    directory: Path,
    evidence: build_candidate.CandidateEvidence,
) -> dict[str, Path]:
    manifest = evidence.manifest
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise InstallVerificationError("candidate manifest has no version")
    if manifest.get("dirty") is not False:
        raise InstallVerificationError("install evidence requires a clean candidate")
    expected_command = f"uv tool install ai-stp-cli=={version}"
    if manifest.get("install_command") != expected_command:
        raise InstallVerificationError("candidate manifest has no exact install command")
    if manifest.get("packages") != list(build_candidate.PUBLISHABLE):
        raise InstallVerificationError("candidate manifest package closure is incomplete")

    rows = _artifact_rows(manifest)
    wheels: dict[str, Path] = {}
    for package in build_candidate.PUBLISHABLE:
        prefix = f"{package.replace('-', '_')}-{version}-"
        matches = [name for name in rows if name.startswith(prefix) and name.endswith(".whl")]
        if len(matches) != 1:
            raise InstallVerificationError(f"candidate must contain one wheel for {package}")
        name = matches[0]
        path = directory / name
        row = rows[name]
        digest = evidence.digests.get(name)
        if row.get("sha256") != digest or row.get("size_bytes") != path.stat().st_size:
            raise InstallVerificationError(f"candidate manifest does not describe {name}")
        wheels[package] = path.resolve()
    return wheels


def _direct_wheel_provenance(tool_root: Path, wheels: dict[str, Path]) -> dict[str, str]:
    site_packages = [
        *tool_root.glob("ai-stp-cli/lib/python*/site-packages"),
        *tool_root.glob("ai-stp-cli/Lib/site-packages"),
    ]
    if len(site_packages) != 1:
        raise InstallVerificationError("installed tool has no unique site-packages directory")
    observed: dict[str, str] = {}
    for package, wheel in wheels.items():
        stem = package.replace("-", "_")
        records = list(site_packages[0].glob(f"{stem}-*.dist-info/direct_url.json"))
        if len(records) != 1:
            raise InstallVerificationError(f"installed {package} has no unique direct provenance")
        try:
            document = json.loads(records[0].read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise InstallVerificationError(
                f"installed {package} provenance is unreadable"
            ) from error
        if not isinstance(document, dict) or not isinstance(document.get("url"), str):
            raise InstallVerificationError(f"installed {package} provenance has no URL")
        parsed = urlparse(cast(str, document["url"]))
        source: Path | None = None
        if parsed.scheme == "file":
            # On Windows file URLs, urlparse yields "/C:/Users/..." — strip the
            # leading slash so Path.resolve() matches the local wheel path.
            path_text = unquote(parsed.path)
            if (
                os.name == "nt"
                and len(path_text) >= 3
                and path_text[0] == "/"
                and path_text[2] == ":"
            ):
                path_text = path_text[1:]
            source = Path(path_text).resolve()
        archive = document.get("archive_info")
        expected_hash = "sha256=" + hashlib.sha256(wheel.read_bytes()).hexdigest()
        if source != wheel or not isinstance(archive, dict):
            raise InstallVerificationError(f"installed {package} did not come from the exact wheel")
        reported_hash = archive.get("hash")
        if reported_hash is not None and reported_hash != expected_hash:
            raise InstallVerificationError(f"installed {package} provenance has a wrong hash")
        observed[package] = expected_hash.removeprefix("sha256=")
    return observed


def _machine_answer(
    executable: Path,
    arguments: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> dict[str, object]:
    raw = _run((str(executable), *arguments, "--json"), cwd=cwd, environment=environment)
    label = " ".join(arguments)
    try:
        answer = json.loads(raw)
    except json.JSONDecodeError as error:
        raise InstallVerificationError(
            f"installed CLI returned invalid JSON for {label}"
        ) from error
    if not isinstance(answer, dict) or answer.get("ok") is not True:
        raise InstallVerificationError(f"installed CLI failed its {label} smoke")
    return cast(dict[str, object], answer)


def _require_python_version(actual: str, expected: str | None) -> None:
    """Accept an exact version or one patch release under a requested major.minor."""
    if expected is None:
        return
    if actual == expected or actual.startswith(expected + "."):
        return
    raise InstallVerificationError(f"installed CLI uses Python {actual!r}, expected {expected!r}")


def verify_install(
    directory: Path,
    *,
    expected_version: str | None,
    expected_sha: str | None,
    expected_python: str | None,
    python: str,
    network_report: Path | None = None,
) -> dict[str, object]:
    """Verify evidence, install direct wheels, execute outside the checkout and uninstall."""
    if not python:
        raise InstallVerificationError("Python selector must not be empty")
    directory = directory.resolve()
    evidence = build_candidate.verify_candidate_evidence(directory)
    version = evidence.manifest.get("version")
    git_sha = evidence.manifest.get("git_sha")
    if expected_version is not None and version != expected_version:
        raise InstallVerificationError(
            f"candidate version is {version!r}, expected {expected_version!r}"
        )
    if expected_sha is not None and git_sha != expected_sha:
        raise InstallVerificationError(f"candidate SHA is {git_sha!r}, expected {expected_sha!r}")
    wheels = _candidate_wheels(directory, evidence)
    uv = shutil.which("uv")
    if uv is None:
        raise InstallVerificationError("uv is required to verify candidate installation")

    with tempfile.TemporaryDirectory(prefix="ai-stp-candidate-install-") as held:
        root = Path(held)
        tool_root = root / "tools"
        bin_root = root / "bin"
        environment = {
            **os.environ,
            "UV_TOOL_DIR": str(tool_root),
            "UV_TOOL_BIN_DIR": str(bin_root),
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"),
            "XDG_STATE_HOME": str(root / "state"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "AI_STP_FORCE_FILE_CREDENTIAL_STORE": "1",
            "PYTHONNOUSERSITE": "1",
        }
        cli_wheel = wheels["ai-stp-cli"]
        internal = [wheels[name] for name in build_candidate.PUBLISHABLE if name != "ai-stp-cli"]
        install: list[str] = [uv, "tool", "install", "--no-config", "--python", python]
        for wheel in internal:
            install.extend(("--with", str(wheel)))
        install.append(str(cli_wheel))
        _run(install, cwd=root, environment=environment)

        executable = bin_root / ("ai-stp.exe" if os.name == "nt" else "ai-stp")
        version_answer = _machine_answer(
            executable, ("version",), cwd=root, environment=environment
        )
        data = version_answer.get("data")
        if not isinstance(data, dict) or data.get("cli_version") != version:
            raise InstallVerificationError("installed CLI version does not match the candidate")
        python_version = data.get("python_version")
        if not isinstance(python_version, str) or not python_version:
            raise InstallVerificationError("installed CLI did not report its Python version")
        _require_python_version(python_version, expected_python)
        _machine_answer(executable, ("capabilities",), cwd=root, environment=environment)
        _machine_answer(executable, ("help", "--agent"), cwd=root, environment=environment)
        if network_report is not None:
            network_answer = _machine_answer(
                executable, ("provider", "network"), cwd=root, environment=environment
            )
            network_report = network_report.resolve()
            network_report.parent.mkdir(parents=True, exist_ok=True)
            network_report.write_text(
                json.dumps(network_answer, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        provenance = _direct_wheel_provenance(tool_root, wheels)

        # Re-read every checksum after installation so a concurrent replacement
        # cannot turn a verified pre-install snapshot into false evidence.
        after = build_candidate.verify_candidate_evidence(directory)
        if after.identity != evidence.identity or after.digests != evidence.digests:
            raise InstallVerificationError("candidate changed during installation verification")
        _run(
            (uv, "tool", "uninstall", "--no-config", "ai-stp-cli"),
            cwd=root,
            environment=environment,
        )
        if executable.exists():
            raise InstallVerificationError("candidate executable remained after uninstall")

    return {
        "schema_version": 1,
        "version": version,
        "git_sha": git_sha,
        "os": platform.system().lower(),
        "architecture": platform.machine().lower(),
        "python_version": python_version,
        "wheels": provenance,
        "installed": True,
        "uninstalled": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--expected-version")
    parser.add_argument("--expected-sha")
    parser.add_argument(
        "--expected-python",
        help="Expected installed Python version or major.minor prefix.",
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--network-report",
        type=Path,
        help="Write provider-network evidence from the exact installed candidate before removal.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    try:
        report = verify_install(
            options.candidate,
            expected_version=options.expected_version,
            expected_sha=options.expected_sha,
            expected_python=options.expected_python,
            python=options.python,
            network_report=options.network_report,
        )
    except (build_candidate.CandidateError, InstallVerificationError, OSError) as error:
        print(f"candidate-install: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
