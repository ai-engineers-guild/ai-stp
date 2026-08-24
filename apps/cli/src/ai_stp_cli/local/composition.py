"""Conflicts, the composition report and the conversion report (`#166`).

`REQ-609` asks a bundle to carry both reports and `REQ-606` names the conflicts
a builder must detect. This module produces all three from the resolved closure
and nothing else — no clock, no network, no model, and no writes.

**Nothing here merges anything.** `REQ-626` forbids automatic semantic merging,
equivalent selection and composition optimisation, so a contradiction blocks and
a person resolves it. Every function below either finds a conflict or does not;
none of them repairs one, and that is the whole design rather than a limitation
of it.

**A loss is named or it is not reported.** A conversion report saying "some
surfaces were lost" explains nothing, and `REQ-609` asks for a loss-aware
report. So every entry names the surface it maps to and every loss says what was
dropped.

**`unsupported` is not automatically fatal.** A harness with no native surface
for a kind cannot take that component, and whether that blocks depends on
whether the component was required. Conflating the two would refuse compositions
that are fine and would hide the ones that are not.
"""

from dataclasses import dataclass, field
from typing import Final

from ai_stp_cli.local.components import Rule

#: Every conflict this module can report, closed by `composition-reports.md`.
#: The four closure conflicts — cycle, missing reference, digest mismatch and
#: incompatible versions — belong to `setup-graph.md`: a composition is not
#: assembled at all until the closure resolves.
CONFLICTS: Final[frozenset[str]] = frozenset(
    {
        "managed_path_owned_twice",
        "native_id_collision",
        "instruction_precedence_conflict",
        "hook_order_conflict",
        "native_surface_lost",
        "path_escapes_bundle",
        "undeclared_environment",
        "permission_escalation",
        "redistribution_forbidden",
        "entitlement_missing",
        "unverified_without_consent",
        "unsupported_platform",
    }
)

#: The deterministic operations `REQ-625` allows an MVP builder. Closed: an
#: operation outside this list does not exist, and a report may only name what
#: it actually applied.
OPERATIONS: Final[tuple[str, ...]] = (
    "canonical_ordering",
    "exact_reference_deduplication",
    "dependency_closure",
    "disjoint_managed_path_union",
    "deterministic_report_generation",
)

#: What a component becomes on the target harness.
STATE_COMPLETE: Final[str] = "complete"
STATE_PARTIAL: Final[str] = "partial"
STATE_UNSUPPORTED: Final[str] = "unsupported"

#: The lane that never reaches an automatic composition without consent.
LANE_EXPERIMENTAL: Final[str] = "experimental"

# Provider projection is relative to the explicit target handed to the public
# manager. It is distinct from discovery: discovery may inspect project-local
# `.pi/` or `.grok/` trees, while a provider writes the isolated harness home.
PROVIDER_RULES: Final[tuple[Rule, ...]] = (
    Rule("instruction", "CLAUDE.md", "file", "claude-code"),
    Rule("skill", "skills", "directory", "claude-code"),
    Rule("mcp", ".mcp.json", "file", "claude-code"),
    Rule("command", "commands", "directory", "claude-code"),
    Rule("agent", "agents", "directory", "claude-code"),
    Rule("instruction", "AGENTS.md", "file", "codex"),
    Rule("skill", ".agents/skills", "directory", "codex"),
    Rule("setting", "config.toml", "file", "codex"),
    # No `agent/` prefix: these are relative to the target, and Pi's target
    # already is `~/.pi/agent`. The segment belongs to the home, not inside it,
    # and prefixing it landed every Pi projection in `~/.pi/agent/agent/`.
    Rule("instruction", "AGENTS.md", "file", "pi"),
    Rule("skill", "skills", "directory", "pi"),
    Rule("plugin", "extensions", "directory", "pi", projection_kind="extension"),
    Rule("setting", "settings.json", "file", "pi"),
    Rule("instruction", "AGENTS.md", "file", "opencode"),
    Rule("skill", "skills", "directory", "opencode"),
    Rule("command", "commands", "directory", "opencode"),
    Rule("agent", "agents", "directory", "opencode"),
    Rule("plugin", "plugins", "directory", "opencode", projection_kind="plugin"),
    Rule("setting", "opencode.json", "file", "opencode"),
    # Cursor installs a plugin rather than sibling directories: its manifest
    # declares commands, hooks, MCP entries, agents, skills and rules as paths
    # inside the plugin, so the plugin is what a provider writes.
    Rule("instruction", "AGENTS.md", "file", "cursor"),
    Rule("setting", "cli-config.json", "file", "cursor"),
    Rule("plugin", "plugins", "directory", "cursor", projection_kind="plugin"),
    # Antigravity's home belongs to Gemini: `antigravity-cli/` is its own and
    # `config/` is shared, so both prefixes are part of the relative path rather
    # than something a target adds.
    Rule("setting", "antigravity-cli/settings.json", "file", "antigravity"),
    Rule("plugin", "antigravity-cli/plugins", "directory", "antigravity", projection_kind="plugin"),
    Rule("skill", "config/skills", "directory", "antigravity"),
    Rule("agent", "config/agents", "directory", "antigravity"),
    Rule("hook", "config/hooks.json", "file", "antigravity"),
    Rule("mcp", "config/mcp_config.json", "file", "antigravity"),
    Rule("instruction", "AGENTS.md", "file", "grok-build"),
    Rule("skill", "skills", "directory", "grok-build"),
    Rule("mcp", ".mcp.json", "file", "grok-build"),
    Rule("hook", "hooks", "directory", "grok-build"),
    Rule("command", "commands", "directory", "grok-build"),
    Rule("agent", "agents", "directory", "grok-build"),
    Rule("plugin", "plugins", "directory", "grok-build", projection_kind="plugin"),
    Rule("setting", "config.toml", "file", "grok-build"),
)


