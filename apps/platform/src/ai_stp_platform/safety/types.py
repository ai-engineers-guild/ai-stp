"""Shared safety-scan result types."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, cast

_PUBLIC_LIMIT = 16
_RULE_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+ /-]{0,239}$")
_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass(slots=True)
class Finding:
    """One redacted finding; never stores raw secret material."""

    check_id: str
    family: str
    rule_id: str
    severity: str  # info | low | medium | high | critical
    title: str
    path: str | None = None
    message: str = ""
    tool_name: str = ""
    fingerprint: str = ""


@dataclass(slots=True)
class CheckOutcome:
    """Result of one planned check."""

    check_id: str
    family: str
    result: str
    source: str = "platform_safety_scan"
    mandatory: bool = True
    tool_name: str = ""
    tool_version: str = ""
    duration_ms: int = 0
    severity_max: str = "info"
    findings: list[Finding] = field(default_factory=list[Finding])
    detail: dict[str, Any] = field(default_factory=dict[str, Any])

    def as_binding(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "family": self.family,
            "result": self.result,
            "source": self.source,
            "mandatory": self.mandatory,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "duration_ms": self.duration_ms,
            "severity_max": self.severity_max,
            "reason": self.reason(),
            "finding_summary": self.public_finding_summary(),
        }

    def public_finding_summary(self) -> dict[str, object] | None:
        """Return bounded identifiers only, never scanner or artifact content."""
        if not self.findings:
            return None
        rules = sorted({_public_rule_id(finding) for finding in self.findings})
        paths = sorted(
            {
                safe
                for finding in self.findings
                if finding.path and (safe := _public_path(finding.path)) is not None
            }
        )
        severity = max(
            (finding.severity for finding in self.findings),
            key=lambda value: _SEVERITY_RANK.get(value, 0),
        )
        return {
            "schema_version": 1,
            "count": len(self.findings),
            "severity_max": severity if severity in _SEVERITY_RANK else "info",
            "rule_ids": rules[:_PUBLIC_LIMIT],
            "paths": paths[:_PUBLIC_LIMIT],
            "truncated": len(rules) > _PUBLIC_LIMIT or len(paths) > _PUBLIC_LIMIT,
        }

    def reason(self) -> str | None:
        """Why this did not pass, short enough for a wire and safe to send.

        Rule identifiers and counts, never the scanned content: this reaches a
        client, and a message quoting what was found would put the artefact's
        bytes somewhere the artefact is not.
        """
        if self.result == "passed":
            return None
        timed_out = self.detail.get("timed_out")
        if timed_out:
            limit = self.detail.get("timeout_seconds")
            names = ", ".join(str(item) for item in cast(list[object], timed_out))
            # A limit nobody recorded is said as an absence. Interpolating it
            # produced "did not finish within Nones", which reads as a defect in
            # this reporter rather than as a timeout, and the repair for the two
            # is not the same. Met in the wild during a publication, where it
            # cost a trip into this file to learn what it meant.
            if limit is None:
                return f"did not finish, and no limit was recorded: {names}"[:200]
            return f"did not finish within {limit}s: {names}"[:200]
        no_report = self.detail.get("no_report")
        if no_report:
            # Named apart from a timeout because the repairs differ: a timeout
            # is a busy worker, this is a tool that could not start at all.
            names = ", ".join(str(item) for item in cast(list[object], no_report))
            return f"ran without producing a report: {names}"[:200]
        if self.findings:
            rules = sorted({finding.rule_id for finding in self.findings})
            shown = ", ".join(rules[:5])
            more = f" and {len(rules) - 5} more" if len(rules) > 5 else ""
            return f"{len(self.findings)} finding(s): {shown}{more}"[:200]
        return f"result {self.result}"[:200]


@dataclass(slots=True)
class ArtifactManifest:
    """Detected features of an unpacked artifact tree."""

    component_type: str
    languages: set[str] = field(default_factory=set[str])
    flags: set[str] = field(default_factory=set[str])
    file_count: int = 0
    total_bytes: int = 0
    text_files: list[str] = field(default_factory=list[str])
    shell_files: list[str] = field(default_factory=list[str])
    python_files: list[str] = field(default_factory=list[str])
    read_errors: list[str] = field(default_factory=list[str])

    def record_read_error(self, relative_path: str) -> None:
        """Keep unreadable files visible to the verdict instead of skipping them."""
        if relative_path not in self.read_errors:
            self.read_errors.append(relative_path)


@dataclass(slots=True)
class SafetyScanResult:
    """Complete suite output for one digest + policy_version."""

    content_digest: str
    policy_version: str
    profile: str
    outcomes: list[CheckOutcome]
    object_kind: str = "component"
    cache_hit: bool = False
    wall_ms: int = 0
    workdir: str | None = None

    def bindings(self) -> list[dict[str, Any]]:
        return [o.as_binding() for o in self.outcomes]

    def all_findings(self) -> list[Finding]:
        out: list[Finding] = []
        for outcome in self.outcomes:
            out.extend(outcome.findings)
        return out


def _public_rule_id(finding: Finding) -> str:
    rule = finding.rule_id.lower()
    if _RULE_ID.fullmatch(rule):
        return rule
    tool = finding.tool_name.lower().replace("-", "_")
    return f"{tool}_finding" if _RULE_ID.fullmatch(tool) else "scanner_finding"


def _public_path(value: str) -> str | None:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or not _SAFE_PATH.fullmatch(normalized):
        return None
    return path.as_posix()
