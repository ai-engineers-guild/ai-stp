from __future__ import annotations

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


class ContractLintTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.write("docs/engineering/git-workflow.md", GIT_WORKFLOW_DOC)
        self.write(".github/workflows/check.yml", WORKFLOW)

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

    def test_workflow_branch_mismatch_fails(self) -> None:
        self.write(".github/workflows/check.yml", WORKFLOW.replace("[dev, main]", "[main]"))
        self.assertIn("CT013", self.codes())

    def test_workflow_missing_declared_line_fails(self) -> None:
        self.write(
            "docs/engineering/git-workflow.md",
            GIT_WORKFLOW_DOC.replace("CI push branches: `dev`, `main`.", "Branches vary."),
        )
        self.assertIn("CT012", self.codes())

    def test_tracked_local_tool_state_fails(self) -> None:
        with patch("docs_scripts.contract_lint.subprocess.run") as git:
            git.return_value.stdout = ".serena/project.yml\0"
            self.assertIn("CT030", self.codes())