@dataclass(frozen=True)
class Surface:
    """What one component contributes to the composed target.

    Read from the passport rather than inferred. Every field here is something
    a conflict is decided from, and a value nobody declared is absent rather
    than defaulted to something plausible — a default would make an undeclared
    permission look like a granted one.
    """

    stable_id: str
    version: str
    component_type: str
    harness_id: str

    #: Exact content-addressed passport revision selected by the resolved graph.
    #: Native projection must never consult the mutable entity head after
    #: confirmation: a later draft revision is not part of this setup version.
    revision_id: str = ""
    source_name: str = ""
    content_format: str = ""

    managed_paths: tuple[str, ...] = ()
    native_ids: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    required_env: tuple[str, ...] = ()
    external_endpoints: tuple[str, ...] = ()
    redistribution: bool = True

    #: Declared precedence for an instruction, and declared order for a hook.
    #: `None` means the component states no preference, which never conflicts.
    precedence: int | None = None
    hook_event: str = ""
    hook_order: int | None = None

    #: Whether this component must be present for the composition to make sense.
    #: An optional component with no native surface is a loss; a required one is
    #: a blocked bundle.
    required: bool = True

    lane: str = "local_owner_or_pinned"
    consented: bool = False


@dataclass(frozen=True)
class Target:
    """What the composition is being built for."""

    harness_id: str
    os: str
    arch: str

    #: Permissions and entitlements the user allows. Compared exactly; there is
    #: no declared vocabulary for either yet, and inventing one here would
    #: create a second undeclared dictionary.
    allowed_permissions: frozenset[str] = frozenset()
    granted_entitlements: frozenset[str] = frozenset()

    #: Environment variable names present, and endpoints the composition
    #: declares. Names only — `REQ-1108` keeps values out of every path.
    declared_env: frozenset[str] = frozenset()
    declared_endpoints: frozenset[str] = frozenset()

    supported_platforms: frozenset[str] = frozenset()
    for_redistribution: bool = False


@dataclass(frozen=True)
class Conflict:
    """One reason this composition cannot be built."""

    code: str
    summary: str
    details: dict[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True)
class Chosen:
    """One component that is in the composition, and why."""

    stable_id: str
    version: str
    lane: str
    reason: str


@dataclass(frozen=True)
class Rejected:
    """One candidate that is not, and why."""

    stable_id: str
    version: str
    reason: str


@dataclass(frozen=True)
class CompositionReport:
    """What was chosen, what was not, what was applied and what conflicts."""

    chosen: tuple[Chosen, ...]
    rejected: tuple[Rejected, ...]
    operations: tuple[str, ...]
    conflicts: tuple[Conflict, ...]

    @property
    def blocked(self) -> bool:
        return bool(self.conflicts)


