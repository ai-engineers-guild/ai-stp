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
from pathlib import PurePosixPath
from typing import Any, Final

from ai_stp_cli.local.components import Found, Rule
from ai_stp_foundation.provider_surfaces import provider_route_rows

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
        "managed_path_outside_projection",
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
def _provider_rule(raw: dict[str, Any]) -> Rule:
    fields: dict[str, Any] = dict(raw)
    fields["excluded_names"] = frozenset(fields["excluded_names"])
    return Rule(**fields)


PROVIDER_RULES: Final[tuple[Rule, ...]] = tuple(
    _provider_rule(row) for row in provider_route_rows()
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
    #: Why this lane was assigned. Empty means the caller did not record one,
    #: and the report then says only that the component was named.
    lane_reason: str = ""
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

    #: Which projection scope this composition is compiled for. `global` is the
    #: harness configuration home; `project` is a workspace root, where the
    #: same kinds live under other names; `user_root` is the shared `~/.agents`
    #: root (`ADR-0125`, `ADR-0127`). The scope is chosen per bundle and per
    #: plan, not read off the components: a rule file adopted from one
    #: repository is content, and where it lands next is a decision.
    scope: str = "global"


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

    #: The kind named to the provider. Equal to `component_type` for every
    #: harness that declares the kind itself; different where the product has
    #: no such kind and the component's native form is another one (`#454`).
    #: Empty is read as "the same", so an entry that never reached a rule does
    #: not have to invent one.
    provider_kind: str = ""


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


def rule_for(component_type: str, harness_id: str, *, scope: str = "global") -> Rule | None:
    """Return the target-relative provider projection for one component kind.

    One kind, one harness, one scope. `project` answers only with a rule whose
    target is a workspace root; `user_root` only with a rule whose target is
    the shared `~/.agents` root; `global` answers with the harness home's
    rules first and falls back to a `user_root` rule where the home has none
    of that kind — codex keeps its skills under `~/.agents` and nowhere else
    (`ADR-0127`), so a home compile of a codex skill lands there.
    """
    fallback: Rule | None = None
    for rule in PROVIDER_RULES:
        if rule.component_type != component_type or rule.harness_id != harness_id:
            continue
        if scope == "project":
            if rule.target_scope == "project":
                return rule
        elif scope == "user_root":
            if rule.target_scope == "user_root":
                return rule
        elif rule.target_scope == "global":
            return rule
        elif rule.target_scope == "user_root" and fallback is None:
            fallback = rule
    return fallback


def adopted_covers(item: Found) -> tuple[str, ...]:
    """Target-relative roots an adopted component owns.

    Discovery paths are relative to a config home or ``$HOME`` and must not be
    copied into ``managed_paths`` (`ADR-0127`): ``.agents/skills/x`` against a
    ``~/.agents`` target lands at ``~/.agents/.agents/skills/x``.
    """
    name = ""
    if item.provenance.subpath:
        name = PurePosixPath(item.provenance.subpath).name
    if not name:
        name = item.absolute.name
    return covers(item.component_type, item.harness_id, name, scope=item.scope)


def covers(
    component_type: str, harness_id: str, name: str, *, scope: str = "global"
) -> tuple[str, ...]:
    """Target-relative roots a component of this kind and name owns.

    The rule both capture paths record: adoption names the component from its
    source path, the importer from the catalogue boundary it found, and the
    roots each writes into `managed_paths` are the same roots the compiler
    checks the projection against.
    """
    rule = rule_for(component_type, harness_id, scope=scope)
    if rule is None:
        if component_type == "cli" and name:
            return (f"bin/{name}",)
        return (f"skills/{name}",) if component_type == "skill" and name else ()
    if rule.shape == "file":
        return claimed_paths(rule.relative) if component_type == "hook" else (rule.relative,)
    if not name:
        return (rule.relative,)
    return (f"{rule.relative}/{name}",)


def rerooted(
    component_type: str, harness_id: str, paths: tuple[str, ...], *, scope: str
) -> tuple[str, ...]:
    """A component's managed paths, expressed against the compile scope's root.

    Passports record managed paths against the harness home — the root every
    capture path writes them for, whatever scope the file was found at — so a
    passport is one object however it is later installed. A workspace compile
    re-roots them: the prefix that is the kind's home surface becomes the
    kind's workspace surface, and a path that sits under neither is left as it
    is, for the projection check to name. `hooks.json#hooks` re-roots like a
    file, because the `#key` suffix is not a path segment.
    """
    if scope == "global":
        return paths
    home = rule_for(component_type, harness_id)
    there = rule_for(component_type, harness_id, scope=scope)
    if home is None or there is None or home.relative == there.relative:
        return paths
    moved: list[str] = []
    for path in paths:
        if path == home.relative or path.startswith((f"{home.relative}/", f"{home.relative}#")):
            moved.append(there.relative + path[len(home.relative) :])
        else:
            moved.append(path)
    return tuple(moved)


def native_surface(component_type: str, harness_id: str, *, scope: str = "global") -> str:
    """Where a component of this kind lives, or empty when nowhere."""
    rule = rule_for(component_type, harness_id, scope=scope)
    return "" if rule is None else rule.relative


def compose(surfaces: tuple[Surface, ...], target: Target) -> CompositionReport:
    """Detect every conflict in one composition. Repairs nothing (`REQ-626`).

    Every class is checked and every conflict collected: a composition with
    three problems should be fixable in one pass. The result is sorted, so one
    canonical input produces one report.

    Exact duplicate references are collapsed, not conflicted: `REQ-625` names
    that operation. The extra copy is rejected rather than chosen twice, and
    conflicts run on the collapsed set so a component does not collide with
    itself.
    """
    ordered = sorted(surfaces, key=lambda item: (item.stable_id, item.version, item.revision_id))
    kept: list[Surface] = []
    rejected: list[Rejected] = []
    seen: set[tuple[str, str]] = set()
    for item in ordered:
        key = (item.stable_id, item.version)
        if key in seen:
            rejected.append(
                Rejected(
                    stable_id=item.stable_id,
                    version=item.version,
                    reason="exact reference already in the composition",
                )
            )
            continue
        seen.add(key)
        kept.append(item)
    kept_surfaces = tuple(kept)

    conflicts: list[Conflict] = []
    conflicts.extend(_paths(kept_surfaces, target))
    conflicts.extend(_identities(kept_surfaces))
    conflicts.extend(_precedence(kept_surfaces))
    conflicts.extend(_hooks(kept_surfaces))
    conflicts.extend(_surfaces(kept_surfaces, target))
    conflicts.extend(_environment(kept_surfaces, target))
    conflicts.extend(_permissions(kept_surfaces, target))
    conflicts.extend(_licences(kept_surfaces, target))
    conflicts.extend(_trust(kept_surfaces))
    conflicts.extend(_platform(target))
    conflicts.sort(key=lambda item: (item.code, item.details.get("stable_id", "")))

    return CompositionReport(
        chosen=tuple(
            Chosen(
                stable_id=item.stable_id,
                version=item.version,
                lane=item.lane,
                reason=item.lane_reason or "named by the confirmed composition",
            )
            for item in kept
        ),
        rejected=tuple(rejected),
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
        if item.component_type == "cli":
            entries.append(
                ConversionEntry(
                    stable_id=item.stable_id,
                    component_type="cli",
                    native_surface="bin",
                    projection_kind="package",
                    provider_kind="cli",
                    state=STATE_COMPLETE,
                )
            )
            continue
        rule = rule_for(item.component_type, target.harness_id, scope=target.scope)
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
                provider_kind=rule.provider_kind or item.component_type,
                state=STATE_PARTIAL if losses else STATE_COMPLETE,
                losses=losses,
            )
        )
    return ConversionReport(entries=tuple(entries))


