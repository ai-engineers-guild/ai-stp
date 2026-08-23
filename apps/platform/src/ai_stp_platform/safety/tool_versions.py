"""Stable tool-version evidence without another subprocess per check."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_EXTERNAL = {
    "bandit",
    "bwrap",
    "cargo",
    "clamscan",
    "eslint",
    "gitleaks",
    "gosec",
    "govulncheck",
    "npm",
    "opengrep",
    "osv-scanner",
    "pip-audit",
    "shellcheck",
    "skill-scanner",
    "yara",
}


@lru_cache(maxsize=1)
def installed_versions() -> dict[str, str]:
    path = Path(os.environ.get("AI_STP_SAFETY_TOOL_MANIFEST", "/opt/safety-bin/MANIFEST.txt"))
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    versions: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key in _EXTERNAL and value:
            versions[key] = value[:64]
    return versions


def evidence_version(tool_name: str, *, policy_version: str) -> str:
    names = [name for name in tool_name.split("+") if name]
    if not names:
        return f"policy:{policy_version}"
    versions = installed_versions()
    resolved = [
        f"{name}:{versions.get(name, 'unavailable')}"
        if name in _EXTERNAL
        else f"{name}:{policy_version}"
        for name in names
    ]
    return "+".join(resolved)[:64]
