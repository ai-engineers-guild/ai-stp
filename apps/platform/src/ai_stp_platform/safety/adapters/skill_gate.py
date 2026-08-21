"""Dual skill engine gate: SkillSpector + Cisco skill-scanner merge."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from ai_stp_platform.safety.adapters._cli import effective_timeout, run_cli, which
from ai_stp_platform.safety.normalize import redact_message
from ai_stp_platform.safety.policy import CheckSpec
from ai_stp_platform.safety.types import ArtifactManifest, CheckOutcome, Finding

#: `timeout(1)` reports this when it kills the child. Distinguished from every
#: other non-zero code because it means the tool was interrupted rather than
#: that it decided anything.
_TIMEOUT_EXIT: Final[int] = 124
#: The shell's "command not found". `which` normally catches an absent tool
#: first; this covers the race where it disappears between the two.
_MISSING_EXIT: Final[int] = 127

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
    incomplete: list[str] = []
    for tool, argv in (
        ("skillspector", ["skillspector", "scan", str(tree), "--no-llm", "--format", "json"]),
        ("skill-scanner", ["skill-scanner", "scan", str(tree), "--format", "json"]),
    ):
        if which(tool) is None:
            engines_missing += 1
            continue
        code, out, err, _ms = run_cli(argv, cwd=tree, timeout=spec.timeout_seconds)
        tools_run.append(tool)
        if code == _TIMEOUT_EXIT:
            # A measurement that did not finish is not a negative measurement.
            # This used to be recorded as a `high` finding titled "reported skill
            # risks", which says the opposite of what happened: the scanner found
            # nothing, because it never got that far. Publishing a whole corpus
            # made it visible — one static analyser takes about nine seconds on
            # an idle worker, and under a burst it crossed the limit and every
            # affected object was refused as dangerous content.
            #
            # `degraded` is what the neighbouring adapters already return when
            # their tool cannot run, and it still blocks a mandatory check. The
            # difference is that it blocks with the truth.
            incomplete.append(tool)
            continue
        if code not in (0, _MISSING_EXIT) and (out or err or code == 1):
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

    if any(f.severity in {"high", "critical"} for f in findings):
        result = "failed"
    elif incomplete:
        # Ordered after a real finding on purpose: an engine that did report
        # something has said more than one that ran out of time.
        result = "degraded"
    else:
        result = "warning" if findings else "passed"
    return CheckOutcome(
        check_id=spec.check_id,
        family=spec.family,
        result=result,
        mandatory=spec.mandatory,
        tool_name="+".join(tools_run) or "skill_static_gate",
        severity_max=max((f.severity for f in findings), default="info", key=_rank),
        findings=findings,
        detail={
            "engines_missing": engines_missing,
            "tools": tools_run,
            "timed_out": incomplete,
            # What the tool was actually given, not what the policy asked for.
            # A report naming the declared value after a shorter kill sends
            # somebody looking in the wrong file.
            "timeout_seconds": effective_timeout(spec.timeout_seconds),
        },
    )


def _rank(s: str) -> int:
    return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(s, 0)
