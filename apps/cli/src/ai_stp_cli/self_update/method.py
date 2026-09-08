"""How this `ai-stp-cli` installation is owned (`SPEC-072` REQ-7205)."""

from __future__ import annotations

import hashlib
import json
import sys
import tomllib
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.paths import redact_home
from ai_stp_cli.runtime import DISTRIBUTION, cli_version
from ai_stp_contracts.machine_help import CliInstallMethod

_RECEIPT_NAME: Final[str] = "uv-receipt.toml"


@dataclass(frozen=True)
class Installation:
    method: CliInstallMethod
    executable: Path
    prefix: Path
    python: Path
    version: str
    receipt: Path | None
    apply_ready: bool
    reason: str


def current_installation(
    *,
    prefix: Path | None = None,
    executable: Path | None = None,
    python: Path | None = None,
) -> Installation:
    """Classify the running distribution without guessing from INSTALLER alone."""
    held_prefix = (prefix or Path(sys.prefix)).resolve()
    held_python = (python or Path(sys.executable)).resolve()
    held_executable = (executable or _argv_executable()).resolve()
    version = cli_version()
    receipt = held_prefix / _RECEIPT_NAME
    if receipt.is_file() and not receipt.is_symlink():
        return Installation(
            method="uv_tool",
            executable=held_executable,
            prefix=held_prefix,
            python=held_python,
            version=version,
            receipt=receipt,
            apply_ready=True,
            reason="uv tool environment with a receipt",
        )
    pipx_receipt = held_prefix / "pipx_metadata.json"
    if _is_pipx_prefix(held_prefix):
        return Installation(
            method="pipx",
            executable=held_executable,
            prefix=held_prefix,
            python=held_python,
            version=version,
            receipt=pipx_receipt,
            apply_ready=True,
            reason="pipx managed virtual environment",
        )
    if _editable():
        return Installation(
            method="source_managed",
            executable=held_executable,
            prefix=held_prefix,
            python=held_python,
            version=version,
            receipt=None,
            apply_ready=False,
            reason="editable or source checkout; not replaced by a wheel",
        )
    if held_prefix == Path(sys.base_prefix).resolve():
        method: CliInstallMethod = (
            "system_environment" if _externally_managed(held_prefix) else "shared_environment"
        )
        return Installation(
            method=method,
            executable=held_executable,
            prefix=held_prefix,
            python=held_python,
            version=version,
            receipt=None,
            apply_ready=False,
            reason="shared or system interpreter; migrate to uv tool or pipx",
        )
    if _externally_managed(held_prefix):
        return Installation(
            method="system_environment",
            executable=held_executable,
            prefix=held_prefix,
            python=held_python,
            version=version,
            receipt=None,
            apply_ready=False,
            reason="externally managed environment; migrate to uv tool or pipx",
        )
    return Installation(
        method="pip_venv",
        executable=held_executable,
        prefix=held_prefix,
        python=held_python,
        version=version,
        receipt=None,
        apply_ready=True,
        reason="dedicated virtual environment",
    )


def fingerprint(installation: Installation) -> str:
    """Identity of this prefix, not a secret and not a moving latest."""
    from ai_stp_foundation.canonical import JsonValue
    from ai_stp_foundation.digests import digest_canonical

    body: dict[str, JsonValue] = {
        "method": installation.method,
        "prefix": str(installation.prefix),
        "executable": str(installation.executable),
        "python": str(installation.python),
        "version": installation.version,
        "receipt_digest": (
            hashlib.sha256(installation.receipt.read_bytes()).hexdigest()
            if installation.receipt is not None and installation.receipt.is_file()
            else ""
        ),
    }
    return digest_canonical("ai-stp:plan:v1", body)


def display_path(path: Path) -> str:
    return redact_home(path)


def _argv_executable() -> Path:
    if sys.argv and sys.argv[0]:
        candidate = Path(sys.argv[0])
        if candidate.is_file() and candidate.name in {"ai-stp", "ai-stp.exe"}:
            return candidate
    scripts = Path(sys.prefix) / ("Scripts" if sys.platform == "win32" else "bin")
    executable = scripts / ("ai-stp.exe" if sys.platform == "win32" else "ai-stp")
    return executable


def _is_pipx_prefix(prefix: Path) -> bool:
    receipt = prefix / "pipx_metadata.json"
    if not receipt.is_file() or receipt.is_symlink():
        return False
    try:
        document = json.loads(receipt.read_text(encoding="utf-8"))
        return isinstance(document, dict) and isinstance(
            cast(dict[str, object], document).get("main_package"), dict
        )
    except (ValueError, OSError):
        return False


def installer_environment(held: Installation) -> dict[str, str]:
    """Bind the managed tool root independently of the next shell's environment."""
    if held.method == "uv_tool":
        result = {"UV_TOOL_DIR": str(held.prefix.parent)}
        if held.receipt is not None:
            try:
                receipt = tomllib.loads(held.receipt.read_text(encoding="utf-8"))
                tool = receipt.get("tool")
                entries: object = (
                    cast(dict[str, object], tool).get("entrypoints", [])
                    if isinstance(tool, dict)
                    else []
                )
                if not isinstance(entries, list):
                    entries = []
                for raw in cast(list[object], entries):
                    if not isinstance(raw, dict):
                        continue
                    entry = cast(dict[str, object], raw)
                    install_path = entry.get("install-path")
                    if entry.get("name") == "ai-stp" and isinstance(install_path, str):
                        result["UV_TOOL_BIN_DIR"] = str(Path(install_path).parent)
            except (ValueError, OSError):
                pass
        return result
    if held.method == "pipx":
        return {"PIPX_HOME": str(held.prefix.parent.parent)}
    return {}


def _externally_managed(prefix: Path) -> bool:
    marker = prefix / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    return (marker / "EXTERNALLY-MANAGED").is_file() or (prefix / "EXTERNALLY-MANAGED").is_file()


def _editable() -> bool:
    try:
        dist = distribution(DISTRIBUTION)
    except PackageNotFoundError:
        return False
    for file in dist.files or ():
        name = Path(str(file)).name
        if name.startswith("_editable") and name.endswith(".pth"):
            return True
        if name != "direct_url.json":
            continue
        direct = Path(str(dist.locate_file(file)))
        if not direct.is_file() or direct.is_symlink():
            continue
        try:
            payload = json.loads(direct.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        held = cast(dict[str, object], payload)
        info = held.get("dir_info")
        if isinstance(info, dict) and cast(dict[str, object], info).get("editable") is True:
            return True
    return False
