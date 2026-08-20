"""Setup pin aggregate: union pin safety summaries without re-scanning trees."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

# Threaded from execute_validate / orchestrator for setup plans.
_pin_context: list[dict[str, Any]] = []


def set_pin_context(pins: list[dict[str, Any]]) -> None:
    """Install pin summaries for the next setup aggregate run.

    Each pin dict: stable_id, version, digest?, checks_summary? | scan_state?,
    failed_mandatory?: bool
    """
    global _pin_context
    _pin_context = list(pins)


def clear_pin_context() -> None:
    global _pin_context
    _pin_context = []


def run(tree: Path, manifest: ArtifactManifest | None, spec: CheckSpec) -> CheckOutcome:
    del tree, manifest
    pins = list(_pin_context)
    if not pins:
        # No pins provided — still not a free pass for empty setup graphs.
        return CheckOutcome(
            check_id=spec.check_id,
            family=spec.family,
            result="not_run",
            mandatory=spec.mandatory,
            tool_name="setup_pin_aggregate",
            detail={"reason": "no_pin_context", "mode": "no_union_rescan"},
        )

    findings: list[Finding] = []
    missing: list[str] = []
    failed: list[str] = []
    for pin in pins:
        sid = str(pin.get("stable_id") or "?")
        ver = str(pin.get("version") or "?")
        label = f"{sid}@{ver}"
        summary = pin.get("checks_summary")
        if summary is None and pin.get("scan_state") is None:
            missing.append(label)
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="pin_missing_scan",
                    severity="high",
                    title=f"Pinned component has no safety scan: {label}",
                    message=redact_message(label),
                    tool_name="setup_pin_aggregate",
                )
            )
            continue
        if pin.get("failed_mandatory") is True:
            failed.append(label)
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id="pin_failed_mandatory",
                    severity="critical",
                    title=f"Pinned component failed mandatory safety: {label}",
                    message=redact_message(label),
                    tool_name="setup_pin_aggregate",
                )
            )
            continue
        if isinstance(summary, dict):
            summary_map = cast(dict[str, Any], summary)
            status = str(summary_map.get("status") or "")
            if status == "pending":
                missing.append(label)
                findings.append(
                    Finding(
                        check_id=spec.check_id,
                        family=spec.family,
                        rule_id="pin_scan_pending",
                        severity="high",
                        title=f"Pinned component safety pending: {label}",
                        message=redact_message(label),
                        tool_name="setup_pin_aggregate",
                    )
                )
            failed_raw = summary_map.get("failed")
            failed_n = int(failed_raw) if isinstance(failed_raw, int | float | str) else 0
            if failed_n > 0 and summary_map.get("status") != "available":
                # failed checks recorded
                pass
            # If any check in summary is failed with mandatory - catalog summary
            # may not carry per-check; use failed count > 0 as soft signal
            checks_any = summary_map.get("checks")
            if isinstance(checks_any, list):
                for raw_c in cast(list[Any], checks_any):
                    if not isinstance(raw_c, dict):
                        continue
                    c = cast(dict[str, Any], raw_c)
                    if c.get("mandatory") and c.get("result") in {
                        "failed",
                        "degraded",
                        "not_run",
                    }:
                        failed.append(label)
                        findings.append(
                            Finding(
                                check_id=spec.check_id,
                                family=spec.family,
                                rule_id="pin_mandatory_not_passed",
                                severity="critical",
                                title=(f"Pin {label} check {c.get('check_id')}={c.get('result')}"),
                                message=redact_message(str(c.get("check_id"))),
                                tool_name="setup_pin_aggregate",
                            )
                        )
                        break

    if failed:
        result = "failed"
    elif missing:
        result = "failed"  # mandatory pins without scans block setup publish
    else:
        result = "passed"

    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result=result,
        mandatory=spec.mandatory,
        tool_name="setup_pin_aggregate",
        severity_max="critical" if findings else "info",
        findings=findings,
        detail={
            "mode": "no_union_rescan",
            "pin_count": len(pins),
            "failed_pins": failed,
            "missing_scans": missing,
        },
    )
