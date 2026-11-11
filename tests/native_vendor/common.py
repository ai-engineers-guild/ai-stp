"""Owned fixture boundaries shared by actual native vendor readers."""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


def environment(root: Path, vendor_variable: str, vendor_home: Path) -> dict[str, str]:
    home = root / "h"
    result = {
        name: value
        for name, value in os.environ.items()
        if name in {"PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"}
    }
    result.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            vendor_variable: str(vendor_home),
            "TMPDIR": str(root / "t"),
            "TMP": str(root / "t"),
            "TEMP": str(root / "t"),
            "LANG": "C.UTF-8",
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
        }
    )
    return result


def write_skill(root: Path, folder: str, name: str, description: str) -> Path:
    directory = root / folder
    directory.mkdir(parents=True)
    document = directory / "SKILL.md"
    document.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n"
        "Format only caller-supplied fixture text.\n",
        encoding="utf-8",
    )
    return document


def binary_digest(executable: Path) -> str:
    with executable.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def native_user_scope(vendor: str) -> Generator[Path | None]:
    """Windows known-folder APIs require an owned child of the native CI profile."""
    if os.name != "nt":
        yield None
        return
    assert os.environ.get("GITHUB_ACTIONS") == "true"
    assert os.environ.get("RUNNER_OS") == "Windows"
    profile_home = Path.home().resolve()
    parent = profile_home / ".agents" / "skills"
    assert parent.resolve().is_relative_to(profile_home)
    parent.mkdir(parents=True, exist_ok=True)
    assert parent.resolve().is_relative_to(profile_home)
    with tempfile.TemporaryDirectory(prefix=f"stp-{vendor}-", dir=parent) as temporary:
        yield Path(temporary)
