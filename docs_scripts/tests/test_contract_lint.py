from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from docs_scripts.contract_lint import (
    COMPONENT_TYPES,
    MCP_TRANSPORTS,
    SIDECAR_NAMES,
    ContractLinter,
)

GIT_WORKFLOW_DOC = """---
description: "Branches"
last_verified: "2026-08-04"
---

# Git workflow

`main` is the repository's only line.
"""

WORKFLOW = """name: check

on:
  push:
    branches: [main]
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

REPO_STRUCTURE = """---
description: "Structure"
last_verified: "2026-08-04"
---

# Repository structure

```text
apps/
docs/
specs/
```
"""


def passports_doc() -> str:
    rows = "\n".join(f"| `{name}` | example | marker |" for name in COMPONENT_TYPES)
    sidecars = "\n".join(SIDECAR_NAMES)
    return (
        '---\ndescription: "Passports"\nlast_verified: "2026-08-05"\n---\n\n'
        "# Passports\n\n```text\n" + sidecars + "\n```\n\n"
        "| Type | Example | Marker |\n|---|---|---|\n" + rows + "\n"
    )


def validation_policy() -> str:
    rows = "\n".join(f"| `{name}` | required checks |" for name in COMPONENT_TYPES)
    transports = "\n".join(f"| `{name}` | required checks |" for name in MCP_TRANSPORTS)
    return (
        '---\ndescription: "Policy"\nlast_verified: "2026-08-04"\n---\n\n'
        "# Validation policy\n\n"
        "| Type | Checks |\n|---|---|\n" + rows + "\n\n"
        "| Class | Checks |\n|---|---|\n" + transports + "\n\n"
        "## Installation eligibility\n\n"
        "A version without current evidence is blocked for new installations and updates.\n\n"
        "## Author attestation\n\n"
        "The record is bound to the exact digest and policy version.\n"
    )


VISION_CONTRACT_FIXTURES = {
    "docs/contracts/device-passport.md": "Full device passports are not merged.",
    "docs/contracts/unverified-consent.md": (
        "The user chooses the `publisher` and `object_major` scopes."
    ),
    "docs/contracts/access-grants-and-forks.md": (
        "An unchanged clone is not published under a new name."
    ),
    "docs/contracts/report-case.md": "A public issue is not created automatically from a report.",
    "docs/contracts/selection-proposal.md": "Confirmation is atomic.",
}


class ContractLintTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.write("docs/engineering/git-workflow.md", GIT_WORKFLOW_DOC)
        self.write("docs/engineering/repository-structure.md", REPO_STRUCTURE)
        self.write("docs/contracts/validation-policy.md", validation_policy())
        self.write("docs/contracts/component-setup-passports.md", passports_doc())
        self.write(".github/workflows/check.yml", WORKFLOW)
        self.write(".serena/.gitignore", SERENA_IGNORE)
        for relative, marker in VISION_CONTRACT_FIXTURES.items():
            self.write(relative, self.doc(marker))
        self.write(
            "specs/active/SPEC-016-reports-moderation.md",
            self.doc("Complaints create a closed moderation case."),
        )

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

    def doc(self, body: str) -> str:
        return (
            f'---\ndescription: "Check"\nlast_verified: "2026-08-04"\n---\n\n# Document\n\n{body}\n'
        )

    def test_clean_tree_passes(self) -> None:
        self.assertEqual(self.codes(), set())

    def test_manifest_digest_fails(self) -> None:
        self.write("docs/contracts/x.md", self.doc("The version link contains `manifest_digest`."))
        self.assertIn("CT001", self.codes())

    def test_manifest_hash_domain_fails(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc("The ai-stp:manifest:v1 namespace applies to the version."),
        )
        self.assertIn("CT002", self.codes())

    def test_setup_variant_entity_fails(self) -> None:
        self.write("docs/contracts/x.md", self.doc("Each `SetupVariant` has its own versions."))
        self.assertIn("CT003", self.codes())

    def test_inferred_origin_fails(self) -> None:
        self.write(
            "docs/contracts/x.md", self.doc("`inferred` provenance is allowed for evaluation.")
        )
        self.assertIn("CT004", self.codes())

    def test_setup_level_variant_id_fails(self) -> None:
        self.write(
            "docs/contracts/x.md", self.doc("The setup version passport contains `variant_id`.")
        )
        self.assertIn("CT005", self.codes())

    def test_marketplace_as_component_type_fails(self) -> None:
        self.write("specs/active/x.md", self.doc("`component_type` accepts `marketplace`."))
        self.assertIn("CT006", self.codes())

    def test_operation_succeeded_fails(self) -> None:
        self.write("specs/active/x.md", self.doc("The operation has state `succeeded` on success."))
        self.assertIn("CT007", self.codes())

    def test_fit_terminology_fails(self) -> None:
        self.write("specs/active/x.md", self.doc("`FitRun` passes through selection states."))
        self.assertIn("CT008", self.codes())

    def test_unsupported_apply_as_state_fails(self) -> None:
        self.write(
            "specs/active/x.md", self.doc("The flow returns state `unsupported_apply` here.")
        )
        self.assertIn("CT009", self.codes())

    def test_prohibition_wording_passes(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc(
                "A setup has no `variant_id`.\n\n"
                "There is no separate `SetupVariant` entity.\n\n"
                "The `inferred` provenance is not used.\n\n"
                "`marketplace` is not a component type.\n\n"
                "The operation has no `succeeded` state: success is called `verified`."
            ),
        )
        self.assertEqual(self.codes(), set())

    def test_component_level_variant_id_passes(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc("The component version link contains an optional `variant_id`."),
        )
        self.assertEqual(self.codes(), set())

    def test_english_prohibition_wording_passes(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc(
                "A setup has no `variant_id`.\n\n"
                "The `inferred` origin is not used.\n\n"
                "The `search.include_unverified` key has been removed."
            ),
        )
        self.assertEqual(self.codes(), set())

    def test_adr_history_is_exempt(self) -> None:
        self.write(
            "docs/adr/ADR-0099-history.md",
            self.doc("The former model used `manifest_digest` and `SetupVariant`."),
        )
        self.assertEqual(self.codes(), set())

    def test_workflow_branch_mismatch_fails(self) -> None:
        self.write(".github/workflows/check.yml", WORKFLOW.replace("[main]", "[main, rldyourmnd]"))
        self.assertIn("CT013", self.codes())

    def test_workflow_missing_declared_line_fails(self) -> None:
        self.write(
            "docs/engineering/git-workflow.md",
            GIT_WORKFLOW_DOC.replace("`main` is the repository's only line.", "Branches vary."),
        )
        self.assertIn("CT012", self.codes())

    def test_missing_component_type_row_fails(self) -> None:
        self.write(
            "docs/contracts/validation-policy.md",
            validation_policy().replace("| `hook` | required checks |\n", ""),
        )
        self.assertIn("CT021", self.codes())

    def test_missing_mcp_transport_row_fails(self) -> None:
        self.write(
            "docs/contracts/validation-policy.md",
            validation_policy().replace("| `remote_https` | required checks |\n", ""),
        )
        self.assertIn("CT022", self.codes())

    def test_missing_component_type_example_fails(self) -> None:
        self.write(
            "docs/contracts/component-setup-passports.md",
            passports_doc().replace("| `plugin` | example | marker |\n", ""),
        )
        self.assertIn("CT024", self.codes())

    def test_missing_sidecar_name_fails(self) -> None:
        self.write(
            "docs/contracts/component-setup-passports.md",
            passports_doc().replace("ai-stp.setup.yaml\n", ""),
        )
        self.assertIn("CT025", self.codes())

    def test_missing_runtime_ignore_entry_fails(self) -> None:
        self.write(".serena/.gitignore", "/cache\n/project.local.yml\n")
        self.assertIn("CT032", self.codes())

    def test_work_directory_in_structure_fails(self) -> None:
        self.write(
            "docs/engineering/repository-structure.md",
            REPO_STRUCTURE.replace("specs/\n", "specs/\n.work/\n"),
        )
        self.assertIn("CT040", self.codes())

    def test_include_unverified_fails(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc("The `include_unverified` key enables everything at once."),
        )
        self.assertIn("CT050", self.codes())

    def test_include_unverified_removal_wording_passes(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc("The `search.include_unverified` key was removed permanently."),
        )
        self.assertNotIn("CT050", self.codes())

    def test_permanent_ceiling_fails(self) -> None:
        self.write(
            "docs/product/x.md",
            self.doc("Five is the product target number; the list is not planned to expand."),
        )
        self.assertIn("CT051", self.codes())

    def test_publishable_not_run_fails(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc(
                "The check returns `not_run` with a reason, and that version is published "
                "without a badge."
            ),
        )
        self.assertIn("CT052", self.codes())

    def test_blocking_not_run_passes(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc(
                "A required `not_run` check blocks public publication.\n\n"
                "A warning does not block publication."
            ),
        )
        self.assertNotIn("CT052", self.codes())

    def test_web_only_scope_fails(self) -> None:
        self.write(
            "docs/product/x.md",
            self.doc("The site in the MVP is only for installation, sign-in, and public search."),
        )
        self.assertIn("CT053", self.codes())

    def test_hardcoded_counts_fail(self) -> None:
        self.write(
            "docs/engineering/x.md",
            self.doc("13 ADR and 15 active specifications with 147 requirements were accepted."),
        )
        self.assertIn("CT054", self.codes())

    def test_developer_passport_env_fails(self) -> None:
        self.write(
            "specs/active/x.md",
            self.doc("The DeveloperPassport stores OS, architecture, and tool versions."),
        )
        self.assertIn("CT055", self.codes())

    def test_device_ownership_wording_passes(self) -> None:
        self.write(
            "specs/active/x.md",
            self.doc(
                "Observed OS and architecture belong to it, not the DeveloperPassport.\n\n"
                "The DeveloperPassport does not contain observed architecture."
            ),
        )
        self.assertNotIn("CT055", self.codes())

    def test_an_unrelated_negation_does_not_exempt_the_violation(self) -> None:
        """The planted control the old four-phrase skip let through.

        A real violation — the developer passport carrying OS and architecture —
        with `does not change` in a clause about something else entirely. The
        exemption is for a negation that binds to the passport; a negation
        anywhere on the line is not the same claim, and reading it as one is how
        a check keeps its green while admitting what it was written to catch.
        """
        self.write(
            "specs/active/x.md",
            self.doc(
                "The DeveloperPassport carries the operating system and architecture "
                "of the machine, and record order does not change their meaning."
            ),
        )
        self.assertIn("CT055", self.codes())

    def test_the_wording_the_estate_actually_uses_is_exempt(self) -> None:
        """`ADR-0025` phrases it this way, and the old skip did not carry it."""
        self.write(
            "specs/active/x.md",
            self.doc(
                "Observed operating system, architecture, and tool versions "
                "are not part of DeveloperPassport."
            ),
        )
        self.assertNotIn("CT055", self.codes())

    def test_report_channel_excluded_fails(self) -> None:
        self.write("specs/active/x.md", self.doc("There is no user complaint channel in the MVP."))
        self.assertIn("CT056", self.codes())

    def test_platform_only_validation_fails(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc("The full set of required checks runs on the platform server."),
        )
        self.assertIn("CT064", self.codes())

    def test_missing_vision_contract_fails(self) -> None:
        (self.root / "docs/contracts/report-case.md").unlink()
        self.assertIn("CT062", self.codes())

    def test_missing_vision_marker_fails(self) -> None:
        self.write(
            "docs/contracts/unverified-consent.md",
            self.doc("Consent records without scopes."),
        )
        self.assertIn("CT063", self.codes())

    def test_missing_reports_spec_fails(self) -> None:
        (self.root / "specs/active/SPEC-016-reports-moderation.md").unlink()
        self.assertIn("CT065", self.codes())

    def test_missing_eligibility_marker_fails(self) -> None:
        self.write(
            "docs/contracts/validation-policy.md",
            validation_policy()
            .replace("## Installation eligibility\n\n", "")
            .replace(
                "A version without current evidence is blocked "
                "for new installations and updates.\n\n",
                "",
            ),
        )
        self.assertIn("CT060", self.codes())

    def test_missing_attestation_marker_fails(self) -> None:
        self.write(
            "docs/contracts/validation-policy.md",
            validation_policy().replace("## Author attestation", "## Other"),
        )
        self.assertIn("CT061", self.codes())

    def test_bare_object_id_fails(self) -> None:
        self.write(
            "docs/contracts/x.md", self.doc("```yaml\nid: component_01J0000000000000000000\n```")
        )
        self.assertIn("CT066", self.codes())

    def test_stable_id_passes(self) -> None:
        self.write(
            "docs/contracts/x.md",
            self.doc("```yaml\nstable_id: component_01J0000000000000000000\n```"),
        )
        self.assertNotIn("CT066", self.codes())


if __name__ == "__main__":
    unittest.main()
