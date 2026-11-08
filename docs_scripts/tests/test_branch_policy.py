from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


class BranchPolicyTest(unittest.TestCase):
    def test_ruleset_contract(self) -> None:
        root = Path(".github")
        permanent = json.loads((root / "permanent-branches.ruleset.json").read_text())
        promotion = json.loads((root / "main-promotion.ruleset.json").read_text())
        updates = json.loads((root / "main-admin-updates.ruleset.json").read_text())
        integration = json.loads((root / "dev-integration.ruleset.json").read_text())
        self.assertEqual(
            permanent["conditions"]["ref_name"]["include"],
            ["refs/heads/main", "refs/heads/dev"],
        )
        rules = {rule["type"]: rule.get("parameters", {}) for rule in permanent["rules"]}
        self.assertEqual(
            set(rules),
            {
                "deletion",
                "non_fast_forward",
                "code_scanning",
            },
        )
        dev_rules = {rule["type"]: rule["parameters"] for rule in integration["rules"]}
        self.assertEqual(set(dev_rules), {"pull_request", "required_status_checks"})
        self.assertEqual(dev_rules["pull_request"]["required_approving_review_count"], 0)
        self.assertEqual(
            integration["conditions"]["ref_name"], {"include": ["refs/heads/dev"], "exclude": []}
        )
        self.assertTrue(dev_rules["required_status_checks"]["strict_required_status_checks_policy"])
        self.assertEqual(
            dev_rules["required_status_checks"]["required_status_checks"],
            [{"context": "qualification", "integration_id": 15368}],
        )
        self.assertEqual(
            rules["code_scanning"]["code_scanning_tools"],
            [{"tool": "CodeQL", "alerts_threshold": "all", "security_alerts_threshold": "all"}],
        )
        self.assertEqual(
            promotion["rules"][0]["parameters"]["required_status_checks"],
            [{"context": "full-qualification", "integration_id": 15368}],
        )
        self.assertEqual([rule["type"] for rule in promotion["rules"]], ["required_status_checks"])
        self.assertFalse(
            promotion["rules"][0]["parameters"]["strict_required_status_checks_policy"]
        )
        self.assertEqual(updates["rules"], [{"type": "update"}])
        for policy in (permanent, promotion, integration):
            self.assertEqual(policy["enforcement"], "active")
            self.assertEqual(
                policy["bypass_actors"],
                [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
            )
        self.assertEqual(updates["enforcement"], "active")
        self.assertEqual(
            updates["conditions"]["ref_name"], {"include": ["refs/heads/main"], "exclude": []}
        )
        self.assertEqual(promotion["conditions"]["ref_name"], updates["conditions"]["ref_name"])
        self.assertEqual(
            updates["bypass_actors"],
            [
                {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"},
            ],
        )

    def test_promotion_source(self) -> None:
        workflow = Path(".github/workflows/branch-policy.yml").read_text(encoding="utf-8")
        script = workflow.split("        run: |\n", 1)[1]
        script = "\n".join(line[10:] for line in script.splitlines())
        bash = "bash"
        if sys.platform == "win32":
            git = shutil.which("git")
            assert git is not None
            bash = str(
                next(
                    candidate
                    for parent in Path(git).parents
                    if (candidate := parent / "bin" / "bash.exe").is_file()
                )
            )
        for event, base, head, source, allowed in (
            ("pull_request", "main", "dev", "owner/repo", False),
            ("pull_request", "main", "feat/example", "owner/repo", False),
            ("pull_request", "main", "dev", "fork/repo", False),
            ("pull_request", "dev", "feat/example", "owner/repo", True),
            ("pull_request", "feature", "feat/example", "owner/repo", False),
            ("push", "", "", "", True),
        ):
            with self.subTest(event=event, base=base, head=head, source=source):
                result = subprocess.run(
                    [
                        bash,
                        "-c",
                        'export EVENT="$1" BASE="$2" HEAD="$3" '
                        'SOURCE_REPOSITORY="$4" REPOSITORY="$5"\n' + script,
                        "branch-policy",
                        event,
                        base,
                        head,
                        source,
                        "owner/repo",
                    ],
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode == 0, allowed)
