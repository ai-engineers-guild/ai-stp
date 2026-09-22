"""Five-class inventory of every declared CLI leaf (SPEC-080 REQ-8002).

The test is the oracle: unlabeled leftover fails. Everyday journeys from the
agent-UX plan must not live only in `expert`. `task_covered` is only an effect
already reachable through a shipped intent; `component publish` stays pending
until that leaf itself is drained. Incomplete `component publish` still starts
the `publish` intent. Install plan/approve/apply/status/recover/resume and
`registry acquire` are `task_covered` because `install` is drained.
`setup compose apply` is `task_covered` because `change` and `author` record
setups through the same compose persist path. Author does not install.
`component adopt` and `component discover` stay pending: author registers a
directory through compose, not through native-path adoption. Incomplete
invocations of those leaves still start the `author` intent.
`setup preserve plan`, `setup restore plan`,
and `setup preserved list` are `task_covered` because `switch` captures drift
and restores the last user working config. `auth login`, `auth complete`, and
`auth logout` are `task_covered` because `account` drains the device-code flow
in-process; login never uploads. `publication plan` and `publication confirm`
are `task_covered` because `publish` drains the no-binding publication plan.
`sync push` and `sync pull` are `task_covered` because explicit account sync
calls those leaves.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, Literal

CapabilityClass = Literal["inspect", "task_covered", "task_pending", "expert", "obsolete"]


def _paths(*rows: str) -> frozenset[tuple[str, ...]]:
    return frozenset(tuple(row.split()) for row in rows)


INSPECT: Final[frozenset[tuple[str, ...]]] = _paths(
    "auth status",
    "capabilities",
    "config show",
    "config validate",
    "contract inventory",
    "corporate assignment distribution",
    "corporate assignment effective",
    "corporate assignment plan",
    "corporate assignment verify",
    "doctor",
    "environment inspect",
    "help",
    "schema list",
    "schema show",
    "task intents",
    "task list",
    "telemetry show",
    "toolchain harness-capabilities",
    "toolchain harnesses",
    "toolchain profile",
    "update check",
    "update status",
    "version",
)

TASK_COVERED: Final[frozenset[tuple[str, ...]]] = _paths(
    "task start",
    "task answer",
    "task continue",
    "task status",
    "task cancel",
    "install apply",
    "install approve",
    "install cancel",
    "install plan",
    "install recover",
    "install resume",
    "install status",
    "registry acquire",
    "setup compose apply",
    "setup preserve plan",
    "setup preserved list",
    "setup restore plan",
    "auth complete",
    "auth login",
    "auth logout",
    "publication confirm",
    "publication plan",
    "sync pull",
    "sync push",
)

TASK_PENDING: Final[frozenset[tuple[str, ...]]] = _paths(
    "component adaptation add",
    "component adopt",
    "component discover",
    "component find",
    "component forget",
    "component fork",
    "component inventory",
    "component materialize apply",
    "component materialize plan",
    "component passport quality",
    "component passport show",
    "component passport suggest",
    "component passport update",
    "component passport validate",
    "component portability apply",
    "component portability plan",
    "component program install",
    "component program remove",
    "component program status",
    "component publish",
    "component scaffold apply",
    "component scaffold plan",
    "component version list",
    "component version release",
    "config init",
    "config set",
    "config unset",
    "corporate assignment distribute",
    "device init",
    "device show",
    "environment plan",
    "install transaction apply",
    "install transaction approve",
    "install transaction cancel",
    "install transaction plan",
    "install transaction recover",
    "install transaction status",
    "passport developer init",
    "passport developer show",
    "passport developer update",
    "passport device refresh",
    "passport device show",
    "project detect",
    "project discover",
    "project index",
    "project link create",
    "project link plan create",
    "project link plan show",
    "project link show",
    "project passport",
    "project revision pull",
    "project revision push",
    "project symbols",
    "project sync apply",
    "project sync plan",
    "project technologies",
    "project technology confirm",
    "project technology mappings fetch",
    "project technology mappings list",
    "project technology override",
    "project technology publish",
    "project technology reject",
    "project technology retire",
    "project unlink",
    "project unlink-plan create",
    "project unlink-plan show",
    "provider fetch",
    "provider forget",
    "provider reinstall apply",
    "provider reinstall plan",
    "provider update apply",
    "provider update plan",
    "publication status",
    "publication visibility confirm",
    "publication visibility plan",
    "publication visibility status",
    "registry fetch",
    "registry port discover",
    "registry port import",
    "registry port inspect",
    "registry port plan",
    "registry search",
    "registry show",
    "registry version",
    "select bundle",
    "select cancel",
    "select confirm",
    "select eligibility",
    "select graph",
    "select propose",
    "setup compose plan",
    "setup export",
    "setup import inspect",
    "setup import plan",
    "setup import register",
    "setup preserve recover",
    "setup preserved show",
    "setup publish confirm",
    "setup publish plan",
    "setup recast apply",
    "setup recast plan",
    "setup scaffold apply",
    "setup scaffold plan",
    "setup update apply",
    "setup update plan",
    "skill install",
    "skill remove",
    "skill status",
    "sync merge",
    "sync preview",
    "target backups",
    "target diff",
    "target rollback",
    "target status",
)

#: Everyday journeys named in the agent-UX plan §2.4. None may be `expert`.
EVERYDAY_JOURNEYS: Final[frozenset[tuple[str, ...]]] = _paths(
    "install plan",
    "install approve",
    "install apply",
    "install cancel",
    "install status",
    "install recover",
    "install resume",
    "install transaction plan",
    "install transaction approve",
    "install transaction apply",
    "install transaction cancel",
    "install transaction status",
    "install transaction recover",
    "setup compose plan",
    "setup compose apply",
    "setup preserve plan",
    "setup preserve recover",
    "setup preserved list",
    "setup preserved show",
    "setup restore plan",
    "setup import inspect",
    "setup import plan",
    "setup import register",
    "registry search",
    "registry acquire",
    "registry port discover",
    "registry port inspect",
    "registry port plan",
    "registry port import",
    "component adopt",
    "component discover",
    "component publish",
    "publication plan",
    "publication confirm",
    "publication status",
    "setup publish plan",
    "setup publish confirm",
    "publication visibility plan",
    "publication visibility confirm",
    "publication visibility status",
    "auth login",
    "config init",
    "select propose",
    "select confirm",
    "select bundle",
)

#: Expert leaves a weak model must not be told to type from an everyday
#: failure envelope. Backup/rollback `--action` stays expert recovery at the
#: parser, not here.
EVERYDAY_FORBIDDEN_WAYBACK: Final[tuple[str, ...]] = (
    "install plan",
    "install approve",
    "install apply",
    "install transaction plan",
    "install transaction approve",
    "install transaction apply",
    "select propose",
    "select confirm",
    "select eligibility",
    "select bundle",
    "select graph",
    "select blast-radius",
    "select impact",
    "auth login",
    "auth complete",
    "auth logout",
    "auth status",
    "sync push",
    "sync pull",
    "publication plan",
    "publication confirm",
    "publication visibility plan",
    "publication visibility confirm",
    "setup publish plan",
    "setup publish confirm",
    "setup compose plan",
    "setup compose apply",
    "setup update plan",
    "setup update apply",
    "setup preserve plan",
    "setup preserve recover",
    "setup preserved list",
    "setup preserved show",
    "setup export",
    "setup restore plan",
    "setup scaffold plan",
    "setup scaffold apply",
    "setup recast plan",
    "setup recast apply",
    "setup import inspect",
    "setup import plan",
    "setup import register",
    "install transaction cancel",
    "install transaction recover",
    "install transaction status",
    "install cancel",
    "install status",
    "environment plan",
    "environment inspect",
    "publication status",
    "eval plan",
    "eval profile",
    "eval run",
    "eval show",
    "eval status",
    "eval component plan",
    "eval component run",
    "eval component show",
    "eval component status",
    "select cancel",
    "select reports",
    "select session",
    "sync merge",
    "sync preview",
    "publication visibility status",
    "component discover",
    "component adopt",
    "component scaffold",
    "component publish",
    "component materialize plan",
    "component materialize apply",
    "component portability plan",
    "component portability apply",
    "help --path",
    "help --agent",
    "help",
    "config init",
    "registry acquire",
    "registry search",
    "registry port discover",
    "registry port inspect",
    "registry port plan",
    "registry port import",
    "registry show",
    "registry fetch",
    "registry version",
    "project passport",
    "project discover",
    "project index",
    "project link plan",
    "project link create",
    "project link show",
    "project revision push",
    "project revision pull",
    "project sync plan",
    "project sync apply",
    "project detect",
    "project technologies",
    "project technology confirm",
    "project technology reject",
    "project technology override",
    "project technology retire",
    "project technology mappings list",
    "project technology mappings fetch",
    "project technology publish",
    "provider network",
    "provider fetch",
    "provider forget",
    "provider check",
    "provider conformance",
    "provider trust",
    "provider reinstall plan",
    "provider reinstall apply",
    "project symbols",
    "project unlink",
    "component adaptation",
    "component program",
    "component template",
    "component source",
    "component passport",
    "component forget",
    "component version",
    "component fork",
    "component find",
    "component inventory",
    "component skill",
    "config set",
    "config unset",
    "config validate",
    "config show",
    "target status",
    "target diff",
    "target backups",
    "target rollback",
    "report confirm",
    "report list",
    "report preview",
    "report status",
    "consent allow",
    "consent list",
    "consent revoke",
    "device reset",
    "device init",
    "device show",
    "passport developer",
    "passport device",
    "grant list",
    "grant invite",
    "grant direct",
    "grant accept",
    "grant invitation",
    "grant revoke",
    "github status",
    "github source",
    "owner object",
    "owner version",
    "contract inventory",
    "harness install",
    "harness update",
    "harness remove",
    "harness resume",
    "harness status",
    "toolchain install",
    "toolchain remove",
    "toolchain harness-capabilities",
    "toolchain harnesses",
    "toolchain profile",
    "skill install",
    "skill remove",
    "skill status",
    "telemetry show",
    "telemetry consent",
    "link web",
    "attestation sign",
    "task status",
    "task info",
    "task get",
    "update plan",
    "update apply",
    "update check",
    "update status",
    "update recover",
    "update rollback",
)


def is_forbidden_wayback(action: str) -> bool:
    """Whether this next_action teaches a leaf qualify forbids."""
    held = action.removeprefix("ai-stp ").lstrip()
    return any(token in held for token in EVERYDAY_FORBIDDEN_WAYBACK)


def teaches_forbidden_wayback(actions: Sequence[str]) -> bool:
    return any(is_forbidden_wayback(item) for item in actions)


EXPERT: Final[dict[tuple[str, ...], str]] = {
    ("attestation", "sign"): "Signs an attestation; exceptional control.",
    ("component", "program", "invoke"): "Invokes a cli-kind executable; blast-radius.",
    ("component", "skill", "validate"): "Evaluates a skill against its contract.",
    ("component", "source", "evidence", "history"): "Source-evidence diagnosis.",
    ("component", "source", "evidence", "refresh"): "Source-evidence diagnosis.",
    ("component", "source", "evidence", "show"): "Source-evidence diagnosis.",
    ("component", "source", "parse"): "Source-coordinate diagnosis.",
    ("component", "source", "resolve"): "Source-coordinate diagnosis.",
    ("component", "source", "search"): "Source-coordinate diagnosis.",
    ("component", "template", "render"): "Renders a template; authoring diagnosis.",
    ("consent", "allow"): "Legal consent grant; not a product journey.",
    ("consent", "list"): "Legal consent diagnosis.",
    ("consent", "revoke"): "Legal consent revocation.",
    ("device", "reset"): "Destructive device-identity reset.",
    ("eval", "component", "plan"): "Evaluation plan; not a product install.",
    ("eval", "component", "run"): "Runs an evaluation; blast-radius.",
    ("eval", "component", "show"): "Evaluation diagnosis.",
    ("eval", "component", "status"): "Evaluation diagnosis.",
    ("eval", "plan"): "Evaluation plan; not a product install.",
    ("eval", "profile"): "Evaluation profile; exceptional control.",
    ("eval", "run"): "Runs an evaluation; blast-radius.",
    ("eval", "show"): "Evaluation diagnosis.",
    ("eval", "status"): "Evaluation diagnosis.",
    ("github", "source", "prepare"): "GitHub source binding; exceptional control.",
    ("github", "status"): "GitHub binding diagnosis.",
    ("grant", "accept"): "Access-grant mutation.",
    ("grant", "direct"): "Access-grant mutation.",
    ("grant", "invitation", "revoke"): "Access-grant mutation.",
    ("grant", "invite"): "Access-grant mutation.",
    ("grant", "list"): "Access-grant diagnosis.",
    ("grant", "revoke"): "Access-grant mutation.",
    ("harness", "install"): "Installs the harness program, not an ai-stp setup.",
    ("harness", "remove"): "Removes the harness program; blast-radius.",
    ("harness", "resume"): "Resumes harness-program install; exceptional.",
    ("harness", "status"): "Harness-program diagnosis.",
    ("harness", "update"): "Updates the harness program; blast-radius.",
    ("link", "web"): "Opens a browser; not headless agent transport.",
    ("owner", "object", "show"): "Catalog-owner diagnosis.",
    ("owner", "objects"): "Catalog-owner diagnosis.",
    ("owner", "version", "show"): "Catalog-owner diagnosis.",
    ("provider", "check"): "Diagnoses a provider executable.",
    ("provider", "conformance"): "Provider-protocol diagnosis.",
    ("provider", "network"): "Provider-network diagnosis.",
    ("provider", "trust"): "Records a provider trust grant.",
    ("report", "confirm"): "Contribution-report confirmation; exceptional.",
    ("report", "list"): "Contribution-report diagnosis.",
    ("report", "preview"): "Contribution-report diagnosis.",
    ("report", "status"): "Contribution-report diagnosis.",
    ("select", "blast-radius"): "Blast-radius diagnosis.",
    ("select", "eligibility-matrix"): "Full eligibility-matrix dump; diagnosis.",
    ("select", "impact"): "Impact diagnosis.",
    ("select", "reports"): "Selection-report dump; diagnosis.",
    ("select", "session"): "Raw selection-session dump; diagnosis.",
    ("telemetry", "consent"): "Privacy-consent grant.",
    ("toolchain", "install"): "Installs toolchain software; blast-radius.",
    ("toolchain", "remove"): "Removes toolchain software; blast-radius.",
    ("update", "apply"): "Applies a CLI self-update; exceptional.",
    ("update", "plan"): "Plans a CLI self-update; exceptional.",
    ("update", "recover"): "Recovers a CLI self-update; exceptional.",
    ("update", "rollback"): "Rolls back a CLI self-update; exceptional.",
}

OBSOLETE: Final[dict[tuple[str, ...], str]] = {}

#: Longest prefix first. Incomplete groups and scoped `help --path` of these
#: families start the draining intent instead of listing expert leaves.
DRAINED_GROUPS: Final[tuple[tuple[tuple[str, ...], str], ...]] = (
    (("setup", "preserved"), "switch"),
    (("setup", "preserve"), "switch"),
    (("setup", "restore"), "switch"),
    (("setup", "publish"), "publish"),
    (("setup", "compose"), "change"),
    (("install",), "install"),
    (("publication",), "publish"),
    (("auth",), "account"),
    (("sync",), "account"),
)

#: Scoped machine-help families that are not 1:1 with a shipped intent.
MIXED_HELP_PREFIXES: Final[frozenset[str]] = frozenset(
    {"component", "select", "setup", "registry", "config"}
)


def intent_for_command_prefix(words: Sequence[str]) -> str | None:
    held = tuple(words)
    if not held:
        return None
    for prefix, intent in DRAINED_GROUPS:
        if held[: len(prefix)] == prefix:
            return intent
    return None


def everyday_intent(path: tuple[str, ...]) -> str | None:
    """Draining intent for a `task_covered` or everyday-journey leaf."""
    if not path or path[0] == "task":
        return None
    if path not in TASK_COVERED and path not in EVERYDAY_JOURNEYS:
        return None
    if path[:2] in {("component", "publish"), ("setup", "publish")}:
        return "publish"
    if path[:2] in {("component", "adopt"), ("component", "discover")}:
        return "author"
    if path == ("config", "init"):
        return "initialize"
    if path[0] == "select":
        return "install"
    if path[:2] == ("setup", "import"):
        return "author"
    if path[0] == "registry":
        return "install"
    return intent_for_command_prefix(path)


def classify(path: tuple[str, ...]) -> CapabilityClass:
    if path in INSPECT:
        return "inspect"
    if path in TASK_COVERED:
        return "task_covered"
    if path in TASK_PENDING:
        return "task_pending"
    if path in EXPERT:
        return "expert"
    if path in OBSOLETE:
        return "obsolete"
    raise KeyError(path)


def everyday_success_start_intent(
    path: tuple[str, ...],
    mutability: str,
    *,
    has_continuations: bool,
) -> str | None:
    """Pending success and covered read/plan success still point at `task start`.

    `auth login` is apply but only records a pending device-code; the account
    intent finishes it from the store. `registry acquire` is apply but only
    materializes catalog bytes; the install intent still drains plan/apply.
    Terminal apply (`install apply`, `auth complete`, `setup compose apply`)
    is not rewritten: those would loop. `has_continuations` is after
    qualify-forbidden way-back has already been stripped.
    """
    if has_continuations:
        return None
    intent = everyday_intent(path)
    if intent is None:
        return None
    kind = classify(path)
    if kind == "task_pending":
        return intent
    if kind == "task_covered" and mutability in {"read", "plan"}:
        return intent
    if path in {("auth", "login"), ("registry", "acquire")}:
        return intent
    return None


def classified_paths() -> frozenset[tuple[str, ...]]:
    return INSPECT | TASK_COVERED | TASK_PENDING | frozenset(EXPERT) | frozenset(OBSOLETE)


def expert_reason(path: tuple[str, ...]) -> str:
    return EXPERT[path]
