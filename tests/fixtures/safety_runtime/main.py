"""Run one declared real-image acceptance case."""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_stp_platform.safety.sandbox import sandbox_status

from .boundary import boundary_cases
from .cisco import cisco_cases
from .go import go_cases
from .osv import osv_cases

CASES: dict[str, Callable[[Path], dict[str, Any]]] = {
    "go": go_cases,
    "boundary": boundary_cases,
    "cisco": cisco_cases,
    "osv": osv_cases,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in CASES:
        raise ValueError("Unknown runtime qualification case")
    assert os.geteuid() == 10001, "image must retain its declared non-root worker"
    assert sys.version_info[:2] == (3, 14)
    status = sandbox_status()
    assert status["mode"] == "bwrap", status
    assert os.environ.get("AI_STP_SAFETY_REQUIRE_BWRAP") == "1"
    with tempfile.TemporaryDirectory(prefix="ai-stp-image-qualification-") as temporary:
        checks = CASES[sys.argv[1]](Path(temporary))
    print(
        json.dumps(
            {
                "architecture": platform.machine(),
                "python": platform.python_version(),
                "sandbox": status["mode"],
                "checks": checks,
            }
        )
    )


if __name__ == "__main__":
    main()
