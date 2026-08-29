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
from typing import Final

from ai_stp_cli.local.components import Found, Rule

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
PROVIDER_RULES: Final[tuple[Rule, ...]] = (
    Rule("instruction", "CLAUDE.md", "file", "claude-code"),
    Rule("skill", "skills", "directory", "claude-code"),
    # No `mcp` rule. `.mcp.json` is claude-code's **project** file, committed to
    # version control at a repository root; the user scope lives in
    # `~/.claude.json` under a top-level `mcpServers` table, and the provider
    # lists that file in `never_touch`. So there is no MCP surface a provider
    # can own inside the target at all, and the honest answer is that it does
    # not exist: `native_surface_lost` blocks the bundle.
    #
    # This row and the catalog's global one both cited `code.claude.com/docs/en/mcp`
    # and neither had read it. That page is *about* MCP scopes, and the global
    # entry took the project scope's filename — the same failure as `.mcp.json`
    # on grok, one row further back: a filename travelling without its scope.
    # Settled from the vendor page by the provider side, which withdrew `Mcp`
    # from claude-code's declaration for the same reason.
    Rule("command", "commands", "directory", "claude-code"),
    Rule("agent", "agents", "directory", "claude-code"),
    # Declared by the released provider and unroutable here until now, so a
    # `setting` component for claude-code was refused as exceeding provider
    # capabilities — by *our* table, while the provider had always accepted it.
    # Citation is the provider's own baseline row rather than elimination:
    # `references/claude-code-baseline.json:100`.
    Rule("setting", "settings.json", "file", "claude-code"),
    Rule("instruction", "AGENTS.md", "file", "codex"),
    # `skills`, under the shared convention's own root, not `.agents/skills`
    # under codex's configuration home. `ADR-0127`, and the eighth face of one
    # sentence: this row said `.agents/skills` and was resolved against
    # `--target`, so it landed in `~/.codex/.agents/skills` — a sibling of the
    # directory codex reads, not a child. An install answered `verified` and
    # wrote twenty-nine files the product never saw.
    #
    # The path is right only together with the root it hangs off, and the root
    # is what `target_scope` names. Under `user_root` the provider's target is
    # `~/.agents`, so the surface is `skills` — writing `.agents/` in again
    # would land them at `~/.agents/.agents/skills`.
    #
    # Measured against codex 0.0.10, which declares the scope:
    # `codex/native-files/user-root/1`, namespaces `["skills"]`,
    # kinds `["skill"]`.
    Rule("skill", "skills", "directory", "codex", target_scope="user_root"),
    Rule("setting", "config.toml", "file", "codex"),
    # `references/codex-baseline.json:52` and `:60`. Both were declared by the
    # provider and routable by nothing here, which conformance reported as
    # `declared_route_is_compilable:hook` and `:command` failing under the
    # *consumer* subject — the provider was right and this table was short.
    #
    # Taken from the baseline rather than by elimination even though
    # elimination would have got these two right. It got claude-code's `plugin`
    # wrong in the same pass, and a method that is right four times out of five
    # is not a method.
    # No `agent` row, and the one that was here for a few hours is the sharpest
    # instance of a rule I had already written down. Codex does not load an
    # agent from a file in `~/.codex/agents/`: a role is an `agents.<name>`
    # table in the settings file whose `config_file` points at a TOML layer,
    # resolved relative to the declaring file. Measured against a temporary
    # `CODEX_HOME` — a bad pointer is reported as a malformed role definition,
    # while an `agents/<name>.md` sitting beside it is loaded by nothing and
    # complained about by nothing.
    #
    # It went in on the provider's declaration plus a vendor page listing the
    # TOML fields, which is exactly the move I had argued against in the same
    # week: **a declaration can refute a route and cannot confirm one.** The
    # provider had declared the kind since it was written and its own builder
    # setup had never run, so nothing on either side had exercised it.
    #
    # The route would need two files written together — a settings table and a
    # layer it points at — and a component of one kind is one thing in one
    # namespace. There is no honest way to state it, so it is absent rather
    # than approximated.
    Rule("hook", "hooks.json", "file", "codex"),
    Rule("command", "prompts", "directory", "codex"),
    # No `agent/` prefix: these are relative to the target, and Pi's target
    # already is `~/.pi/agent`. The segment belongs to the home, not inside it,
    # and prefixing it landed every Pi projection in `~/.pi/agent/agent/`.
    Rule("instruction", "AGENTS.md", "file", "pi"),
    # `skill` stays global for pi, and for opencode, cursor and grok-build
    # below, and that is a measurement rather than an omission.
    #
    # From `0.0.28` those four publish a `user_root` scoped profile carrying
    # `skill` -> `skills`, beside codex's. It is tempting to follow, and it
    # would be wrong: read from the shipped binaries, all four **also** keep
    # `skill` in their global profile with `skills` among its namespaces.
    # Codex is the only harness whose global profile does not declare the kind,
    # which is why its row is scoped — forced, not chosen.
    #
    # So for these four the provider offers a second root; it does not retire
    # the first. Moving them would relocate every published skill component out
    # of the harness's own home into `~/.agents`, which is shared across
    # harnesses — a skill installed for pi becomes visible to grok. That is a
    # product decision about who sees what, not a mechanical follow-the-
    # declaration step, and `managed_paths` records `skills/nddev-builder`
    # without the root it hangs off, so the relocation would not be visible in
    # any published passport.
    #
    # Measured 2026-08-29 against `0.0.28`:
    #     claude   global skill=yes  scoped skill=no
    #     codex    global skill=NO   scoped skill=yes
    #     cursor, grok, pi, opencode   global yes  AND  scoped yes
    #
    # The rule that falls out, and it is derivable from the wire format rather
    # than from anyone's judgement: **route a kind to a scope only where the
    # global profile does not declare that kind.** Codex gets its route for the
    # reason it actually has one; the four keep theirs; and a provider adding a
    # second root stops being a decision this table has to make.
    #
    # What the wire format cannot say, and why the rule stops there: declaring
    # `skill` in both profiles answers *can you?*. A routing table needs
    # *should you?*, and whether these four should move is a decision about who
    # sees what.
    Rule("skill", "skills", "directory", "pi"),
    # Native path is `extensions/`; the package family is `package`
    # (`docs/contracts/component-setup-passports.md`, first-party Pi plugin
    # passports, OpenNetwork Pi `projection_kinds`). `extension` is not a
    # protocol value and install plan refused it as an invalid ProjectionKind.
    Rule("plugin", "extensions", "directory", "pi", projection_kind="package"),
    Rule("setting", "settings.json", "file", "pi"),
    # `references/pi-baseline.json:229`. Same shape as codex's `prompts`, and
    # the same reason: declared by the provider, reachable by nothing here.
    Rule("command", "prompts", "directory", "pi"),
    Rule("instruction", "AGENTS.md", "file", "opencode"),
    Rule("skill", "skills", "directory", "opencode"),
    Rule("command", "commands", "directory", "opencode"),
    Rule("agent", "agents", "directory", "opencode"),
    Rule("plugin", "plugins", "directory", "opencode", projection_kind="plugin"),
    Rule("setting", "opencode.json", "file", "opencode"),
    # Cursor installs a plugin rather than sibling directories: its manifest
    # declares commands, hooks, MCP entries, agents, skills and rules as paths
    # inside the plugin, so the plugin is what a provider writes.
    #
    # No `instruction` rule. It used to project `AGENTS.md` into the target,
    # which is cursor's configuration home — and `cursor.com/docs/rules`, the
    # page this row and the catalog's global one both cited, says AGENTS.md is
    # read from the **project root and its subdirectories**. There is no global
    # `~/.cursor/AGENTS.md`; user-level rules are a setting, not a file. So the
    # rule wrote a real file to a path cursor never reads, and the install
    # answered `verified`.
    #
    # The sixth instance of one sentence: a project-scope placement named as a
    # global surface. `.mcp.json` on claude-code and on grok were the same, and
    # the citation was the same kind of citation — a page about the subject,
    # taken as agreement with the row beneath it.
    #
    # Corroborated independently: the released `cursor-setup-system` 0.0.7
    # declares `component_kinds` of exactly `plugin` and `setting`, and its
    # `native_namespaces` are `cli-config.json` and `plugins`. The provider had
    # already stopped accepting the kind this rule produced.
    Rule("setting", "cli-config.json", "file", "cursor"),
    # `plugins`, and `cursor.com/docs/plugins` says local plugins go in
    # `~/.cursor/plugins/local/<name>`. So this is one level short and the
    # product reads nothing — the seventh instance of one sentence, and the
    # third on Cursor where the page that looks authoritative does not name the
    # placement: the plugin reference explains how to build one, not where it
    # is installed.
    #
    # **The rollover, and why it needed a release in the middle.** `install.py`
    # refuses a bundle whose `native_surface` is absent from the provider's
    # declared `native_namespaces`, an exact set difference. So moving this row
    # while the released provider declared `plugins` alone would have turned
    # every cursor install into `the exact native projection exceeds provider
    # capabilities`, and moving the declaration first would have broken every
    # already-shipped CLI. Neither order works: `0.0.8` declares **both**, which
    # opens the window this row moves through, and the old name is dropped a
    # release later. Verified on the released artifact rather than the tag:
    # `["cli-config.json", "plugins", "plugins/local"]`, attestation passing.
    #
    # Neither table caught the original: the released provider declared
    # `plugins` too, so the cross-check against `provider-info` passed on two
    # tables that were wrong together. Only the vendor page settled it, and no
    # test on either side can read one.
    Rule("plugin", "plugins/local", "directory", "cursor", projection_kind="plugin"),
    # Five global surfaces, held for a round because they contradicted
    # `components_are_plugin_declared` — the sentence three cursor defects were
    # corrected *towards*. The question that settled them was whether the
    # product reads a file placed there with no plugin manifest naming it.
    #
    # `mcp.json` was answered by running it: a server written straight to
    # `~/.cursor/mcp.json` is listed and dialled, and both controls hold — the
    # file removed reports no servers, and the same file one directory to the
    # side reports no servers. The product's own help names the global path
    # unprompted.
    #
    # The other four are confirmed at the line in the pinned bundle rather than
    # by a run, because they need an authenticated session: `commands` joins
    # `homedir(), ".cursor", "commands"` and tags entries `scope: "user"`;
    # `hooks.json` has a distinct user tier beside enterprise and project;
    # `rules` is the User Rule branch of the product's own scope picker,
    # hinted "Applies to all your projects"; `skills` is one row of a table the
    # bundle carries, beside `.claude`, `.codex`, `.grok` and `.agents`.
    #
    # So the gap was true of the documentation and false of the product — the
    # docs page describes the manifest key and has not caught up. It is
    # withdrawn in `harness_catalog.py` rather than left standing, because a gap
    # asserted from a page is how `.mcp.json` came to be called global twice.
    #
    # `mcp.json` here is deliberately not the same claim as `.mcp.json` on
    # claude-code and grok. Those were project files at a repository root called
    # global — a filename travelling without its scope. This one is under the
    # configuration home the provider owns, and the provider declares it.
    #
    # `skill -> skills` waited one release. Added with the rest and refused by
    # the evidence slice — `skill -> skills: kind not declared` against
    # `0.0.11` — because it was the provider's own false decline and is declared
    # only from `0.0.13`. Verified against that tag before landing here.
    Rule("instruction", "rules", "directory", "cursor"),
    Rule("skill", "skills", "directory", "cursor"),
    Rule("command", "commands", "directory", "cursor"),
    Rule("hook", "hooks.json", "file", "cursor"),
    Rule("mcp", "mcp.json", "file", "cursor"),
    # Antigravity's home belongs to Gemini: `antigravity-cli/` is its own and
    # `config/` is shared, so both prefixes are part of the relative path rather
    # than something a target adds.
    Rule("setting", "antigravity-cli/settings.json", "file", "antigravity"),
    # `config/plugins`, not `antigravity-cli/plugins`. The row said the latter
    # while every other antigravity row here — skill, agent, hook, mcp — sits
    # under `config/`, and a shared surface that holds four of a setup's five
    # kinds and not the fifth was the tell. Settled against the product rather
    # than argued: `antigravity-setup-system` ships its own plugin at
    # `home/config/plugins/nddev-builder`, where `home/` is the target root.
    #
    # `antigravity-cli/plugins` is not merely unread — it is where the CLI puts
    # what it installs itself, so writing a setup's plugin there lands it in
    # another manager's directory.
    #
    # The tenth instance of one sentence, and the first found by our own two
    # tables being made to answer each other: `provider-info` declares *both*
    # namespaces, so the released-provider cross-check passed on a wrong row, in
    # exactly the way it passed for cursor's `plugins`. What caught it is the
    # new composition conflict comparing a published `managed_paths` against the
    # rule for its kind — the corpus had carried the right path all along and
    # nothing had ever compared the two.
    Rule("plugin", "config/plugins", "directory", "antigravity", projection_kind="plugin"),
    # `config/global_workflows/<name>.md`, invoked as `/workflow-name` across
    # every workspace. Found as a path literal in the pinned `1.1.22` binary and
    # then run, which is the difference between a string and a surface — the
    # catalogue's `no_global_command` gap said this did not exist, on the
    # strength of the product's documentation.
    Rule("command", "config/global_workflows", "directory", "antigravity"),
    # Antigravity was the only harness of the seven with no `instruction` route,
    # and the blank was ours rather than the product's: its own reference lists
    # rules among the five customization elements available inside any
    # customization root, and the provider's declaration had carried four of
    # them.
    #
    # Directory, not file: the product takes `rules/` relative to the
    # customization root, whose global form is `~/.gemini/config/`, and its
    # reference recommends one consolidated `AGENTS.md` under that directory
    # over separate rule files.
    #
    # Landed against the released `0.0.29`, read from the downloaded binary:
    # `instruction` in `component_kinds` and `config/rules` in
    # `native_namespaces`. `0.0.28` declared neither, which is why this row
    # waited a release — with no declaration the route would have composed a
    # bundle the provider refuses, moving an early `native_surface_lost` refusal
    # to a late one, past the point an immutable version can exist.
    Rule("instruction", "config/rules", "directory", "antigravity"),
    Rule("skill", "config/skills", "directory", "antigravity"),
    Rule("agent", "config/agents", "directory", "antigravity"),
    Rule("hook", "config/hooks.json", "file", "antigravity"),
    Rule("mcp", "config/mcp_config.json", "file", "antigravity"),
    Rule("instruction", "AGENTS.md", "file", "grok-build"),
    Rule("skill", "skills", "directory", "grok-build"),
    # No `mcp` rule, exactly as `codex` has none, and for the same reason: both
    # spell their MCP servers as an `mcp_servers` table *inside* `config.toml`
    # (`local/harness_catalog.py`, cited to `docs.x.ai/build/settings`). There
    # is no separate file for a provider to write, so the honest answer is that
    # the surface does not exist and `native_surface_lost` blocks the bundle.
    #
    # It used to say `.mcp.json`, which is claude-code's spelling and reads as
    # correct on the line above it. A grok-build MCP component would have been
    # written to a file grok-build never reads: install verified, MCP absent.
    # Nothing in the live catalog is an `mcp` component yet, so this was a
    # defect with no victim rather than one already paid for.
    Rule("hook", "hooks", "directory", "grok-build"),
    # No `command` rule either, and it is the same copy as the `.mcp.json` above
    # rather than a separate mistake: claude-code has `mcp`, `command`, `agent`
    # and `instruction`, and all four arrived here together.
    #
    # Grok surfaces slash commands as **skills** — a user-invocable skill is
    # `/<skill-name>`, qualified on collision — so there is no `~/.grok/commands`
    # for a provider to write to. Measured on the vendor's own documentation by
    # the provider side (`grok-setup-system#36`), which declines to declare
    # `Command` for grok for exactly this reason: declaring a kind is a promise
    # of rollback, and there is nothing to roll back.
    #
    # `agent` and `instruction` stay. They are absent from the vendor page the
    # catalog cites but present in the provider's own `grok-baseline`
    # `native_discovery`, which is a source rather than a memory.
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


def adopted_covers(item: Found) -> tuple[str, ...]:
    """Target-relative roots an adopted component owns.

    Discovery paths are relative to a config home or ``$HOME`` and must not be
    copied into ``managed_paths`` (`ADR-0127`): ``.agents/skills/x`` against a
    ``~/.agents`` target lands at ``~/.agents/.agents/skills/x``.
    """
    rule = rule_for(item.component_type, item.harness_id)
    name = ""
    if item.provenance.subpath:
        name = PurePosixPath(item.provenance.subpath).name
    if not name:
        name = item.absolute.name
    if rule is None:
        return (f"skills/{name}",) if item.component_type == "skill" and name else ()
    if rule.shape == "file":
        return claimed_paths(rule.relative) if item.component_type == "hook" else (rule.relative,)
    if not name:
        return (rule.relative,)
    return (f"{rule.relative}/{name}",)


def native_surface(component_type: str, harness_id: str) -> str:
    """Where a component of this kind lives, or empty when nowhere."""
    rule = rule_for(component_type, harness_id)
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


def _projection_root_of(component_type: str, harness_id: str) -> str:
    rule = rule_for(component_type, harness_id)
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
        outside = _outside_projection(item, rule_for(item.component_type, target.harness_id))
        for path in sorted(outside):
            conflicts.append(
                Conflict(
                    "managed_path_outside_projection",
                    "a managed path does not sit under this kind's projection root",
                    {
                        "stable_id": item.stable_id,
                        "path": path,
                        "projection_root": _projection_root_of(
                            item.component_type, target.harness_id
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
            claims = claimed_paths(path) if item.component_type == "hook" else (path,)
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
