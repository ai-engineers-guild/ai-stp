#!/usr/bin/env python3
"""Render all Mermaid blocks through the pinned repository-local mmdc binary."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MMDC = (
    ROOT
    / "docs_scripts"
    / "node_modules"
    / ".bin"
    / ("mmdc.cmd" if sys.platform == "win32" else "mmdc")
)
BLOCK_RE = re.compile(r"^```mermaid\n(.*?)^```", re.S | re.M)

#: Directories that a tree walk must not treat as repository documentation.
#: Git already knows this; the list is only needed without Git.
_WALK_EXCLUDED = frozenset({"node_modules", ".venv", ".next", ".git", ".site", "dist"})


def documents() -> list[Path]:
    """Return Markdown files actually present in the repository.

    Git provides the answer rather than a tree walk. A walk also finds build
    output: `.next` creates an `agents.md` directory, and reading it as a file
    once broke the check. A growing ignore list would be worse than Git's answer.

    Include tracked files and new files not covered by ignore so a local document
    is checked before its first `git add`.
    """
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.md"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as failure:
        print(f"WARNING mermaid: git unavailable ({failure}); walking the tree", file=sys.stderr)
        return sorted(
            path
            for path in ROOT.rglob("*.md")
            if path.is_file() and not any(part in _WALK_EXCLUDED for part in path.parts)
        )
    return sorted({ROOT / name for name in listed.split("\0") if name and (ROOT / name).is_file()})


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")  # pyright: ignore[reportAttributeAccessIssue]

    if not MMDC.is_file():
        print("ERROR mermaid: local mmdc binary not found. Run just setup.")
        return 1

    failures = 0
    checked = 0
    with tempfile.TemporaryDirectory() as tmp_raw:
        tmp = Path(tmp_raw)
        for path in documents():
            text = path.read_text(encoding="utf-8")
            for index, block in enumerate(BLOCK_RE.findall(text), start=1):
                identity = hashlib.sha256(f"{path}:{index}".encode()).hexdigest()[:12]
                source = tmp / f"{identity}.mmd"
                output = tmp / f"{identity}.svg"
                source.write_text(block, encoding="utf-8")
                try:
                    result = subprocess.run(
                        [str(MMDC), "-i", str(source), "-o", str(output)],
                        capture_output=True,
                        text=True,
                        timeout=45,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    failures += 1
                    print(f"ERROR {path.relative_to(ROOT)}: block {index} exceeded 45 seconds")
                    continue
                checked += 1
                if result.returncode != 0:
                    failures += 1
                    details = (result.stderr or result.stdout)[-4000:].strip().splitlines()
                    reason = details[-1] if details else "unknown error"
                    relative = path.relative_to(ROOT)
                    print(f"::error file={relative},title=mermaid::block {index}: {reason}")
                    print(f"ERROR {relative}: block {index} did not render: {reason}")

    print(f"Blocks checked: {checked}, render failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