@dataclass(frozen=True)
class ConversionEntry:
    """What one component becomes on the target, and what is lost doing it."""

    stable_id: str
    component_type: str
    native_surface: str
    projection_kind: str
    state: str
    losses: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConversionReport:
    """Native adaptation, per component, with every loss named (`REQ-609`)."""

    entries: tuple[ConversionEntry, ...]

    @property
    def complete(self) -> bool:
        return all(item.state == STATE_COMPLETE for item in self.entries)

    @property
    def losses(self) -> tuple[str, ...]:
        return tuple(loss for item in self.entries for loss in item.losses)


def rule_for(component_type: str, harness_id: str) -> Rule | None:
    """Return the target-relative provider projection for one component kind."""
    for rule in PROVIDER_RULES:
        if rule.component_type == component_type and rule.harness_id == harness_id:
            return rule
    return None


def native_surface(component_type: str, harness_id: str) -> str:
    """Where a component of this kind lives, or empty when nowhere."""
    rule = rule_for(component_type, harness_id)
    return "" if rule is None else rule.relative


def compose(surfaces: tuple[Surface, ...], target: Target) -> CompositionReport:
    """Detect every conflict in one composition. Repairs nothing (`REQ-626`).

    Every class is checked and every conflict collected: a composition with
    three problems should be fixable in one pass. The result is sorted, so one
    canonical input produces one report.
    """
    conflicts: list[Conflict] = []
    conflicts.extend(_paths(surfaces, target))
    conflicts.extend(_identities(surfaces))
    conflicts.extend(_precedence(surfaces))
    conflicts.extend(_hooks(surfaces))
    conflicts.extend(_surfaces(surfaces, target))
    conflicts.extend(_environment(surfaces, target))
    conflicts.extend(_permissions(surfaces, target))
    conflicts.extend(_licences(surfaces, target))
    conflicts.extend(_trust(surfaces))
    conflicts.extend(_platform(target))
    conflicts.sort(key=lambda item: (item.code, item.details.get("stable_id", "")))

    ordered = sorted(surfaces, key=lambda item: (item.stable_id, item.version))
    return CompositionReport(
        chosen=tuple(
            Chosen(
                stable_id=item.stable_id,
                version=item.version,
                lane=item.lane,
                reason="named by the confirmed composition",
            )
            for item in ordered
        ),
        rejected=(),
        operations=_applied(surfaces),
        conflicts=tuple(conflicts),
    )


def convert(surfaces: tuple[Surface, ...], target: Target) -> ConversionReport:
    """What each component becomes on the target harness, and what is lost.

    A loss here is a loss *of conversion* and nothing else. An undeclared
    environment variable is already a conflict above, and repeating it as a
    conversion loss would make one problem look like two.
    """
    ordered = sorted(surfaces, key=lambda item: item.stable_id)

    # How many components of each kind land on one surface. A file-shaped
    # surface holding two of them cannot keep them apart, and that is the one
    # partial conversion this build can actually decide — everything else
    # needs harness knowledge the providers of phase 6 bring.
    crowded: dict[str, int] = {}
    for item in ordered:
        crowded[item.component_type] = crowded.get(item.component_type, 0) + 1

    entries: list[ConversionEntry] = []
    for item in ordered:
        rule = rule_for(item.component_type, target.harness_id)
        if rule is None:
            # A passport with no declared kind lands here too, and says so. It
            # is malformed, and the report is where a person finds that out.
            entries.append(
                ConversionEntry(
                    stable_id=item.stable_id,
                    component_type=item.component_type,
                    native_surface="",
                    projection_kind="native_files",
                    state=STATE_UNSUPPORTED,
                    losses=(
                        (f"{target.harness_id} has no native surface for {item.component_type}")
                        if item.component_type
                        else "this passport declares no component type",
                    ),
                )
            )
            continue

        losses: tuple[str, ...] = ()
        sharing = crowded[item.component_type]
        if rule.shape == "file" and sharing > 1:
            losses = (
                f"{sharing} components of this kind share the single file "
                f"{rule.relative}; their separate identity is not preserved",
            )
        entries.append(
            ConversionEntry(
                stable_id=item.stable_id,
                component_type=item.component_type,
                native_surface=rule.relative,
                projection_kind=rule.projection_kind,
                state=STATE_PARTIAL if losses else STATE_COMPLETE,
                losses=losses,
            )
        )
    return ConversionReport(entries=tuple(entries))


