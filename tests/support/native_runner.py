"""Admission for fixtures that mutate disposable native OS user state."""

from __future__ import annotations

import os
import platform


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
