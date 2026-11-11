"""Check each runtime package using uv's authoritative workspace membership."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path.cwd().resolve()
    workspace = subprocess.run(
        [
            "uv",
            "--offline",
            "--no-python-downloads",
            "--color",
            "never",
            "workspace",
            "list",
            "--paths",
        ],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    if workspace.returncode:
        return workspace.returncode
    members = [Path(line).resolve() for line in workspace.stdout.splitlines() if line]
    if root not in members:
        raise SystemExit("Run the dependency check from the workspace root.")
    owners = [member for member in members if member != root]
    if not owners:
        raise SystemExit("No Python workspace members found.")
    failed = False
    for owner in owners:
        if not (owner / "src").is_dir() or not (owner / "pyproject.toml").is_file():
            raise SystemExit(f"Python workspace member has no source owner: {owner}")
        print(f"Checking {owner.relative_to(root)}", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "deptry", "src", "--config", "pyproject.toml", "--no-ansi"],
            cwd=owner,
            check=False,
        )
        failed |= result.returncode != 0
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
