#!/usr/bin/env python3
"""Check semantic regressions, retired terms, branch policy, and validation coverage.

Run through just rather than directly:

    just docs-static

The regular docs_lint checks document shape. This linter checks meaning: a decision
accepted in an ADR must not return to normative text under another name. Such an
error does not break links or markup, so it needs a separate pass.

Term checks skip the history in docs/adr/: a superseded decision must be able to
describe what it replaced.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Normative roots. docs/adr describes decision history and is excluded here.
NORMATIVE_GLOBS = ("docs/**/*.md", "specs/**/*.md")
HISTORY_DIR = "docs/adr"
ROOT_DOCS = (
    "README.md",
    "README.ru.md",
    "AGENTS.md",
    "QUICKSTART.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
)

# Eight component types under ADR-0015. Each must have a matrix row.
COMPONENT_TYPES = (
    "instruction",
    "skill",
    "mcp",
    "hook",
    "command",
    "agent",
    "plugin",
    "setting",
)

# MCP transport classes from validation-policy.md.
MCP_TRANSPORTS = ("local_exec", "package", "remote_https")

VALIDATION_POLICY = Path("docs/contracts/validation-policy.md")
PASSPORTS_DOC = Path("docs/contracts/component-setup-passports.md")

# Canonical sidecar filenames used by the CLI to identify a described object.
SIDECAR_NAMES = ("ai-stp.component.yaml", "ai-stp.setup.yaml")
#: The gate whose push branches must match the documented branch model. Which
#: file that is depends on the tree: the working copy runs no workflows of its
#: own any more (`ADR-0110`), so the gate it holds is the overlay it publishes,
#: while the built tree holds that same file as its actual gate. Resolved rather
#: than fixed, because the property is about the gate that runs and not about a
#: path.
_OVERLAY_WORKFLOW = Path("release_scripts/public_overlay/.github/workflows/check.yml")
WORKFLOW = Path(".github/workflows/check.yml")
GIT_WORKFLOW_DOC = Path("docs/engineering/git-workflow.md")
REPO_STRUCTURE_DOC = Path("docs/engineering/repository-structure.md")
SERENA_IGNORE = Path(".serena/.gitignore")

# State files for a specific checkout: they contain a SHA, branch, and absolute path.
SERENA_TRANSIENT = (
    ".serena/.auto_sync_head",
    ".serena/.flow_blocker_ack.json",
    ".serena/.flow_post_task_state.json",
    ".serena/.flow_sync_marker",
    ".serena/.serena_sync_state.json",
)


@dataclass(frozen=True)
class BannedTerm:
    pattern: str
    code: str
    reason: str


BANNED_TERMS = (
    BannedTerm(
        r"\binclude_unverified\b",
        "CT050",
        "indefinite global consent was removed: use the session flag and scope records (ADR-0029)",
    ),
    BannedTerm(
        r"\bmanifest_digest\b",
        "CT001",
        "versions are described by passports: use passport_digest (ADR-0012, ADR-0014)",
    ),
    BannedTerm(
        r"ai-stp:manifest:v1",
        "CT002",
        "the version manifest namespace does not exist: use ai-stp:passport:v1 (ADR-0014)",
    ),
    BannedTerm(
        r"\bSetupVariant\b",
        "CT003",
        "a setup belongs to one harness; there is no separate variant entity (ADR-0014)",
    ),
    BannedTerm(
        r"\binferred\b",
        "CT004",
        "inferred provenance was removed: use derived with a recorded rule (ADR-0021)",
    ),
    BannedTerm(
        r"\bFitRun\b|\bno_verified_candidate\b",
        "CT008",
        "the product searches and composes rather than fitting: use SelectionRun and no_candidate",
    ),
    BannedTerm(
        r"`unsupported_apply`",
        "CT009",
        "unsupported application is an error code, not a readiness-axis state",
    ),
)

# `variant_id` is valid for a component and forbidden for a setup. Catch only explicit pairings.
SETUP_VARIANT_RE = re.compile(
    r"setup[^.\n]{0,60}`variant_id`|`variant_id`[^.\n]{0,60}setup",
    re.IGNORECASE,
)

# `marketplace` as a component type. The word itself is valid as a projection_kind
# and native harness surface, so only the type enumeration is checked.
MARKETPLACE_AS_TYPE_RE = re.compile(
    r"component_type[^.\n]{0,120}\bmarketplace\b"
    r"|\bmarketplace\b[^.\n]{0,80}component_type",
    re.IGNORECASE,
)

# `succeeded` as the success state of a mutating operation. Worker jobs have their own state.
OPERATION_SUCCEEDED_RE = re.compile(
    r"operation[^.\n]{0,160}`succeeded`",
    re.IGNORECASE,
)

# Returns of closed vision decisions (ADR-0025..0034). These checks bypass
# NEGATION_RE because the forbidden formulations themselves can be negated.
CEILING_RE = re.compile(r"product target number|not planned to expand")
WEB_ONLY_RE = re.compile(
    r"(?:site|web)[^\n]{0,60}?only for[^\n]{0,60}?(?:installation|sign-in|search)",
)
COUNTS_RE = re.compile(
    r"\b\d{1,4} ADR\b|\b\d{1,4} active specifications"
    r"|\bwith \d{1,4} requirements|\b\d{1,4} requirements\b",
)
#: A claim about which phase is finished or starting. `implementation-roadmap.md`
#: owns that fact; anywhere else it is a copy that goes stale on the next phase.
#: It did: `scope.md` said phase 1 was beginning while the roadmap had it done.
PHASE_STATE_RE = re.compile(
    r"phase \d+[^\n]{0,40}(finished|starting)|(starting|finished) phase \d+",
)

NOT_RUN_PUBLISH_RE = re.compile(
    r"does not block|not_run[^\n]{0,80}(?:is|gets?)\s+published",
    re.IGNORECASE,
)
NOT_RUN_BLOCKING_RE = re.compile(r"blocks?[^\n]{0,30}(?:publish|publication)", re.IGNORECASE)
DEV_PASSPORT_RE = re.compile(r"DeveloperPassport", re.IGNORECASE)
ENV_FACT_RE = re.compile(
    r"\bOS\b|\barchitecture\b|operating system|architecture"
    r"|installed harness|tool version",
)
#: The exemption for CT055: a line saying the environment does **not** belong to
#: the developer passport. What matters is that the negation binds to the
#: passport, not that a negation appears somewhere on the line.
#:
#: The skip pattern must bind negation to the passport, not merely find a
#: negation somewhere on the line. This prevents unrelated clauses from hiding
#: a real violation while allowing the documented exemption.
#:
#: Measured before changing it: the old regex exempted **zero** lines in the
#: scanned tree. It had no members and cost the check its teeth.
DEV_PASSPORT_SKIP_RE = re.compile(
    r"(?:does not|doesn't|not)\s+(?:\S+\s+){0,3}(?:in\s+|from\s+)?DeveloperPassport"
    r"|DeveloperPassport\s+(?:\S+\s+){0,2}(?:does not|doesn't|not)\s",
    re.IGNORECASE,
)
REPORT_EXCLUDED_RE = re.compile(
    r"no (?:user )?complaint channel[^\n]{0,30}|user complaint[^\n]{0,30}component",
)
PLATFORM_ONLY_RE = re.compile(
    r"full set of required checks[^\n]{0,60}"
    r"(?:runs|executes)[^\n]{0,40}on (?:the )?(?:platform )?server",
    re.IGNORECASE,
)
BARE_ID_RE = re.compile(
    r"^\s*(?:\"id\"|id):\s*\"?(?:component_|setup_|developer_|device_|project_)",
)

# Canonical owners of closed decisions: the file and markers without which a
# decision is lost. Removing an owner or marker is a regression, not cleanup.
VISION_CONTRACTS = {
    Path("docs/contracts/device-passport.md"): ("not merged",),
    Path("docs/contracts/unverified-consent.md"): ("`publisher`", "`object_major`"),
    Path("docs/contracts/access-grants-and-forks.md"): ("An unchanged clone",),
    Path("docs/contracts/report-case.md"): ("is not created automatically",),
    Path("docs/contracts/selection-proposal.md"): ("is atomic",),
}
REPORTS_SPEC = Path("specs/active/SPEC-016-reports-moderation.md")
ELIGIBILITY_MARKERS = ("Installation eligibility", "blocked for new installations and updates")
ATTESTATION_MARKER = "Author attestation"


# A canonical document must name a retired term so it can forbid it. A negated
# sentence states the rule rather than violating it; a returned term is introduced
# affirmatively as a field or allowed value.
NEGATION_RE = re.compile(
    r"\b(?:no|not|never)\b|\b(?:is|are|was|were|has been) removed\b|\bdoes not\b|\bhas no\b",
    re.IGNORECASE,
)


@dataclass
class Issue:
    path: str
    code: str
    message: str


class ContractLinter:
    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        self.issues: list[Issue] = []

    def error(self, path: Path | str, code: str, message: str) -> None:
        self.issues.append(Issue(str(path), code, message))

    def normative_files(self) -> list[Path]:
        files: list[Path] = []
        for name in ROOT_DOCS:
            candidate = self.root / name
            if candidate.exists():
                files.append(candidate)
        for pattern in NORMATIVE_GLOBS:
            for path in sorted(self.root.glob(pattern)):
                rel = path.relative_to(self.root).as_posix()
                if rel.startswith(f"{HISTORY_DIR}/"):
                    continue
                files.append(path)
        return files

    def run(self) -> None:
        self.check_banned_terms()
        self.check_branch_parity()
        self.check_validation_matrix()
        self.check_component_type_examples()
        self.check_sidecar_names()
        self.check_tracked_runtime_state()
        self.check_removed_work_dir()
        self.check_vision_regressions()
        self.check_vision_owners()

    # -- checks -----------------------------------------------------------

    def check_banned_terms(self) -> None:
        contextual = (
            (
                SETUP_VARIANT_RE,
                "CT005",
                "setup-level variant_id was removed; variants remain only on components (ADR-0014)",
            ),
            (
                MARKETPLACE_AS_TYPE_RE,
                "CT006",
                "marketplace is not a component type; it is a projection_kind (ADR-0015)",
            ),
            (
                OPERATION_SUCCEEDED_RE,
                "CT007",
                "the only operation success name is verified (contracts/operation.md)",
            ),
        )
        for path in self.normative_files():
            rel = path.relative_to(self.root).as_posix()
            seen: set[str] = set()
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if NEGATION_RE.search(line):
                    continue
                for term in BANNED_TERMS:
                    if term.code not in seen and re.search(term.pattern, line):
                        seen.add(term.code)
                        self.error(f"{rel}:{number}", term.code, term.reason)
                for pattern, code, reason in contextual:
                    if code not in seen and pattern.search(line):
                        seen.add(code)
                        self.error(f"{rel}:{number}", code, reason)

    def check_branch_parity(self) -> None:
        """Push branches in the workflow must match the documented branches."""
        overlay = self.root / _OVERLAY_WORKFLOW
        workflow = overlay if overlay.exists() else self.root / WORKFLOW
        doc = self.root / GIT_WORKFLOW_DOC
        if not workflow.exists() or not doc.exists():
            self.error(WORKFLOW, "CT010", "workflow or branch documentation is missing")
            return

        match = re.search(
            r"push:\s*\n\s*branches:\s*\[([^\]]*)\]", workflow.read_text(encoding="utf-8")
        )
        if not match:
            self.error(WORKFLOW, "CT011", "push branch list was not found")
            return
        actual = {item.strip().strip("\"'") for item in match.group(1).split(",") if item.strip()}

        text = doc.read_text(encoding="utf-8")
        # There is one line rather than an integration and release pair. Read the
        # declared line instead of assuming its name so workflow/document drift
        # fails here rather than silently disabling checks on pull-request branches.
        declared = re.search(
            r"`(\w[\w./-]*)`(?: is the repository's only line)",
            text,
            re.IGNORECASE,
        )
        if not declared:
            self.error(
                GIT_WORKFLOW_DOC, "CT012", "document does not name the repository's only line"
            )
            return
        expected = {declared.group(1)}

        if actual != expected:
            self.error(
                WORKFLOW,
                "CT013",
                f"push branches {sorted(actual)} differ from documented {sorted(expected)}",
            )

    def check_validation_matrix(self) -> None:
        """Every component type and MCP transport class has a matrix row."""
        policy = self.root / VALIDATION_POLICY
        if not policy.exists():
            self.error(VALIDATION_POLICY, "CT020", "canonical validation policy matrix is missing")
            return
        text = policy.read_text(encoding="utf-8")
        for component_type in COMPONENT_TYPES:
            if not re.search(rf"\|\s*`{re.escape(component_type)}`\s*\|", text):
                self.error(
                    VALIDATION_POLICY,
                    "CT021",
                    f"matrix row is missing for component type `{component_type}`",
                )
        for transport in MCP_TRANSPORTS:
            if not re.search(rf"\|\s*`{re.escape(transport)}`\s*\|", text):
                self.error(
                    VALIDATION_POLICY,
                    "CT022",
                    f"matrix row is missing for transport class `{transport}`",
                )

    def check_component_type_examples(self) -> None:
        """Every component type has an attribution-rule example."""
        doc = self.root / PASSPORTS_DOC
        if not doc.exists():
            self.error(PASSPORTS_DOC, "CT023", "component and setup passport contract is missing")
            return
        text = doc.read_text(encoding="utf-8")
        for component_type in COMPONENT_TYPES:
            if not re.search(rf"\|\s*`{re.escape(component_type)}`\s*\|[^|\n]+\|", text):
                self.error(
                    PASSPORTS_DOC,
                    "CT024",
                    f"attribution example is missing for type `{component_type}`",
                )

    def check_sidecar_names(self) -> None:
        """The sidecar filename is an explicit machine boundary."""
        doc = self.root / PASSPORTS_DOC
        if not doc.exists():
            return
        text = doc.read_text(encoding="utf-8")
        for name in SIDECAR_NAMES:
            if name not in text:
                self.error(
                    PASSPORTS_DOC,
                    "CT025",
                    f"canonical sidecar filename {name} is not declared",
                )

    def check_tracked_runtime_state(self) -> None:
        """Specific checkout state is untracked and declared in ignore.

        Both halves are independent: the ignore declaration is checked even
        without Git, or the check would silently disappear with the working tree.
        """
        try:
            tracked = subprocess.run(
                ["git", "ls-files", "-z", "--", ".serena"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split("\0")
        except (OSError, subprocess.CalledProcessError):
            tracked = []  # Outside a Git checkout there is no tracking to inspect.

        tracked_set = {item for item in tracked if item}
        for name in SERENA_TRANSIENT:
            if name in tracked_set:
                self.error(
                    name,
                    "CT030",
                    "specific checkout state is tracked again: SHA, branch, and machine path",
                )

        ignore = self.root / SERENA_IGNORE
        if not ignore.exists():
            self.error(SERENA_IGNORE, "CT031", "session-state ignore file is missing")
            return
        declared = {
            line.strip().lstrip("/") for line in ignore.read_text(encoding="utf-8").splitlines()
        }
        for name in SERENA_TRANSIENT:
            basename = Path(name).name
            if basename not in declared:
                self.error(SERENA_IGNORE, "CT032", f"{basename} is not declared in ignore")

    def check_removed_work_dir(self) -> None:
        """The removed work directory must not return through structure documentation."""
        doc = self.root / REPO_STRUCTURE_DOC
        if not doc.exists():
            return
        for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"^\s*\.work/\s*$", line):
                self.error(
                    f"{REPO_STRUCTURE_DOC}:{number}",
                    "CT040",
                    ".work was removed with its validator and is not part of the target structure",
                )

    def check_vision_regressions(self) -> None:
        """Closed vision decisions must not return under another name.

        These checks bypass NEGATION_RE because some forbidden formulations are
        themselves written as negations, and a general negation exemption would hide them.
        """
        rules = (
            (
                "CT051",
                CEILING_RE,
                None,
                "seven harnesses are the complete MVP set under ADR-0120, with promotion under "
                "ADR-0033; "
                "the permanent ceiling was removed",
            ),
            (
                "CT053",
                WEB_ONLY_RE,
                None,
                "the web owns the account and catalog under ADR-0018, "
                "not only installation and search",
            ),
            (
                "CT054",
                COUNTS_RE,
                None,
                "decision and requirement counts live in generated indexes, not prose",
            ),
            (
                "CT056",
                REPORT_EXCLUDED_RE,
                None,
                "complaints are in the MVP: a closed ReportCase under SPEC-016 (ADR-0031)",
            ),
            (
                "CT064",
                PLATFORM_ONLY_RE,
                None,
                "the accepted source is set per check: credential-dependent checks "
                "use author attestation (ADR-0026)",
            ),
            (
                "CT066",
                BARE_ID_RE,
                None,
                "object identity is called stable_id, not id (SPEC-015 REQ-1501)",
            ),
        )
        for path in self.normative_files():
            rel = path.relative_to(self.root).as_posix()
            seen: set[str] = set()
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for code, pattern, skip, reason in rules:
                    if code in seen or not pattern.search(line):
                        continue
                    if skip and skip.search(line):
                        continue
                    seen.add(code)
                    self.error(f"{rel}:{number}", code, reason)
                if (
                    "CT057" not in seen
                    and rel != "docs/engineering/implementation-roadmap.md"
                    and PHASE_STATE_RE.search(line)
                ):
                    seen.add("CT057")
                    self.error(
                        f"{rel}:{number}",
                        "CT057",
                        "phase state belongs to implementation-roadmap.md, "
                        "and a copy drifts on the next phase",
                    )
                if (
                    "CT052" not in seen
                    and "`not_run`" in line
                    and NOT_RUN_PUBLISH_RE.search(line)
                    and not NOT_RUN_BLOCKING_RE.search(line)
                ):
                    seen.add("CT052")
                    self.error(
                        f"{rel}:{number}",
                        "CT052",
                        "required not_run blocks publication; "
                        "published not_run was removed (ADR-0026)",
                    )
                if (
                    "CT055" not in seen
                    and DEV_PASSPORT_RE.search(line)
                    and ENV_FACT_RE.search(line)
                    and not DEV_PASSPORT_SKIP_RE.search(line)
                ):
                    seen.add("CT055")
                    self.error(
                        f"{rel}:{number}",
                        "CT055",
                        "observed environment belongs to the device passport, "
                        "not the developer passport (ADR-0025)",
                    )

    def check_vision_owners(self) -> None:
        """Canonical owners of closed decisions exist and carry their markers."""
        for relative, markers in VISION_CONTRACTS.items():
            path = self.root / relative
            if not path.exists():
                self.error(relative, "CT062", "canonical closed-decision contract is missing")
                continue
            text = path.read_text(encoding="utf-8")
            for marker in markers:
                if marker not in text:
                    self.error(
                        relative,
                        "CT063",
                        f"contract lacks required decision marker: {marker}",
                    )
        if not (self.root / REPORTS_SPEC).exists():
            self.error(REPORTS_SPEC, "CT065", "complaints and moderation specification is missing")
        policy = self.root / VALIDATION_POLICY
        if policy.exists():
            text = policy.read_text(encoding="utf-8")
            for marker in ELIGIBILITY_MARKERS:
                if marker not in text:
                    self.error(
                        VALIDATION_POLICY,
                        "CT060",
                        f"validation policy lacks readiness marker: {marker}",
                    )
            if ATTESTATION_MARKER not in text:
                self.error(
                    VALIDATION_POLICY,
                    "CT061",
                    "validation policy lacks the author-attestation section",
                )

    # -- output -----------------------------------------------------------

    def report(self, fmt: str) -> int:
        if fmt == "github":
            for issue in self.issues:
                print(f"::error file={issue.path},title={issue.code}::{issue.message}")
        else:
            for issue in sorted(self.issues, key=lambda item: (item.path, item.code)):
                print(f"ERROR {issue.path} [{issue.code}] {issue.message}")
        print()
        print(f"Contract errors: {len(self.issues)}")
        return 1 if self.issues else 0


def main() -> int:
    fmt = "github" if "--format=github" in sys.argv else "text"
    linter = ContractLinter()
    linter.run()
    return linter.report(fmt)


if __name__ == "__main__":
    raise SystemExit(main())
