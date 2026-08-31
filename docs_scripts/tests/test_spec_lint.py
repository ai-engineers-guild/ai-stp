from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from docs_scripts.spec_lint import SpecLinter

GOOD_SPEC = """---
description: \"Check\"
last_verified: \"2026-08-03\"
---

# SPEC-001: Check

## Purpose

Observable outcome.

## Scope

One behavior is in scope; another is not.

## Terms

`Object` is the object under test.

## Requirements

- `REQ-001`: The object has a stable identifier.

## States and errors

`ready` and `failed` are distinct.

## Security and privacy

Secrets are not processed.

## Compatibility and migration

The schema version is required.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-001` | A unit test verifies stability. |
"""


class SpecLintTests(unittest.TestCase):
    def make_root(self, text: str) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name)
        directory = root / "specs" / "active"
        directory.mkdir(parents=True)
        (directory / "SPEC-001-example.md").write_text(text, encoding="utf-8")
        return root

    def test_complete_spec_passes(self) -> None:
        linter = SpecLinter(self.make_root(GOOD_SPEC))
        linter.run()
        self.assertEqual([], linter.issues)

    def test_missing_acceptance_mapping_fails(self) -> None:
        broken = GOOD_SPEC.replace(
            "| `REQ-001` | A unit test verifies stability. |", "| - | No mapping. |"
        )
        linter = SpecLinter(self.make_root(broken))
        linter.run()
        self.assertIn("SP09", {issue.code for issue in linter.issues})

    def test_missing_required_section_fails(self) -> None:
        broken = GOOD_SPEC.replace(
            "## Compatibility and migration\n\nThe schema version is required.\n\n", ""
        )
        linter = SpecLinter(self.make_root(broken))
        linter.run()
        self.assertIn("SP06", {issue.code for issue in linter.issues})


if __name__ == "__main__":
    unittest.main()