def _projected_root(item: Surface, target: Target) -> str:
    rule = rule_for(item.component_type, target.harness_id, scope=target.scope)
    if rule is None:
        return ""
    if rule.shape == "directory":
        return f"{rule.relative}/{item.source_name}" if item.source_name else ""
    return rule.relative


def _projection_root_of(component_type: str, harness_id: str, scope: str) -> str:
    rule = rule_for(component_type, harness_id, scope=scope)
    return rule.relative if rule is not None else ""


def path_covers(root: str, path: str) -> bool:
    """Whether `path` is `root` or sits strictly under it.

    Passports name native roots. `skills/foo` owns `skills/foo/SKILL.md`.
    `skills/review` does not own `skills/review.md`.
    """
    return path == root or path.startswith(f"{root}/")


def paths_overlap(left: str, right: str) -> bool:
    """Two managed-path claims that are not disjoint."""
    return path_covers(left, right) or path_covers(right, left)


def hook_sibling_directory(manifest: str) -> str:
    """The `hooks/` directory that sits beside a `hooks.json` manifest.

    Native layouts discover the file and keep handlers next to it, not inside
    it. A claim on the file that did not also claim that sibling let a second
    component own `config/hooks/h01.py` while the first owned `config/hooks.json`.
    """
    held = PurePosixPath(manifest)
    if held.name != "hooks.json":
        return ""
    parent = str(held.parent)
    return "hooks" if parent == "." else f"{parent}/hooks"


