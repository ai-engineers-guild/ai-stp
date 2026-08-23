"""Skill gate: Cisco scanner verdict plus independent owned static rules."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

from ai_stp_platform.safety.adapters._cli import (
    deadline_expired,
    effective_timeout,
    run_cli,
    which,
)
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
#: What an owned keyword match is worth once a real engine has read the same
#: file. `medium` is already the gate's word for "a human should look at this",
#: and it does not by itself refuse.
_ADVISORY: Final[str] = "medium"

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
    findings: list[Finding] = []
    tools_run: list[str] = []
    #: Engines that reached a verdict on this artefact, clean or otherwise.
    #: Distinct from `tools_run`, which also holds engines that timed out or
    #: refused to start — neither of those read anything.
    reported: list[str] = []
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
        (
            "skill-scanner",
            ["skill-scanner", "scan", "{}", "--format", "json", "--use-behavioral"],
        ),
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
        code, reports, incomplete = _scan_packages(argv, tree, packages, spec.timeout_seconds)
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
        if reports:
            reported.append(tool)
            for report_code, report in reports:
                if report_code == 0:
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
        if incomplete:
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

    # The owned static pass always runs, and always contributes — but it does
    # not always decide. It is a keyword scan, and a keyword scan cannot tell a
    # skill that exfiltrates data from a skill whose job is to review code for
    # exfiltration. Both contain the word.
    #
    # That is not hypothetical: two security-review skills in the first-party
    # corpus were refused as `critical` for naming the risk they exist to find,
    # while both real engines read the same file and returned `is_safe: true`.
    # A regex overruling two purpose-built analysers that examined the same
    # bytes is the fallback outranking the thing it stands in for.
    #
    # So when an engine actually reported, the owned findings are advisory: they
    # stay in the record, visible on the object, at a severity that does not by
    # itself refuse. When no engine could look — the case this pass was written
    # for — they keep their full weight, because then they are the only reading
    # anyone has.
    decisive = not reported
    for path in tree.rglob("SKILL.md"):
        rel = path.relative_to(tree).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            manifest.record_read_error(rel)
            continue
        for pattern, rule, sev in SKILL_RISK:
            if _non_defensive_match(pattern, text):
                findings.append(
                    Finding(
                        check_id=spec.check_id,
                        family=spec.family,
                        rule_id=rule,
                        severity=sev if decisive else _ADVISORY,
                        title=f"Skill static risk: {rule}",
                        path=rel,
                        message=redact_message(rule),
                        tool_name="skill_static_owned",
                    )
                )

    # The owned pass is useful context, but it is not a replacement for the
    # mandatory external engine. Missing it must remain incomplete.
    if engines_missing == 1 and packages:
        tools_run.append("skill_static_owned")
        no_report.append("skill-scanner")

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
    argv: list[str],
    tree: Path,
    packages: tuple[Path, ...],
    timeout: float,
) -> tuple[int, list[tuple[int, str]], int]:
    """Run one engine over every package and retain every report.

    A timeout or missing report for any package keeps the engine incomplete;
    one clean package must not hide an unread package later in the tree.
    """
    last = 0
    reports: list[tuple[int, str]] = []
    incomplete = 0
    for index, package in enumerate(packages):
        if deadline_expired():
            return _TIMEOUT_EXIT, reports, len(packages) - index
        code, out, _, _ = run_cli(
            [str(package) if item == "{}" else item for item in argv],
            cwd=tree,
            timeout=timeout,
        )
        if code == _TIMEOUT_EXIT:
            return code, reports, len(packages) - index
        report = _report(out)
        if report is not None:
            reports.append((code, report))
        else:
            incomplete += 1
        last = code
    return last, reports, incomplete


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


def _non_defensive_match(pattern: re.Pattern[str], text: str) -> bool:
    for line in text.splitlines():
        if pattern.search(line) and not re.search(
            r"(?i)\b(?:do not|don't|never|avoid|must not|detect|block|forbid(?:den)?)\b", line
        ):
            return True
    return False
