"""Versioned check registry and safety profiles.

``policy_version`` is frozen with the publication plan. Changing mandatory
checks requires a new policy version so old evidence can expire cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

POLICY_VERSION = "safety-1"

CheckResultName = Literal[
    "passed", "warning", "failed", "degraded", "not_run", "not_applicable", "skipped"
]
EvidenceSource = Literal[
    "platform_safety_scan",
    "platform_structure_verified",
    "platform_digest_verified",
    "author_attested",
]


class SafetyProfile(StrEnum):
    """Runtime profile gates optional heavy engines."""

    MINIMAL = "minimal"
    STANDARD = "standard"
    STRICT = "strict"


@dataclass(frozen=True, slots=True)
class CheckSpec:
    """One registered safety check."""

    check_id: str
    family: str
    mandatory: bool
    timeout_seconds: float
    stage: int
    # kinds: empty means all component kinds; setup handled separately
    kinds: frozenset[str]
    # language gates: empty means no language requirement
    languages: frozenset[str]
    # flags from detect: mcp, skill_md, hooks, shell, pdf, html, binary
    requires_any_flag: frozenset[str]
    profiles: frozenset[SafetyProfile]
    weight: float = 1.0


# Stage numbers match the session plan S0-S7 (compressed for MVP).
CHECK_REGISTRY: tuple[CheckSpec, ...] = (
    CheckSpec(
        check_id="artifact_unpack",
        family="unpack",
        mandatory=True,
        timeout_seconds=30,
        stage=0,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.MINIMAL, SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=2.0,
    ),
    CheckSpec(
        check_id="path_denylist",
        family="path",
        mandatory=True,
        timeout_seconds=15,
        stage=0,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.MINIMAL, SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=2.0,
    ),
    CheckSpec(
        check_id="secrets_heuristic",
        family="secrets",
        mandatory=True,
        timeout_seconds=20,
        stage=0,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.MINIMAL, SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=2.0,
    ),
    CheckSpec(
        # Mandatory when it runs with findings; missing binary → not_run (non-blocking).
        # In-proc secrets_heuristic remains the always-on secrets gate.
        check_id="secrets_gitleaks",
        family="secrets",
        mandatory=False,
        timeout_seconds=15,
        stage=1,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.MINIMAL, SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=2.0,
    ),
    CheckSpec(
        check_id="pi_content_pack",
        family="prompt_injection",
        mandatory=False,
        timeout_seconds=20,
        stage=2,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=0.5,
    ),
    CheckSpec(
        check_id="content_hidden",
        family="content_stego",
        mandatory=False,
        timeout_seconds=30,
        stage=2,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=0.5,
    ),
    CheckSpec(
        check_id="sast_opengrep",
        family="sast_generic",
        mandatory=False,
        timeout_seconds=20,
        stage=3,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.0,
    ),
    CheckSpec(
        check_id="mcp_config_static",
        family="mcp_config",
        mandatory=True,
        timeout_seconds=15,
        stage=4,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset({"mcp"}),
        profiles=frozenset({SafetyProfile.MINIMAL, SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.5,
    ),
    CheckSpec(
        check_id="hook_schema_static",
        family="hook_schema",
        mandatory=True,
        timeout_seconds=15,
        stage=4,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset({"hooks"}),
        profiles=frozenset({SafetyProfile.MINIMAL, SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.5,
    ),
    CheckSpec(
        check_id="hook_command_argv",
        family="hook_command",
        mandatory=True,
        timeout_seconds=15,
        stage=4,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset({"hooks"}),
        profiles=frozenset({SafetyProfile.MINIMAL, SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.5,
    ),
    CheckSpec(
        check_id="skill_static_gate",
        family="skill_static",
        mandatory=True,
        # Sixty rather than twenty, measured rather than guessed: one
        # `skillspector` pass over a real component tree takes about nine
        # seconds on an idle worker, and publishing a corpus of a hundred
        # objects put enough of them in flight at once to cross the old limit.
        # The adapter now reports a timeout honestly instead of as a finding,
        # which makes a too-small limit visible — but visible is not the same
        # as fixed, and a static analyser needs room to finish.
        timeout_seconds=60,
        stage=4,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset({"skill_md", "agent"}),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.5,
    ),
    CheckSpec(
        check_id="shell_obfuscation",
        family="shell_obfuscation",
        mandatory=False,
        timeout_seconds=10,
        stage=5,
        kinds=frozenset({"component"}),
        languages=frozenset({"shell"}),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.0,
    ),
    CheckSpec(
        check_id="sast_shellcheck",
        family="sast_shell",
        mandatory=False,
        timeout_seconds=15,
        stage=5,
        kinds=frozenset({"component"}),
        languages=frozenset({"shell"}),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.0,
    ),
    CheckSpec(
        check_id="sast_bandit",
        family="sast_python",
        mandatory=False,
        timeout_seconds=15,
        stage=5,
        kinds=frozenset({"component"}),
        languages=frozenset({"python"}),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.0,
    ),
    CheckSpec(
        check_id="sca_pip_audit",
        family="sca_python",
        mandatory=False,
        timeout_seconds=20,
        stage=5,
        kinds=frozenset({"component"}),
        languages=frozenset({"python"}),
        requires_any_flag=frozenset({"manifests"}),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.0,
    ),
    CheckSpec(
        check_id="sast_gosec",
        family="sast_go",
        mandatory=False,
        timeout_seconds=20,
        stage=5,
        kinds=frozenset({"component"}),
        languages=frozenset({"go"}),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.0,
    ),
    CheckSpec(
        check_id="sca_govulncheck",
        family="sca_go",
        mandatory=False,
        timeout_seconds=20,
        stage=5,
        kinds=frozenset({"component"}),
        languages=frozenset({"go"}),
        requires_any_flag=frozenset({"manifests"}),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.0,
    ),
    CheckSpec(
        check_id="sca_cargo_audit",
        family="sca_rust",
        mandatory=False,
        timeout_seconds=20,
        stage=5,
        kinds=frozenset({"component"}),
        languages=frozenset({"rust"}),
        requires_any_flag=frozenset({"manifests"}),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.0,
    ),
    CheckSpec(
        check_id="sast_eslint_security",
        family="sast_js",
        mandatory=False,
        timeout_seconds=20,
        stage=5,
        kinds=frozenset({"component"}),
        languages=frozenset({"js"}),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.0,
    ),
    CheckSpec(
        check_id="sca_npm_audit",
        family="sca_js",
        mandatory=False,
        timeout_seconds=20,
        stage=5,
        kinds=frozenset({"component"}),
        languages=frozenset({"js"}),
        requires_any_flag=frozenset({"manifests"}),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.0,
    ),
    CheckSpec(
        check_id="sca_cargo_deny",
        family="sca_rust_policy",
        mandatory=False,
        timeout_seconds=20,
        stage=5,
        kinds=frozenset({"component"}),
        languages=frozenset({"rust"}),
        requires_any_flag=frozenset({"manifests"}),
        profiles=frozenset({SafetyProfile.STRICT}),
        weight=1.0,
    ),
    CheckSpec(
        check_id="document_pdf",
        family="document_pdf",
        mandatory=False,
        timeout_seconds=20,
        stage=6,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset({"pdf"}),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=0.5,
    ),
    CheckSpec(
        check_id="sca_osv",
        family="sca",
        mandatory=False,
        timeout_seconds=25,
        stage=6,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset({"manifests"}),
        profiles=frozenset({SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.0,
    ),
    CheckSpec(
        check_id="malware_clamav",
        family="malware",
        mandatory=False,
        timeout_seconds=15,
        stage=7,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset({"binary"}),
        profiles=frozenset({SafetyProfile.STRICT}),
        weight=2.0,
    ),
    CheckSpec(
        check_id="malware_yara",
        family="malware_yara",
        mandatory=False,
        timeout_seconds=15,
        stage=7,
        kinds=frozenset({"component"}),
        languages=frozenset(),
        requires_any_flag=frozenset({"binary"}),
        profiles=frozenset({SafetyProfile.STRICT}),
        weight=1.5,
    ),
    CheckSpec(
        check_id="setup_pin_aggregate",
        family="setup_aggregate",
        mandatory=True,
        timeout_seconds=10,
        stage=0,
        kinds=frozenset({"setup"}),
        languages=frozenset(),
        requires_any_flag=frozenset(),
        profiles=frozenset({SafetyProfile.MINIMAL, SafetyProfile.STANDARD, SafetyProfile.STRICT}),
        weight=1.0,
    ),
)


def registry_by_id() -> dict[str, CheckSpec]:
    return {spec.check_id: spec for spec in CHECK_REGISTRY}