def claimed_paths(path: str) -> tuple[str, ...]:
    """Ownership claims one declared path actually makes.

    `hooks.json` also owns the sibling handler directory. Every other path is
    itself, as a root.
    """
    sibling = hook_sibling_directory(path)
    return (path, sibling) if sibling else (path,)


def projection_covers(rule: Rule, path: str) -> bool:
    """Whether this kind's native surface can hold `path`."""
    if path_covers(rule.relative, path):
        return True
    if rule.component_type == "hook" and rule.shape == "file":
        sibling = hook_sibling_directory(rule.relative)
        return bool(sibling) and path_covers(sibling, path)
    return False


def managed_path_drift(
    declared: frozenset[str], projected: frozenset[str]
) -> tuple[frozenset[str], frozenset[str]]:
    """Declared roots the artifact missed, and projected paths it never claimed.

    Passports name the native roots a component owns. The artifact then expands
    into files under those roots. Set equality would refuse every directory
    component: the passport says ``skills/foo``, the zip contains
    ``skills/foo/SKILL.md``.
    """
    missing = frozenset(
        root for root in declared if not any(path_covers(root, path) for path in projected)
    )
    undeclared = frozenset(
        path for path in projected if not any(path_covers(root, path) for root in declared)
    )
    return missing, undeclared


def _outside_projection(item: Surface, rule: Rule | None) -> list[str]:
    """Managed paths this kind's rule cannot reach.

    A published `managed_paths` and the root computed from the rule were unioned
    and never compared, so a component could declare any path at all and the
    composition simply carried both. Measured against the live catalogue on
    2026-08-28, three groups disagreed: 61 codex skills declaring
    `.agents/skills/<name>` — relative to `$HOME`, from before the surface moved
    to a `~/.agents` target — one cursor plugin at `plugins/<name>` from before
    the `plugins/local` correction, and one cursor `instruction` for a kind the
    provider stopped accepting.

    Every one of them projected into a path the product does not read, and the
    install still answered `verified`. `install.py` does refuse a native surface
    the provider never declared, but it refuses the whole bundle after selection,
    naming provider capabilities rather than the component that is wrong. This
    says which component and which path, while a person can still act on it.

    The ninth instance of one sentence: a path is only a path together with what
    it is relative to. Declaring the root is what makes the two comparable.

    No rule means no claim. A kind with no row is one this compiler does not
    project, and refusing its paths here would be inventing a rule from absence.
    """
    if rule is None:
        return []
    return [path for path in sorted(set(item.managed_paths)) if not projection_covers(rule, path)]


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
        outside = _outside_projection(
            item, rule_for(item.component_type, target.harness_id, scope=target.scope)
        )
        for path in sorted(outside):
            conflicts.append(
                Conflict(
                    "managed_path_outside_projection",
                    "a managed path does not sit under this kind's projection root",
                    {
                        "stable_id": item.stable_id,
                        "path": path,
                        "projection_root": _projection_root_of(
                            item.component_type, target.harness_id, target.scope
                        ),
                    },
                )
            )
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
            # A contribution owns a key, not the file (`ADR-0129`). Claiming
            # the path would collide with the `setting` component that owns the
            # rest of it, and those two legitimately coexist: the bundle
            # assembles the contribution onto the sibling's bytes.
            #
            # The existing overlap rule needs no change to express this.
            # `config.toml` and `config.toml#mcp_servers` are disjoint because
            # neither is a `/`-rooted prefix of the other, while two components
            # contributing the same key claim the identical string and still
            # collide — which is the case that must keep failing.
            contributing = rule_for(item.component_type, target.harness_id, scope=target.scope)
            if contributing is not None and contributing.declared_key:
                claims: tuple[str, ...] = (f"{path}#{contributing.declared_key}",)
            elif item.component_type == "hook":
                claims = claimed_paths(path)
            else:
                claims = (path,)
            held = next(
                (
                    owner
                    for claim in claims
                    for claimed, owner in owners.items()
                    if owner != item.stable_id and paths_overlap(claimed, claim)
                ),
                None,
            )
            if held is not None:
                conflicts.append(
                    Conflict(
                        "managed_path_owned_twice",
                        "two components claim the same managed path",
                        {"stable_id": item.stable_id, "path": path, "also": held},
                    )
                )
                continue
            for claim in claims:
                owners[claim] = item.stable_id
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
                **(
                    {
                        "hint": (
                            "carry servers in the setting component; "
                            "this harness has no separate MCP file"
                        )
                    }
                    if item.component_type == "mcp"
                    else {}
                ),
            },
        )
        for item in sorted(surfaces, key=lambda item: item.stable_id)
        if item.required
        and item.component_type != "cli"
        and not native_surface(item.component_type, target.harness_id, scope=target.scope)
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