def _projected_root(item: Surface, target: Target) -> str:
    rule = rule_for(item.component_type, target.harness_id)
    if rule is None:
        return ""
    if rule.shape == "directory":
        return f"{rule.relative}/{item.source_name}" if item.source_name else ""
    return rule.relative


def _paths(surfaces: tuple[Surface, ...], target: Target) -> list[Conflict]:
    """Two owners of one managed path, and paths that leave the bundle.

    `harness-bundle.md` rejects absolute and parent paths outright, so they are
    caught here rather than at packaging: a conflict named during composition is
    one a person can act on, and the same path rejected inside a bundle writer
    is a failure with no context.
    """
    conflicts: list[Conflict] = []
    owners: dict[str, str] = {}
    for item in sorted(surfaces, key=lambda item: item.stable_id):
        projected = _projected_root(item, target)
        paths = set(item.managed_paths)
        if projected:
            paths.add(projected)
        for path in sorted(paths):
            if _escapes(path):
                conflicts.append(
                    Conflict(
                        "path_escapes_bundle",
                        "a managed path is absolute, parent-relative or empty",
                        {"stable_id": item.stable_id, "path": path},
                    )
                )
                continue
            held = owners.get(path)
            if held is not None and held != item.stable_id:
                conflicts.append(
                    Conflict(
                        "managed_path_owned_twice",
                        "two components claim the same managed path",
                        {"stable_id": item.stable_id, "path": path, "also": held},
                    )
                )
                continue
            owners[path] = item.stable_id
    return conflicts


def _identities(surfaces: tuple[Surface, ...]) -> list[Conflict]:
    """One native identifier belongs to one component."""
    conflicts: list[Conflict] = []
    owners: dict[str, str] = {}
    for item in sorted(surfaces, key=lambda item: item.stable_id):
        for native in sorted(set(item.native_ids)):
            held = owners.get(native)
            if held is not None and held != item.stable_id:
                conflicts.append(
                    Conflict(
                        "native_id_collision",
                        "two components declare the same native identifier",
                        {"stable_id": item.stable_id, "native_id": native, "also": held},
                    )
                )
                continue
            owners[native] = item.stable_id
    return conflicts


def _precedence(surfaces: tuple[Surface, ...]) -> list[Conflict]:
    """Two instructions cannot occupy one precedence level.

    A level decides which text wins, so two claimants make the outcome depend on
    the order they happened to be read in — which is exactly the kind of
    unresolved tie the whole composition is arranged to avoid.
    """
    conflicts: list[Conflict] = []
    held: dict[int, str] = {}
    for item in sorted(surfaces, key=lambda item: item.stable_id):
        if item.component_type != "instruction" or item.precedence is None:
            continue
        owner = held.get(item.precedence)
        if owner is not None:
            conflicts.append(
                Conflict(
                    "instruction_precedence_conflict",
                    "two instructions claim the same precedence",
                    {
                        "stable_id": item.stable_id,
                        "precedence": str(item.precedence),
                        "also": owner,
                    },
                )
            )
            continue
        held[item.precedence] = item.stable_id
    return conflicts


def _hooks(surfaces: tuple[Surface, ...]) -> list[Conflict]:
    """Two hooks cannot claim one position on one event."""
    conflicts: list[Conflict] = []
    held: dict[tuple[str, int], str] = {}
    for item in sorted(surfaces, key=lambda item: item.stable_id):
        if item.component_type != "hook" or item.hook_order is None:
            continue
        key = (item.hook_event, item.hook_order)
        owner = held.get(key)
        if owner is not None:
            conflicts.append(
                Conflict(
                    "hook_order_conflict",
                    "two hooks claim the same order on one event",
                    {
                        "stable_id": item.stable_id,
                        "event": item.hook_event,
                        "order": str(item.hook_order),
                        "also": owner,
                    },
                )
            )
            continue
        held[key] = item.stable_id
    return conflicts


