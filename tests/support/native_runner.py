"""Admission for fixtures that mutate disposable native OS user state."""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path


def disposable_runner() -> None:
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Native fixtures require hosted CI"
    assert os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
    assert (
        os.environ.get("RUNNER_OS")
        == {
            "Linux": "Linux",
            "Darwin": "macOS",
            "Windows": "Windows",
        }[platform.system()]
    )
    assert os.environ.get("RUNNER_TEMP")


def cli_environment(home: Path) -> dict[str, str]:
    """Isolate CLI state while preserving the disposable macOS login Keychain."""
    environment = dict(
        os.environ,
        XDG_DATA_HOME=str(home),
        XDG_CONFIG_HOME=str(home),
        AI_STP_TELEMETRY_SUPPRESS="1",
    )
    if platform.system() == "Darwin":
        disposable_runner()
    else:
        environment["HOME"] = str(home)
    return environment


def report_stage(name: str) -> None:
    """Publish a content-free CI lifecycle marker."""
    print(json.dumps({"native_fixture_stage": name}), flush=True)
