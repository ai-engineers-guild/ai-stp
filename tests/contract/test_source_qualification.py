"""A native workflow dependency cannot disappear or turn failure into promotion."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from typing import Any, cast

import yaml
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from release_scripts._github_delivery import PromotionRefused
from release_scripts.source_admission import admit_source
from tests.contract.test_gate_split_covers_the_gate import command_text

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
                if name
                in {
                    "analysis",
                    "secrets",
                    "native-experiments",
                    "rust-dependencies",
                    "python-dependencies",
                    "wasi-confinement",
                }
                or name.startswith("integration-") == (phase == "integration")
                else "skipped"
            }
            for name in workflow("source.yml")["jobs"]["qualification"]["needs"]
        }

    def decision(self, results: object, *, private: bool = False, phase: str = "full") -> bool:
        outcome = execute(
            script("source.yml", "qualification"),
            {
                "RESULTS": json.dumps(results),
                "PRIVATE_REPOSITORY": json.dumps(private),
                "PHASE": phase,
                "WASI_SELECTED": "true",
            },
        )
        return outcome.returncode == 0

    def test_dependency_ownership_covers_each_supported_python_minor(self) -> None:
        source = workflow("source.yml")
        latest = Version(source["env"]["PYTHON_VERSION"])
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        supported = SpecifierSet(project["project"]["requires-python"])
        selected = {
            Version(source["env"]["PYTHON_VERSION"] if item == "current" else item)
            for item in source["jobs"]["python-dependencies"]["strategy"]["matrix"]["python"]
        }
        expected = {
            (latest.major, minor)
            for minor in range(latest.minor + 1)
            if Version(f"{latest.major}.{minor}") in supported
        }
        self.assertEqual({(item.major, item.minor) for item in selected}, expected)

    def test_completion_directly_depends_on_every_owning_job(self) -> None:
        jobs = workflow("source.yml")["jobs"]
        gate = jobs["qualification"]
        self.assertEqual(set(gate["needs"]), set(jobs) - {"qualification"})
        self.assertEqual(len(gate["needs"]), len(set(gate["needs"])))
        self.assertEqual(gate["if"], "always()")
        self.assertTrue(all(job.get("continue-on-error") != "true" for job in jobs.values()))
        for job, filename in [
            ("desktop", "desktop.yml"),
            ("native-corporate", "native-corporate-checks.yml"),
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
        corporate = jobs["native-corporate"]
        self.assertEqual(corporate["needs"], "archives")
        self.assertNotIn("with", corporate)

    def test_pr_eligibility_and_full_dev_have_distinct_complete_owners(self) -> None:
        source = workflow("source.yml")
        self.assertEqual(set(source["on"]), {"workflow_call"})
        full = workflow("check.yml")
        self.assertEqual(full["on"]["push"]["branches"], ["dev"])
        self.assertEqual(set(full["on"]), {"push", "workflow_dispatch"})
        integration = workflow("integration.yml")
        self.assertEqual(set(integration["on"]), {"pull_request"})
        self.assertEqual(full["concurrency"]["cancel-in-progress"], "false")
        self.assertEqual(integration["concurrency"]["cancel-in-progress"], "true")
        for owner, context in [(full, "full-qualification"), (integration, "qualification")]:
            self.assertEqual(set(owner["jobs"]), {"verify", "qualification"})
            self.assertEqual(owner["jobs"]["verify"]["uses"], "./.github/workflows/source.yml")
            gate = owner["jobs"]["qualification"]
            self.assertEqual(gate["name"], context)
            self.assertEqual(gate["if"], "always()")
            self.assertEqual(gate["needs"], "verify")
            for result in ["success", "skipped", "failure", "cancelled", "neutral", ""]:
                outcome = execute(gate["steps"][0]["run"], {"RESULT": result})
                self.assertEqual(outcome.returncode == 0, result == "success")
        for name, job in source["jobs"].items():
            if name in {"analysis", "qualification", "secrets"}:
                continue
            if name in {"native-experiments", "rust-dependencies", "python-dependencies"}:
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
                self.assertLessEqual(
                    int(job.get("timeout-minutes", job.get("with", {}).get("timeout-minutes"))),
                    20,
                )
                if name == "integration-native":
                    self.assertEqual(
                        job["strategy"],
                        {
                            "fail-fast": "false",
                            "matrix": {"os": ["ubuntu-26.04", "macos-26", "windows-latest"]},
                        },
                    )
                    self.assertEqual(job["name"], "integration-native-${{ matrix.os }}")
                    self.assertEqual(job["runs-on"], "${{ matrix.os }}")
                else:
                    self.assertNotIn("strategy", job)
                commands = command_text(job)
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
            "SOURCE_REF": "refs/heads/dev",
            "SOURCE_SHA": "a" * 40,
            "EVENT": "push",
            "PRIVATE_REPOSITORY": "false",
            "CURRENT": "a" * 40,
            "FINDINGS": "0",
        }
        body = fixture + script("source.yml", "qualification", 1)
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
        self.assertNotIn("build", release["jobs"])
        self.assertEqual(release["jobs"]["attest"]["needs"], "guard")
        self.assertEqual(
            release["jobs"]["attest"]["if"],
            "github.event_name == 'workflow_dispatch' && inputs.version != ''",
        )
        self.assertTrue(
            all(
                "actions/checkout@" not in step.get("uses", "")
                for step in release["jobs"]["attest"]["steps"]
            )
        )
        guard = release["jobs"]["guard"]["steps"][0]
        self.assertIn("refs/tags/cli-v${EXPECTED_VERSION}", guard["run"])
        staged = release["jobs"]["attest"]["steps"][0]["with"]
        self.assertEqual(staged["name"], "qualified-cli-release")
        self.assertEqual(staged["digest-mismatch"], "error")


class PromotionAdmissionTests(unittest.TestCase):
    def candidate(self) -> dict[str, Any]:
        return {
            "id": 41,
            "repository": {"full_name": "example/project"},
            "head_repository": {"full_name": "example/project"},
            "head_sha": "a" * 40,
            "event": "push",
            "head_branch": "dev",
            "path": ".github/workflows/check.yml",
            "status": "completed",
            "conclusion": "success",
            "run_attempt": 1,
        }

    def jobs(self) -> dict[str, Any]:
        return {
            "total_count": 1,
            "jobs": [
                {"name": "full-qualification", "status": "completed", "conclusion": "success"}
            ],
        }

    def decision(
        self, candidate: dict[str, Any], jobs: dict[str, Any], *, current: str | None = None
    ) -> bool:
        try:
            admit_source(
                "example/project",
                "a" * 40,
                41,
                1,
                candidate,
                {"total_count": 1, "workflow_runs": [candidate]},
                jobs,
                current if current is not None else "a" * 40,
            )
            return True
        except (PromotionRefused, TypeError, KeyError):
            return False

    def test_only_the_current_successful_source_attempt_is_admitted(self) -> None:
        self.assertTrue(self.decision(self.candidate(), self.jobs()))
        replacements: dict[str, Any] = {
            "id": 42,
            "repository": {"full_name": "other/project"},
            "head_repository": {"full_name": "fork/project"},
            "head_sha": "b" * 40,
            "event": "pull_request",
            "head_branch": "main",
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


class DesktopReleaseAdmissionTests(unittest.TestCase):
    def release_decision(
        self,
        runs: list[dict[str, Any]],
        jobs: dict[str, Any],
        *,
        current: str | None = None,
        count: int | None = None,
        output: Path | None = None,
    ) -> bool:
        fixture = """