def _surfaces(surfaces: tuple[Surface, ...], target: Target) -> list[Conflict]:
    """A required component the target harness cannot hold blocks the bundle."""
    return [
        Conflict(
            "native_surface_lost",
            "the target harness has no native surface for a required component",
            {
                "stable_id": item.stable_id,
                "component_type": item.component_type,
                "harness_id": target.harness_id,
            },
        )
        for item in sorted(surfaces, key=lambda item: item.stable_id)
        if item.required and not native_surface(item.component_type, target.harness_id)
    ]


def _environment(surfaces: tuple[Surface, ...], target: Target) -> list[Conflict]:
    """Nothing the composition needs may be undeclared.

    This is about the *composition* declaring what it needs, not about a value
    being present: a missing value is an advisory at install time by REQ-111,
    and an undeclared requirement is a composition that lies about itself.
    """
    conflicts: list[Conflict] = []
    for item in sorted(surfaces, key=lambda item: item.stable_id):
        for name in sorted(set(item.required_env) - target.declared_env):
            conflicts.append(
                Conflict(
                    "undeclared_environment",
                    "a component needs an environment variable the composition does not declare",
                    {"stable_id": item.stable_id, "name": name},
                )
            )
        for endpoint in sorted(set(item.external_endpoints) - target.declared_endpoints):
            conflicts.append(
                Conflict(
                    "undeclared_environment",
                    "a component reaches an endpoint the composition does not declare",
                    {"stable_id": item.stable_id, "endpoint": endpoint},
                )
            )
    return conflicts


def _permissions(surfaces: tuple[Surface, ...], target: Target) -> list[Conflict]:
    """A composition may not need more than the user allowed.

    Two codes, not one. `permission_escalation` is a component asking for
    something outside what the target permits; `entitlement_missing` is a right
    that was never granted. They are fixed differently — one by narrowing the
    composition, the other by granting — and one code would send the user to the
    wrong place half the time.
    """
    conflicts: list[Conflict] = []
    for item in sorted(surfaces, key=lambda item: item.stable_id):
        for wanted in sorted(set(item.permissions)):
            if wanted in target.allowed_permissions:
                continue
            code = (
                "entitlement_missing"
                if wanted in target.granted_entitlements
                else "permission_escalation"
            )
            conflicts.append(
                Conflict(
                    code,
                    "a component requires more than this target allows",
                    {"stable_id": item.stable_id, "permission": wanted},
                )
            )
    return conflicts


def _licences(surfaces: tuple[Surface, ...], target: Target) -> list[Conflict]:
    if not target.for_redistribution:
        return []
    return [
        Conflict(
            "redistribution_forbidden",
            "this composition is for distribution and a component forbids it",
            {"stable_id": item.stable_id},
        )
        for item in sorted(surfaces, key=lambda item: item.stable_id)
        if not item.redistribution
    ]


def _trust(surfaces: tuple[Surface, ...]) -> list[Conflict]:
    return [
        Conflict(
            "unverified_without_consent",
            "an unverified component is in this composition without consent",
            {"stable_id": item.stable_id},
        )
        for item in sorted(surfaces, key=lambda item: item.stable_id)
        if item.lane == LANE_EXPERIMENTAL and not item.consented
    ]


def _platform(target: Target) -> list[Conflict]:
    platform = f"{target.os}/{target.arch}"
    if not target.supported_platforms or platform in target.supported_platforms:
        return []
    return [
        Conflict(
            "unsupported_platform",
            "this platform and harness pair is not supported",
            {"platform": platform, "harness_id": target.harness_id},
        )
    ]


def _applied(surfaces: tuple[Surface, ...]) -> tuple[str, ...]:
    """Which of the allowed operations this composition actually used.

    Named rather than assumed. `REQ-625` bounds the builder to a closed set, and
    a report listing the whole set every time would prove nothing about what
    happened.
    """
    applied = ["canonical_ordering", "dependency_closure", "deterministic_report_generation"]
    identifiers = [item.stable_id for item in surfaces]
    if len(identifiers) != len(set(identifiers)):
        applied.append("exact_reference_deduplication")
    if any(item.managed_paths for item in surfaces):
        applied.append("disjoint_managed_path_union")
    return tuple(name for name in OPERATIONS if name in applied)


def _escapes(path: str) -> bool:
    """Whether a managed path leaves the bundle (`harness-bundle.md`)."""
    if not path or path.startswith("/") or path.startswith("~"):
        return True
    segments = path.split("/")
    return any(segment in {"", ".", ".."} for segment in segments)
