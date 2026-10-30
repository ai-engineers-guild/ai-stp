"""The exact legacy buffer disposition cannot suppress a different implementation."""

from __future__ import annotations

import copy
import unittest
from datetime import date
from typing import Any

from scripts.safety.check_advisory_scope import (
    ADVISORY,
    AUDITED_SOURCES,
    LEGACY_CHECKSUM,
    REGISTRY,
    REVIEW_BEFORE,
    main as check_committed_scopes,
    validate_scope,
)


class AdvisoryScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.lock: dict[str, Any] = {
            "package": [
                {
                    "name": "block-buffer",
                    "version": "0.10.4",
                    "source": REGISTRY,
                    "checksum": LEGACY_CHECKSUM,
                },
                {
                    "name": "block-buffer",
                    "version": "0.12.1",
                    "source": REGISTRY,
                    "checksum": AUDITED_SOURCES["0.12.1"],
                },
                {"name": "digest", "version": "0.10.7", "dependencies": ["block-buffer 0.10.4"]},
            ]
        }
        self.config: dict[str, Any] = {
            "IgnoredVulns": [{"id": ADVISORY, "ignoreUntil": REVIEW_BEFORE, "reason": "audit"}]
        }
        self.today = date(2026, 10, 27)

    def test_exact_legacy_and_patched_graph_is_accepted(self) -> None:
        self.assertTrue(validate_scope(self.lock, self.config, self.today))

    def test_other_versions_cannot_inherit_the_assessment(self) -> None:
        for version in ("0.9.0", "0.10.5", "0.11.0", "0.12.0", "0.12.1-rc.1", "0.12.2", "0.13.0"):
            with self.subTest(version=version):
                changed = copy.deepcopy(self.lock)
                changed["package"].append({"name": "block-buffer", "version": version})
                with self.assertRaisesRegex(ValueError, "unaudited buffer"):
                    validate_scope(changed, self.config, self.today)

    def test_changed_source_or_checksum_is_refused(self) -> None:
        for key, value in (
            ("source", "git+https://example.invalid/replacement"),
            ("checksum", "0" * 64),
        ):
            with self.subTest(key=key):
                changed = copy.deepcopy(self.lock)
                changed["package"][0][key] = value
                with self.assertRaisesRegex(ValueError, "source differs"):
                    validate_scope(changed, self.config, self.today)

    def test_deadline_expiry_and_unreviewed_extension_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicit review"):
            validate_scope(self.lock, self.config, REVIEW_BEFORE)
        changed = copy.deepcopy(self.config)
        changed["IgnoredVulns"][0]["ignoreUntil"] = date(2027, 1, 1)
        with self.assertRaisesRegex(ValueError, "explicit review"):
            validate_scope(self.lock, changed, self.today)

    def test_regression_dependency_cannot_keep_a_stale_assessment_alive(self) -> None:
        self.lock["package"].pop()
        self.lock["package"].append(
            {"name": "ai-stp-cli", "version": "0.1.3", "dependencies": ["block-buffer 0.10.4"]}
        )
        with self.assertRaisesRegex(ValueError, "last consumer"):
            validate_scope(self.lock, self.config, self.today)

    def test_absent_legacy_and_duplicate_assessments_are_refused(self) -> None:
        changed = copy.deepcopy(self.lock)
        changed["package"].pop(0)
        with self.assertRaisesRegex(ValueError, "stale or ambiguous"):
            validate_scope(changed, self.config, self.today)
        self.config["IgnoredVulns"].append(copy.deepcopy(self.config["IgnoredVulns"][0]))
        with self.assertRaisesRegex(ValueError, "explicit review"):
            validate_scope(self.lock, self.config, self.today)

    def test_no_assessment_leaves_the_normal_scanner_responsible(self) -> None:
        self.assertFalse(validate_scope(self.lock, {}, self.today))

    def test_committed_assessments_match_the_actual_lock_graph(self) -> None:
        check_committed_scopes()


if __name__ == "__main__":
    unittest.main()