gh() {
  case "$*" in
    */git/ref/heads/main*|*/git/ref/heads/dev*) printf '%s' "$CURRENT" ;;
    */attempts/*/jobs*) printf '%s' "$JOBS" ;;
    */actions/runs\\?*) printf '%s' "$RUNS" ;;
    *) return 92 ;;
  esac
}
"""
        outcome = execute(
            fixture + (ROOT / ".github/scripts/require-client-release-source.sh").read_text(),
            {
                "REPOSITORY": "example/project",
                "HEAD_SHA": "a" * 40,
                "RUNS": json.dumps(
                    {"total_count": len(runs) if count is None else count, "workflow_runs": runs}
                ),
                "JOBS": json.dumps(jobs),
                "CURRENT": "a" * 40 if current is None else current,
                **({"GITHUB_OUTPUT": str(output)} if output else {}),
            },
        )
        return outcome.returncode == 0

    def test_release_refuses_stale_failed_missing_or_truncated_source(self) -> None:
        fixtures = PromotionAdmissionTests()
        source, jobs = fixtures.candidate(), fixtures.jobs()
        self.assertTrue(self.release_decision([source], jobs))
        self.assertFalse(self.release_decision([], jobs))
        self.assertFalse(self.release_decision([source], jobs, current="b" * 40))
        self.assertFalse(self.release_decision([source], jobs, count=2))
        for field, value in {
            "repository": {"full_name": "other/project"},
            "head_repository": {"full_name": "fork/project"},
            "head_sha": "b" * 40,
            "event": "pull_request",
            "head_branch": "main",
            "path": ".github/workflows/desktop.yml",
            "status": "in_progress",
            "conclusion": "failure",
        }.items():
            with self.subTest(field=field):
                self.assertFalse(self.release_decision([source | {field: value}], jobs))
        # An older success cannot hide the newest failed source run.
        self.assertFalse(
            self.release_decision([source, source | {"id": 42, "conclusion": "failure"}], jobs)
        )
        self.assertFalse(
            self.release_decision(
                [source, source | {"id": 42, "head_repository": {"full_name": "fork/project"}}],
                jobs,
            )
        )
        for value in ["failure", "cancelled", "skipped", None]:
            failed = fixtures.jobs()
            failed["jobs"][0]["conclusion"] = value
            self.assertFalse(self.release_decision([source], failed))
        self.assertFalse(self.release_decision([source], {"total_count": 0, "jobs": []}))
        self.assertFalse(self.release_decision([source], jobs | {"total_count": 2}))
        duplicate = fixtures.jobs()
        duplicate["jobs"].append(duplicate["jobs"][0].copy())
        duplicate["total_count"] = 2
        self.assertFalse(self.release_decision([source], duplicate))

    def test_published_packages_are_owned_by_the_installed_three_os_workflow(self) -> None:
        release = workflow("desktop-release.yml")
        self.assertNotIn("bundle", release["jobs"])
        self.assertEqual(release["jobs"]["release"]["needs"], "guard")
        self.assertEqual(
            workflow("source.yml")["jobs"]["desktop"]["uses"], "./.github/workflows/desktop.yml"
        )
        publisher = workflow("client-publication.yml")["jobs"]["release"]["steps"]
        self.assertEqual(publisher[0]["with"]["name"], "qualified-${{ inputs.kind }}-release")
        self.assertEqual(publisher[0]["with"]["digest-mismatch"], "error")
        self.assertFalse(any("actions/checkout@" in step.get("uses", "") for step in publisher))
        self.assertTrue(all("python" not in step.get("run", "") for step in publisher))
        source_download = next(
            step
            for step in release["jobs"]["guard"]["steps"]
            if step.get("name") == "Download the qualified source installers"
        )
        self.assertEqual(
            source_download["with"]["run-id"], "${{ steps.source.outputs.qualified_run_id }}"
        )
        self.assertEqual(source_download["with"]["digest-mismatch"], "error")
        self.assertEqual(release["jobs"]["guard"]["permissions"]["contents"], "read")
        admission = "bash .github/scripts/require-client-release-source.sh"
        for name in ("desktop-release.yml", "cli-release.yml"):
            steps = workflow(name)["jobs"]["guard"]["steps"]
            source = next(step for step in steps if step.get("id") == "source")
            self.assertIn(admission, source["run"])
        self.assertIn("workflow_call", release["on"])
        auto = workflow("deploy.yml")["jobs"]["desktop-release"]
        self.assertEqual(auto["needs"], "promote")
        self.assertEqual(auto["uses"], "./.github/workflows/desktop-release.yml")

    def test_exports_only_the_verified_source_run_and_attempt(self) -> None:
        fixtures = PromotionAdmissionTests()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "outputs"
            self.assertTrue(
                self.release_decision([fixtures.candidate()], fixtures.jobs(), output=output)
            )
            self.assertEqual(output.read_text(), "qualified_run_id=41\nqualified_run_attempt=1\n")
            output.unlink()
            for field in ("id", "run_attempt"):
                self.assertFalse(
                    self.release_decision(
                        [fixtures.candidate() | {field: "41\nforged=1"}],
                        fixtures.jobs(),
                        output=output,
                    )
                )
                self.assertFalse(output.exists())


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
