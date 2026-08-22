"""Dual skill engine gate: SkillSpector + Cisco skill-scanner merge."""

from __future__ import annotations

import json
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

    # Both engines load a *skill package*, so they are pointed at the directory
    # holding a `SKILL.md` rather than at the artefact root. Handed the root of
    # a tree whose skill sits one level down, `skill-scanner` answers
    # `Error loading skill: SKILL.md not found`, exit 1, nothing on stdout —
    # which the gate used to record as "skill-scanner reported skill risks".
    # That refused ninety-six components of a hundred and three for content the
    # scanner never read, and blocked every setup pinning one.
    #
    # The owned static pass below already knew where the packages are. This is
    # the same walk, applied to the engines.
    packages = _packages(tree)
    timed_out: list[str] = []
    no_report: list[str] = []
    for tool, argv in (
        ("skillspector", ["skillspector", "scan", "{}", "--no-llm", "--format", "json"]),
        ("skill-scanner", ["skill-scanner", "scan", "{}", "--format", "json"]),
    ):
        if which(tool) is None:
            engines_missing += 1
            continue
        if not packages:
            # An `agent` component need not carry a `SKILL.md` at all, and an
            # engine that can only load a skill package has nothing to say
            # about one. Not run rather than run-and-refused: the second would
            # report the artefact as dangerous for not being a skill.
            continue
        code, out = _scan_packages(tool, argv, tree, packages, spec.timeout_seconds)
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
            timed_out.append(tool)
            continue
        if code in (0, _MISSING_EXIT):
            continue
        report = _report(out)
        if report is None:
            # The tool exited non-zero without a report. That is the tool
            # refusing to run — a bad argument, a missing interpreter, a
            # sandbox it could not enter — and it is not a statement about the
            # object. Recording it as a `high` finding titled "reported skill
            # risks" says the opposite of what happened, and it says it about
            # somebody's component.
            #
            # The discriminator is the report, not the exit code: these tools
            # are asked for `--format json` and a scanner that scanned writes
            # one. A code alone cannot tell "found something" from "could not
            # start", and every code but zero was being read as the first.
            no_report.append(tool)
            continue
        findings.append(
            Finding(
                check_id=spec.check_id,
                family=spec.family,
                rule_id=f"{tool}_finding",
                severity="high",
                title=f"{tool} reported skill risks",
                message=redact_message(report[:300]),
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
    elif timed_out or no_report:
        # Ordered after a real finding on purpose: an engine that did report
        # something has said more than one that could not.
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
            # How many skill packages the engines were pointed at. Zero means
            # the artefact carries no `SKILL.md`, so the engines had nothing to
            # load and were not run — which is a different fact from an engine
            # that ran and refused, and used to be indistinguishable.
            "skill_packages": len(packages),
            "timed_out": timed_out,
            # Ran, exited non-zero, produced no report. Kept apart from a
            # timeout because the repairs differ: one is a busy worker, the
            # other is an argument or an image.
            "no_report": no_report,
            # What the tool was actually given, not what the policy asked for.
            # A report naming the declared value after a shorter kill sends
            # somebody looking in the wrong file.
            "timeout_seconds": effective_timeout(spec.timeout_seconds),
        },
    )


def _packages(tree: Path) -> tuple[Path, ...]:
    """Every skill package in this artefact: the directories holding a `SKILL.md`.

    Sorted so two runs over the same bytes scan in the same order and produce
    the same report, which is what lets an identical artefact reach an
    identical verdict.
    """
    return tuple(sorted({path.parent for path in tree.rglob("SKILL.md")}))


def _scan_packages(
    tool: str,
    argv: list[str],
    tree: Path,
    packages: tuple[Path, ...],
    timeout: float,
) -> tuple[int, str]:
    """Run one engine over each package; return the first result worth acting on.

    A timeout anywhere is a timeout for the engine — the measurement is
    incomplete whatever the other packages said. Otherwise the first package
    that produced a report wins, because a report is the thing the caller can
    act on; if none did, the last exit code is returned so the caller can see
    the engine never reported at all.
    """
    del tool
    last = 0
    for package in packages:
        code, out, _err, _ms = run_cli(
            [str(package) if item == "{}" else item for item in argv],
            cwd=tree,
            timeout=timeout,
        )
        if code == _TIMEOUT_EXIT:
            return code, ""
        if _report(out) is not None:
            return code, out
        last = code
    return last, ""


def _report(stdout: str) -> str | None:
    """The tool's own report, or nothing to read.

    Both engines are invoked with `--format json`, so a run that reached a
    verdict leaves JSON on stdout. Anything else — empty, a usage message, a
    traceback — is the tool not having produced a verdict, whatever it exited
    with.

    An empty JSON report counts as a report: a scanner that ran and found
    nothing still ran, and its exit code is its own business.
    """
    text = stdout.strip()
    if not text:
        return None
    try:
        json.loads(text)
    except ValueError:
        return None
    return text


def _rank(s: str) -> int:
    return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(s, 0)
