"""A native workflow dependency cannot disappear or turn failure into promotion."""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"


def workflow(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        yaml.load((WORKFLOWS / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader),
    )


def script(name: str, job: str, index: int = 0) -> str:
    return cast(str, workflow(name)["jobs"][job]["steps"][index]["run"])


def execute(body: str, values: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", body],
        env={"PATH": os.environ.get("PATH", os.defpath), **values},
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


class QualificationTests(unittest.TestCase):
    def results(self, phase: str = "full") -> dict[str, dict[str, str]]:
        return {
            name: {
                "result": "success"
                if name in {"analysis", "secrets", "native-experiments", "wasi-confinement"}
                or name.startswith("integration-") == (phase == "integration")
                else "skipped"
            }
            for name in workflow("check.yml")["jobs"]["qualification"]["needs"]
        }

    def decision(self, results: object, *, private: bool = False, phase: str = "full") -> bool:
        outcome = execute(
            script("check.yml", "qualification"),
            {
                "RESULTS": json.dumps(results),
                "PRIVATE_REPOSITORY": json.dumps(private),
                "PHASE": phase,
                "WASI_SELECTED": "true",
            },
        )
        return outcome.returncode == 0

    def test_completion_directly_depends_on_every_owning_job(self) -> None:
        jobs = workflow("check.yml")["jobs"]
        gate = jobs["qualification"]
        self.assertEqual(set(gate["needs"]), set(jobs) - {"qualification"})
        self.assertEqual(len(gate["needs"]), len(set(gate["needs"])))
        self.assertEqual(gate["if"], "always()")
        self.assertTrue(all(job.get("continue-on-error") != "true" for job in jobs.values()))
        for job, filename in [
            ("desktop", "desktop.yml"),
            ("analysis", "codeql.yml"),
            ("archives", "cli-archives.yml"),
            ("wasi-confinement", "wasi-confinement.yml"),
        ]:
            self.assertEqual(jobs[job]["uses"], f"./.github/workflows/{filename}")
            self.assertNotIn("secrets", jobs[job])
            events = workflow(filename)["on"]
            self.assertIn("workflow_call", events)
            self.assertNotIn("push", events)
            self.assertNotIn("pull_request", events)
        self.assertIn("schedule", workflow("codeql.yml")["on"])

    def test_pr_eligibility_and_full_main_have_distinct_complete_owners(self) -> None:
        source = workflow("check.yml")
        self.assertEqual(source["on"]["push"]["branches"], ["main"])
        self.assertIn("pull_request", source["on"])
        self.assertIn("workflow_dispatch", source["on"])
        for name, job in source["jobs"].items():
            if name in {"analysis", "qualification", "secrets"}:
                continue
            if name == "native-experiments":
                self.assertNotIn("if", job)
                continue
            if name == "wasi-confinement":
                self.assertEqual(job["needs"], "native-experiments")
                self.assertEqual(job["if"], "needs.native-experiments.outputs.wasi == 'true'")
                continue
            expected = (
                "github.event_name == 'pull_request'"
                if name.startswith("integration-")
                else "github.event_name != 'pull_request'"
            )
            self.assertEqual(job["if"], expected, name)
            if name.startswith("integration-"):
                self.assertLessEqual(int(job["timeout-minutes"]), 20)
                self.assertNotIn("strategy", job)
                commands = "\n".join(step.get("run", "") for step in job["steps"])
                for command in ["--release", "tauri build", "test:e2e", "uv build"]:
                    self.assertNotIn(command, commands, name)
        self.assertNotIn("if", source["jobs"]["secrets"])

    def test_failed_cancelled_missing_and_skipped_results_cannot_qualify(self) -> None:
        for phase in ["integration", "full"]:
            self.assertTrue(self.decision(self.results(phase), phase=phase))
            self.assertFalse(self.decision({}, phase=phase))
            self.assertFalse(self.decision([], phase=phase))
            for name, expected in self.results(phase).items():
                for result in [
                    "success",
                    "failure",
                    "cancelled",
                    "skipped",
                    "neutral",
                    "timed_out",
                    None,
                ]:
                    if result == expected["result"]:
                        continue
                    with self.subTest(phase=phase, job=name, result=result):
                        changed: dict[str, Any] = self.results(phase)
                        changed[name] = {} if result is None else {"result": result}
                        self.assertFalse(self.decision(changed, phase=phase))
        self.assertFalse(self.decision(self.results(), phase="unknown"))

    def test_only_private_repository_analysis_is_intentionally_inapplicable(self) -> None:
        for phase in ["integration", "full"]:
            results = self.results(phase)
            results["analysis"]["result"] = "skipped"
            self.assertTrue(self.decision(results, private=True, phase=phase))
            self.assertFalse(self.decision(results, phase=phase))
            for name, expected in results.items():
                if name != "analysis":
                    changed = self.results(phase)
                    changed["analysis"]["result"] = "skipped"
                    changed[name]["result"] = (
                        "success" if expected["result"] == "skipped" else "skipped"
                    )
                    self.assertFalse(self.decision(changed, private=True, phase=phase))

    def test_processed_findings_and_superseded_pushes_refuse(self) -> None:
        fixture = """
gh() {
  case "$*" in
    *code-scanning/alerts*) printf '%s' "$FINDINGS" ;;
    *git/ref/*) printf '%s' "$CURRENT" ;;
    *) return 91 ;;
  esac
}
"""
        values = {
            "REPOSITORY": "example/project",
            "SOURCE_REF": "refs/heads/main",
            "SOURCE_SHA": "a" * 40,
            "EVENT": "push",
            "PRIVATE_REPOSITORY": "false",
            "CURRENT": "a" * 40,
            "FINDINGS": "0",
        }
        body = fixture + script("check.yml", "qualification", 1)
        self.assertEqual(execute(body, values).returncode, 0)
        for change in [{"FINDINGS": "1"}, {"FINDINGS": ""}, {"CURRENT": "b" * 40}]:
            self.assertNotEqual(execute(body, values | change).returncode, 0)
        self.assertIn('-f ref="${SOURCE_REF}"', body)

    def test_release_attestation_requires_explicit_tagged_dispatch(self) -> None:
        release = workflow("cli-release.yml")
        archive = workflow("cli-archives.yml")
        self.assertEqual(
            release["on"]["workflow_dispatch"]["inputs"]["version"]["required"], "true"
        )
        self.assertNotIn("workflow_call", release["on"])
        self.assertNotIn("attest", archive["jobs"])
        self.assertEqual(archive["permissions"], {"contents": "read"})
        self.assertEqual(release["jobs"]["build"]["uses"], "./.github/workflows/cli-archives.yml")
        self.assertEqual(release["jobs"]["build"]["with"]["version"], "${{ inputs.version }}")
        guard = archive["jobs"]["build"]["steps"][0]
        self.assertIn("github.event_name == 'workflow_dispatch'", guard["if"])
        self.assertIn("inputs.version != ''", guard["if"])
        self.assertIn("refs/tags/cli-v${EXPECTED_VERSION}", guard["run"])
        self.assertEqual(release["jobs"]["attest"]["if"], guard["if"])


class PromotionAdmissionTests(unittest.TestCase):
    def candidate(self) -> dict[str, Any]:
        return {
            "id": 41,
            "repository": {"full_name": "example/project"},
            "head_repository": {"full_name": "example/project"},
            "head_sha": "a" * 40,
            "event": "push",
            "head_branch": "main",
            "path": ".github/workflows/check.yml",
            "status": "completed",
            "conclusion": "success",
            "run_attempt": 1,
        }

    def jobs(self) -> dict[str, Any]:
        return {
            "total_count": 1,
            "jobs": [{"name": "qualification", "status": "completed", "conclusion": "success"}],
        }

    def decision(
        self, candidate: dict[str, Any], jobs: dict[str, Any], *, current: str | None = None
    ) -> bool:
        fixture = """
gh() {
  case "$*" in
    */attempts/*/jobs*) printf '%s' "$JOBS" ;;
    */actions/runs/*) printf '%s' "$CANDIDATE" ;;
    */git/ref/heads/main*) printf '%s' "$CURRENT" ;;
    *) return 92 ;;
  esac
}
"""
        outcome = execute(
            fixture + script("deploy.yml", "promote"),
            {
                "REPOSITORY": "example/project",
                "HEAD_SHA": "a" * 40,
                "SOURCE_RUN_ID": "41",
                "SOURCE_ATTEMPT": "1",
                "CANDIDATE": json.dumps(candidate),
                "JOBS": json.dumps(jobs),
                "CURRENT": current if current is not None else "a" * 40,
            },
        )
        return outcome.returncode == 0

    def test_only_the_current_successful_source_attempt_is_admitted(self) -> None:
        self.assertTrue(self.decision(self.candidate(), self.jobs()))
        replacements: dict[str, Any] = {
            "id": 42,
            "repository": {"full_name": "other/project"},
            "head_repository": {"full_name": "fork/project"},
            "head_sha": "b" * 40,
            "event": "pull_request",
            "head_branch": "dev",
            "path": ".github/workflows/desktop.yml",
            "status": "in_progress",
            "conclusion": "failure",
            "run_attempt": 2,
        }
        for key, value in replacements.items():
            with self.subTest(field=key):
                self.assertFalse(self.decision(self.candidate() | {key: value}, self.jobs()))
        self.assertFalse(self.decision(self.candidate(), self.jobs(), current="b" * 40))

    def test_missing_incomplete_duplicate_and_truncated_qualification_refuse(self) -> None:
        self.assertFalse(self.decision(self.candidate(), {"jobs": [], "total_count": 0}))
        self.assertFalse(self.decision(self.candidate(), self.jobs() | {"total_count": 2}))
        for state in ["failure", "cancelled", "skipped", None]:
            jobs = self.jobs()
            jobs["jobs"][0]["conclusion"] = state
            self.assertFalse(self.decision(self.candidate(), jobs))
        jobs = self.jobs()
        jobs["jobs"][0]["status"] = "in_progress"
        self.assertFalse(self.decision(self.candidate(), jobs))
        jobs = self.jobs()
        jobs["jobs"].append(jobs["jobs"][0].copy())
        jobs["total_count"] = 2
        self.assertFalse(self.decision(self.candidate(), jobs))


class ScannerSelectionTests(unittest.TestCase):
    def test_default_owner_is_unchanged_and_missing_selected_scanner_refuses(self) -> None:
        text = (ROOT / "scripts/safety/install_scanners.sh").read_text(encoding="utf-8")
        main = "main() {\n" + text.rsplit("main() {\n", 1)[1].rsplit('\nmain "$@"', 1)[0]
        stages = [
            "install_gitleaks",
            "install_osv_scanner",
            "install_shellcheck",
            "install_opengrep",
            "install_gosec",
            "install_python_tools",
            "install_govulncheck",
            "write_manifest",
        ]
        fixture = "set -euo pipefail\nrequire_cmd() { :; }\nlog() { :; }\n"
        fixture += "\n".join(f"{name}() {{ printf '%s\\n' {name}; }}" for name in stages)
        body = (
            fixture + "\n" + main + '\nif [ "$MODE" = default ]; then main; else main "$MODE"; fi'
        )
        values = {
            "PREFIX": "/__ai_stp_absent_scanner__",
            "PIP_VENV": "/__ai_stp_unused_scanner_environment__",
            "GITLEAKS_VERSION": "test",
        }
        default = execute(body, values | {"MODE": "default"})
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(default.stdout.splitlines(), stages)
        missing = execute(body, values | {"MODE": "--gitleaks-only"})
        self.assertNotEqual(missing.returncode, 0)
        self.assertEqual(missing.stdout.splitlines(), ["install_gitleaks"])
        invalid = execute(body, values | {"MODE": "--unknown"})
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(invalid.stdout, "")


if __name__ == "__main__":
    unittest.main()
