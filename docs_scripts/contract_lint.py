#!/usr/bin/env python3
"""Validate the documented CI push branches and exclusion of checkout-specific state."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WORKFLOW = Path(".github/workflows/check.yml")

GIT_WORKFLOW_DOC = Path("docs/engineering/git-workflow.md")

LOCAL_TOOL_PATHS = (".serena", ".serena.local-backup-before-ff")


@dataclass
class Issue:
    path: str
    code: str
    message: str


class ContractLinter:
    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        self.issues: list[Issue] = []

    def error(self, path: Path | str, code: str, message: str) -> None:
        self.issues.append(Issue(str(path), code, message))

    def run(self) -> None:
        self.check_branch_parity()
        self.check_tracked_runtime_state()

    def check_branch_parity(self) -> None:
        """Push branches in the workflow must match the documented branches."""
        workflow = self.root / WORKFLOW
        doc = self.root / GIT_WORKFLOW_DOC
        if not workflow.exists() or not doc.exists():
            self.error(WORKFLOW, "CT010", "workflow or branch documentation is missing")
            return

        match = re.search(
            r"push:\s*\n\s*branches:\s*\[([^\]]*)\]", workflow.read_text(encoding="utf-8")
        )
        if not match:
            self.error(WORKFLOW, "CT011", "push branch list was not found")
            return
        actual = {item.strip().strip("\"'") for item in match.group(1).split(",") if item.strip()}

        text = doc.read_text(encoding="utf-8")
        declared = re.search(
            r"CI push branches: ([^\n]+)",
            text,
            re.IGNORECASE,
        )
        if not declared:
            self.error(GIT_WORKFLOW_DOC, "CT012", "document does not name CI push branches")
            return
        expected = set(re.findall(r"`([^`]+)`", declared.group(1)))

        if actual != expected:
            self.error(
                WORKFLOW,
                "CT013",
                f"push branches {sorted(actual)} differ from documented {sorted(expected)}",
            )

    def check_tracked_runtime_state(self) -> None:
        """Local tool configuration and session state stay outside the Git index."""
        try:
            tracked = subprocess.run(
                ["git", "ls-files", "-z", "--", *LOCAL_TOOL_PATHS],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            return  # Source exports have no Git index.

        for path in filter(None, tracked.split("\0")):
            self.error(path, "CT030", "checkout-specific tool data must not be tracked")

    def report(self, fmt: str) -> int:
        if fmt == "github":
            for issue in self.issues:
                print(f"::error file={issue.path},title={issue.code}::{issue.message}")
        else:
            for issue in sorted(self.issues, key=lambda item: (item.path, item.code)):
                print(f"ERROR {issue.path} [{issue.code}] {issue.message}")
        print()
        print(f"Contract errors: {len(self.issues)}")
        return 1 if self.issues else 0


def main() -> int:
    fmt = "github" if "--format=github" in sys.argv else "text"
    linter = ContractLinter()
    linter.run()
    return linter.report(fmt)


if __name__ == "__main__":
    raise SystemExit(main())
