"""Run a bash script with a bash that can actually execute this checkout.

On Windows the ``bash`` on PATH is frequently WSL
(``C:\\Windows\\System32\\bash.exe``). WSL is another machine: it does not
see this working tree, ``uv``, or the host tools the way Git-for-Windows
bash does. ``just back-regress`` used to refuse the whole OS instead of
picking the right binary.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


class BashNotFoundError(FileNotFoundError):
    """No usable bash is installed on this host."""


def _on_windows() -> bool:
    """Whether this host is Windows, asked through one function on purpose.

    A test that wants to exercise the Windows branch cannot simply set
    `os.name = "nt"`: from Python 3.13 `pathlib` reads that at construction, so
    `Path("/tmp/...")` becomes a `WindowsPath` and `is_file()` answers False
    about a file that exists. The guard below would then refuse for the wrong
    reason — as it did here, failing while the code it tests was correct.
    """
    return os.name == "nt"


def _is_wsl_bash(path: Path) -> bool:
    parts = {part.lower() for part in path.resolve().parts}
    return bool(parts & {"system32", "sysnative", "windowsapps"})


def locate_bash() -> Path:
    """Return a bash executable that can run repository scripts on this host.

    ``AI_STP_BASH`` wins when it points at a real file that is not WSL.
    On POSIX the PATH ``bash`` is enough. On Windows the search is Git for
    Windows: next to ``git.exe``, then the conventional Program Files
    locations. Unqualified PATH ``bash`` is consulted last and rejected
    when it is WSL.
    """
    override = os.environ.get("AI_STP_BASH", "").strip()
    if override:
        candidate = Path(override)
        if not candidate.is_file():
            raise BashNotFoundError(f"AI_STP_BASH is not a file: {override}")
        if _on_windows() and _is_wsl_bash(candidate):
            raise BashNotFoundError(f"AI_STP_BASH points at WSL bash: {candidate}")
        return candidate

    if not _on_windows():
        found = shutil.which("bash")
        if found is None:
            raise BashNotFoundError("bash is not on PATH")
        return Path(found)

    for candidate in _windows_candidates():
        if candidate.is_file() and not _is_wsl_bash(candidate):
            return candidate
    raise BashNotFoundError(
        "Git for Windows bash not found; install Git for Windows or set AI_STP_BASH to its bash.exe"
    )


def _windows_candidates() -> list[Path]:
    found: list[Path] = []
    git = shutil.which("git")
    if git is not None:
        git_path = Path(git).resolve()
        # Git\\cmd\\git.exe → Git\\bin\\bash.exe
        found.append(git_path.parent.parent / "bin" / "bash.exe")
        # Git\\bin\\git.exe → Git\\bin\\bash.exe
        found.append(git_path.parent / "bash.exe")
    for root_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(root_name)
        if not root:
            continue
        base = Path(root)
        if root_name == "LOCALAPPDATA":
            found.append(base / "Programs" / "Git" / "bin" / "bash.exe")
        else:
            found.append(base / "Git" / "bin" / "bash.exe")
    path_bash = shutil.which("bash")
    if path_bash is not None:
        found.append(Path(path_bash))
    return found


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        sys.stderr.write("usage: run_bash.py SCRIPT [args...]\n")
        return 2
    try:
        bash = locate_bash()
    except BashNotFoundError as exc:
        sys.stderr.write(f"run_bash: {exc}\n")
        return 1
    completed = subprocess.run([str(bash), *args], check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
