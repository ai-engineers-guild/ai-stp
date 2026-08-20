"""Dual skill engine gate: SkillSpector + Cisco skill-scanner merge."""

from __future__ import annotations

import re
from pathlib import Path

from ai_stp_platform.safety.adapters._cli import run_cli, which
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

# Static in-proc patterns when CLIs absent (still real path on SKILL.md).
SKILL_RISK = [
    (re.compile(r"(?i)curl\s+.*\|\s*(bash|sh)"), "skill_pipe_shell", "critical"),
    (re.compile(r"(?i)ignore\s+previous\s+instructions"), "skill_pi", "high"),
    (re.compile(r"(?i)exfiltrat|steal\s+(credentials|secrets|tokens)"), "skill_exfil", "critical"),
    (re.compile(r"(?i)rm\s+-rf\s+/"), "skill_rm_root", "critical"),
    (re.compile(r"(?i)cat\s+~/?\.ssh|read\s+id_rsa"), "skill_ssh_read", "high"),
    # Medium: preference-hijack language (warning-class for skill gate).
    (
        re.compile(r"(?i)always\s+prefer\s+this\s+skill\s+over\s+any\s+other"),
        "skill_prefer_hijack",
        "medium",
    ),
]


def run(tree: Path, manifest: ArtifactManifest, spec: CheckSpec) -> CheckOutcome:
    del manifest
    findings: list[Finding] = []
    tools_run: list[str] = []
    engines_missing = 0

    # NVIDIA SkillSpector (static only) + Cisco skill-scanner (static default;
    # do not pass --use-llm — publication validate must not call model APIs).
    for tool, argv in (
        ("skillspector", ["skillspector", "scan", str(tree), "--no-llm", "--format", "json"]),
        ("skill-scanner", ["skill-scanner", "scan", str(tree), "--format", "json"]),
    ):
        if which(tool) is None:
            engines_missing += 1
            continue
        code, out, err, _ms = run_cli(argv, cwd=tree, timeout=min(spec.timeout_seconds, 20))
        tools_run.append(tool)
        if code not in (0, 127) and (out or err or code == 1):
            findings.append(
                Finding(
                    check_id=spec.check_id,
                    family=spec.family,
                    rule_id=f"{tool}_finding",
                    severity="high",
                    title=f"{tool} reported skill risks",
                    message=redact_message((out or err or "findings")[:300]),
                    tool_name=tool,
                )
            )

    # Always run owned static pass on SKILL.md files (merge into same gate)
    for path in tree.rglob("SKILL.md"):
        rel = path.relative_to(tree).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern, rule, sev in SKILL_RISK:
            if pattern.search(text):
                findings.append(
                    Finding(
                        check_id=spec.check_id,
                        family=spec.family,
                        rule_id=rule,
                        severity=sev,
                        title=f"Skill static risk: {rule}",
                        path=rel,
                        message=redact_message(rule),
                        tool_name="skill_static_owned",
                    )
                )

    # If both CLIs missing but owned static ran — still a complete gate
    if engines_missing == 2 and not tools_run:
        tools_run.append("skill_static_owned")

    result = (
        "failed"
        if any(f.severity in {"high", "critical"} for f in findings)
        else ("warning" if findings else "passed")
    )
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result=result,
        mandatory=spec.mandatory,
        tool_name="+".join(tools_run) or "skill_static_gate",
        severity_max=max((f.severity for f in findings), default="info", key=_rank),
        findings=findings,
        detail={"engines_missing": engines_missing, "tools": tools_run},
    )


def _rank(s: str) -> int:
    return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(s, 0)
