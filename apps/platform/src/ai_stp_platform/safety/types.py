"""Shared safety-scan result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
        }


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


@dataclass(slots=True)
class SafetyScanResult:
    """Complete suite output for one digest + policy_version."""

    content_digest: str
    policy_version: str
    profile: str
    outcomes: list[CheckOutcome]
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
