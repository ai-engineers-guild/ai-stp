#!/usr/bin/env python3
"""Validate branch policy and exclusion of checkout-specific state."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BRANCH_PREFIXES = ("feat", "chore", "docs", "test", "fix", "refactor")

BRANCH_NAME_RE = re.compile(rf"^(?:{'|'.join(BRANCH_PREFIXES)})/.+$")


def is_dependabot_pull_request(branch: str) -> bool:
    """Accept only a same-repository PR actually authored by Dependabot."""
    if not branch.startswith("dependabot/") or branch == "dependabot/":
        return False
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return False
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    repository = os.environ.get("GITHUB_REPOSITORY")
    if not event_path or not repository:
        return False
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(event, dict):
        return False
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        return False
    user = pull_request.get("user")
    head = pull_request.get("head")
    return (
        isinstance(user, dict)
        and user.get("login") == "dependabot[bot]"
        and isinstance(head, dict)
        and head.get("ref") == branch
        and isinstance(head.get("repo"), dict)
        and head["repo"].get("full_name") == repository
    )


WORKFLOW = Path(".github/workflows/check.yml")

GIT_WORKFLOW_DOC = Path("docs/engineering/git-workflow.md")

SERENA_IGNORE = Path(".serena/.gitignore")

SERENA_TRANSIENT = (
    ".serena/.auto_sync_head",
    ".serena/.flow_blocker_ack.json",
    ".serena/.flow_post_task_state.json",
    ".serena/.flow_sync_marker",
    ".serena/.serena_sync_state.json",
)


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
        self.check_branch_name()
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

    def check_branch_name(self) -> None:
        """CI branches use the repository's allowed conventional prefixes."""
        branch = os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME")
        if (
            not branch
            or branch in {"main", "dev"}
            or BRANCH_NAME_RE.fullmatch(branch)
            or is_dependabot_pull_request(branch)
        ):
            return
        self.error(
            GIT_WORKFLOW_DOC,
            "CT014",
            f"branch `{branch}` must use one of: "
            f"{', '.join(f'{prefix}/' for prefix in BRANCH_PREFIXES)}",
        )

    def check_tracked_runtime_state(self) -> None:
        """Specific checkout state is untracked and declared in ignore.

        Both halves are independent: the ignore declaration is checked even
        without Git, or the check would silently disappear with the working tree.
        """
        try:
            tracked = subprocess.run(
                ["git", "ls-files", "-z", "--", ".serena"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split("\0")
        except (OSError, subprocess.CalledProcessError):
            tracked = []  # Outside a Git checkout there is no tracking to inspect.

        tracked_set = {item for item in tracked if item}
        for name in SERENA_TRANSIENT:
            if name in tracked_set:
                self.error(
                    name,
                    "CT030",
                    "specific checkout state is tracked again: SHA, branch, and machine path",
                )

        ignore = self.root / SERENA_IGNORE
        if not ignore.exists():
            self.error(SERENA_IGNORE, "CT031", "session-state ignore file is missing")
            return
        declared = {
            line.strip().lstrip("/") for line in ignore.read_text(encoding="utf-8").splitlines()
        }
        for name in SERENA_TRANSIENT:
            basename = Path(name).name
            if basename not in declared:
                self.error(SERENA_IGNORE, "CT032", f"{basename} is not declared in ignore")

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
