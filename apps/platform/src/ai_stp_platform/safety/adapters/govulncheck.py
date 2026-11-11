"""Go vulnerability analysis against a fresh local native database."""

from __future__ import annotations

import time
from pathlib import Path

from ai_stp_platform.safety.adapters._cli import classify_cli_exit, manifest_roots, run_cli
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.osv_health import (
    max_age_hours,
    offline_db_age_hours,
    osv_offline_dir,
)
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import (
    ArtifactManifest,
    CheckOutcome,
    Finding,
    maximum_finding_severity,
)


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    result = CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result="not_applicable",
        mandatory=spec.mandatory,
        tool_name="govulncheck",
    )
    if "go" not in manifest.languages:
        return result
    roots = manifest_roots(tree, "go.mod")
    if not roots:
        result.result = "not_run"
        result.detail = {"reason": "module_manifest_missing"}
        return result
    base = osv_offline_dir()
    database = base / "govulncheck" if base else None
    if database is None or not all(
        (database / "index" / name).is_file() for name in ("db.json", "modules.json", "vulns.json")
    ):
        result.result = "not_run"
        result.detail = {"reason": "offline_db_missing"}
        return result
    age = offline_db_age_hours(database)
    if age is None or age > max_age_hours():
        result.result = "not_run"
        result.detail = {"reason": "offline_db_unavailable" if age is None else "offline_db_stale"}
        return result
    deadline = time.perf_counter() + spec.timeout_seconds
    incomplete = False
    for root in roots:
        code, out, err, ms = run_cli(
            ["govulncheck", "-db", database.resolve().as_uri(), "./..."],
            cwd=root,
            timeout=max(0.0, deadline - time.perf_counter()),
        )
        result.duration_ms += ms
        if code == 3:
            # Native text output reserves 3 for vulnerabilities; 1 is an execution error.
            result.findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="govulncheck",
                    severity="medium",
                    title="govulncheck reported vulnerabilities",
                    message="Vulnerable reachable Go symbols were reported.",
                    tool_name="govulncheck",
                )
            )
        elif code != 0:
            state, detail = classify_cli_exit(code, out, err)
            result.result = "degraded" if code == 1 else state
            result.detail = (
                {"reason": "tool_error", "exit_code": code, "stderr": redact_message(err)}
                if code == 1
                else detail
            )
            incomplete = True
            if code == 124:
                break
    if not incomplete:
        result.result = "warning" if result.findings else "passed"
    result.severity_max = maximum_finding_severity(result.findings)
    result.detail["database_age_hours"] = round(age, 3)
    return result
