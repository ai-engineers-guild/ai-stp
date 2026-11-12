"""Observe file protection through the native metadata owner, without changing it."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast


@dataclass(frozen=True)
class FileProtection:
    mode: int
    attributes: int | None = None
    descriptor: str | None = field(default=None, repr=False)


def file_protection(path: Path) -> FileProtection:
    assert path.is_file() and not path.is_symlink()
    mode = stat.S_IMODE(path.stat().st_mode)
    if os.name != "nt":
        return FileProtection(mode)
    observed = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            ".github/scripts/read-native-file-protection.ps1",
            "-Path",
            str(path),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=15,
        check=True,
    )
    assert len(observed.stdout) <= 256 * 1024
    payload = cast(dict[str, object], json.loads(observed.stdout))
    assert set(payload) == {"attributes", "descriptor"}
    attributes, descriptor = payload["attributes"], payload["descriptor"]
    assert isinstance(attributes, int) and isinstance(descriptor, str) and descriptor
    return FileProtection(mode, attributes, descriptor)
