from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docs_scripts.contract_lint import ContractLinter

GIT_WORKFLOW_DOC = """---
description: "Branches"
last_verified: "2026-08-04"
---

# Git workflow

CI push branches: `dev`, `main`.
"""

WORKFLOW = """name: check

on:
  push:
    branches: [dev, main]
  pull_request:
"""

SERENA_IGNORE = """/cache
/project.local.yml
/.auto_sync_head
/.flow_blocker_ack.json
/.flow_post_task_state.json
/.flow_sync_marker
/.serena_sync_state.json
"""


class ContractLintTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.write("docs/engineering/git-workflow.md", GIT_WORKFLOW_DOC)
        self.write(".github/workflows/check.yml", WORKFLOW)
        self.write(".serena/.gitignore", SERENA_IGNORE)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def codes(self) -> set[str]:
        linter = ContractLinter(self.root)
        linter.run()
        return {issue.code for issue in linter.issues}

    def test_clean_tree_passes(self) -> None:
        self.assertEqual(self.codes(), set())

    def test_disallowed_branch_prefix_fails(self) -> None:
        for branch in ("claude/example", "codex/example", "bugfix/example"):
            with (
                self.subTest(branch=branch),
                patch.dict(os.environ, {"GITHUB_HEAD_REF": branch}, clear=False),
            ):
                self.assertIn("CT014", self.codes())

    def test_allowed_branch_prefix_passes(self) -> None:
        for branch in ("refactor/git-workflow", "dev", "main"):
            with patch.dict(os.environ, {"GITHUB_HEAD_REF": branch}, clear=False):
                self.assertNotIn("CT014", self.codes())

    def test_dependabot_branch_requires_same_repository_bot_pr(self) -> None:
        branch = "dependabot/uv/idna-3.20"
        event = {
            "pull_request": {
                "user": {"login": "dependabot[bot]"},
                "head": {"ref": branch, "repo": {"full_name": "owner/repo"}},
            }
        }
        env = {
            "GITHUB_HEAD_REF": branch,
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(self.root / "event.json"),
            "GITHUB_REPOSITORY": "owner/repo",
        }
        with patch.dict(os.environ, env, clear=False):
            self.write("event.json", json.dumps(event))
            self.assertNotIn("CT014", self.codes())

            event["pull_request"]["user"]["login"] = "other-user"
            self.write("event.json", json.dumps(event))
            self.assertIn("CT014", self.codes())

            event["pull_request"]["user"]["login"] = "dependabot[bot]"
            event["pull_request"]["head"]["repo"]["full_name"] = "other/repo"
            self.write("event.json", json.dumps(event))
            self.assertIn("CT014", self.codes())

            event["pull_request"]["head"]["repo"]["full_name"] = "owner/repo"
            event["pull_request"]["head"]["ref"] = "dependabot/uv/other"
            self.write("event.json", json.dumps(event))
            self.assertIn("CT014", self.codes())

            event["pull_request"]["head"]["ref"] = branch
            self.write("event.json", json.dumps(event))
            with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "push"}, clear=False):
                self.assertIn("CT014", self.codes())

            self.write("event.json", "not JSON")
            self.assertIn("CT014", self.codes())

    def test_workflow_branch_mismatch_fails(self) -> None:
        self.write(".github/workflows/check.yml", WORKFLOW.replace("[dev, main]", "[main]"))
        self.assertIn("CT013", self.codes())

    def test_workflow_missing_declared_line_fails(self) -> None:
        self.write(
            "docs/engineering/git-workflow.md",
            GIT_WORKFLOW_DOC.replace("CI push branches: `dev`, `main`.", "Branches vary."),
        )
        self.assertIn("CT012", self.codes())

    def test_missing_runtime_ignore_entry_fails(self) -> None:
        self.write(".serena/.gitignore", "/cache\n/project.local.yml\n")
        self.assertIn("CT032", self.codes())
