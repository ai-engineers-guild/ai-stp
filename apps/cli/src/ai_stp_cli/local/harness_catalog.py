"""Single executable owner of supported harness layouts and capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, cast

from ai_stp_foundation.harnesses import (
    UNDEFINED_HARNESS,
    HarnessId,
    SupportTier,
    support_tier,
)

#: Wider than `SupportTier`: `undefined` is shared conventions, not a harness.
type HarnessSupport = SupportTier | Literal["portable"]


@dataclass(frozen=True)
class Layout:
    component_type: str
    relative: str
    shape: str
    source: str
    scope: str
    root: str = "config"

    #: How this row was established, weakest first: `page` — a vendor page and
    #: nothing else; `bytes` — the product's own shipped bytes were read, a
    #: literal or an embedded reference in a pinned artifact; `ran` — the
    #: product was run and the behaviour observed.
    #:
    #: The default is the weakest value on purpose. Absence of a record of
    #: measurement is not evidence of measurement, and a column that graded
    #: generously would make the catalogue look measured and change nothing.
    #:
    #: What it marks is a property of *this repository*, not of the row.
    #: `page` rows are not suspicious — most are correct and several were
    #: carefully reasoned. They are the rows where **a wrong answer is
    #: undetectable by anything here**, which is a different and worse property
    #: than being unverified. Every projection defect found this week sat on a
    #: real, live vendor page: `antigravity-cli/plugins`, cursor's `plugins`,
    #: `.mcp.json` called global on two harnesses. Ranking a page above a
    #: measurement would promote exactly those.
    evidence: str = "page"

    excluded_names: frozenset[str] = frozenset()
    projection_kind: str = "native_files"

    #: When set, this file is a component only if it structurally declares at
    #: least one entry under this key. Used where a kind lives inside a file
    #: that is also a setting, so its mere presence proves nothing. Only key
    #: names are read; see `ai_stp_cli.local.mcp_clients`.
    declared_key: str = ""

    #: The same idea for the directory shape: a child carrying a plugin
    #: manifest belongs to the `plugin` kind rather than to this layout's. Set
    #: where one directory serves two kinds and the product separates them by a
    #: manifest instead of by location.
    excludes_plugin_manifest: bool = False


@dataclass(frozen=True)
class HarnessDefinition:
    harness_id: str
    title: str
    executable: str | None
    version_arguments: tuple[str, ...]
    config_root: str | None
    source: str
    layouts: tuple[Layout, ...]
    native_authoring: frozenset[str]
    gaps: tuple[str, ...] = ()
    xdg_config: bool = False
    #: The leaf under `XDG_CONFIG_HOME` when the product spells it differently
    #: there than under the home directory.
    xdg_config_root: str | None = None
    root_override: str | None = None
    npm_packages: tuple[str, ...] = ()
    scoop_app: str | None = None

    #: Other command names the vendor installs for the same product. Cursor
    #: ships two — `binNames: ["agent", "cursor-agent"]` from the installer
    #: object in the pinned bundle — and "neither is more canonical, so either
    #: detects an installation" was written above the executable field long
    #: before detection could actually do it.
    executable_aliases: tuple[str, ...] = ()

    @property
    def support(self) -> HarnessSupport:
        """The declared support level, read from its owner rather than restated.

        For the supported harnesses this is the product tier owned by
        `ai_stp_foundation.harnesses`. It used to be the third positional field
        of every definition here, and the same table also existed in the
        platform catalog projection; deriving it removes the second copy
        instead of keeping two in agreement by hand.

        `undefined` is not a harness and has no product tier. It is the shared
        conventions entry, and `portable` says exactly that. Answering it here
        rather than storing it keeps the special case visible instead of hiding
        it as a third literal among the product tiers.
        """
        if self.harness_id == UNDEFINED_HARNESS:
            return "portable"
        return support_tier(cast("HarnessId", self.harness_id))

    #: Subtrees of the configuration root that hold runtime state rather than
    #: configuration: session transcripts, job records, caches, downloads.
    #: Relative to the configuration root, POSIX separators, no leading slash.
    #:
    #: A denylist rather than an allowlist, deliberately. The layouts above are
    #: incomplete for import — `codex` declares `hooks.json` only at project
    #: scope and `claude-code` declares no plugin layout at all — so importing
    #: only what is declared would silently drop configuration a person wrote.
    #: Naming state explicitly can only ever exclude something named here.
    state_paths: tuple[str, ...] = ()


def _layout(
    component_type: str,
    relative: str,
    shape: str,
    source: str,
    scope: str,
    *,
    root: str = "config",
    excluded: frozenset[str] = frozenset(),
    declared_key: str = "",
    excludes_plugin_manifest: bool = False,
    evidence: str = "page",
) -> Layout:
    return Layout(
        component_type,
        relative,
        shape,
        source,
        scope,
        root,
        evidence,
        excluded,
        declared_key=declared_key,
        excludes_plugin_manifest=excludes_plugin_manifest,
    )


G = "global"
P = "project"

#: The table key that holds MCP client servers. `codex` and `grok-build` spell
#: it the same way in the same TOML file; `opencode` spells it its own way in
#: JSON. Named here rather than repeated at each layout so the two harnesses
#: that share a spelling are visibly sharing one fact.
CODEX_MCP_KEY = "mcp_servers"
OPENCODE_MCP_KEY = "mcp"
CLAUDE = "code.claude.com/docs/en"
CODEX = "learn.chatgpt.com/docs"
PI = "pi.dev/docs/latest"
OPENCODE = "opencode.ai/docs"
GROK = "docs.x.ai/build"
CURSOR = "cursor.com/docs"
ANTIGRAVITY = "antigravity.google/docs"

#: Four citations in this file answered 404 when somebody finally fetched them,
#: and two of those were written the same day — a URL composed from the pattern
#: of its neighbours rather than from a page that was opened. Nothing here
#: fetches a citation, so a dead one is found by a person reading it and in no
#: other way; `just evidence-citations` is that person, made repeatable.
#:
#: Named rather than interpolated, because `f"{ANTIGRAVITY}/commands"` reads as
#: derived from a known root and is exactly how the wrong three were produced.
ANTIGRAVITY_AGENTS = "antigravity.google/docs/subagents"
ANTIGRAVITY_COMMANDS = "antigravity.google/docs/slash-commands"
ANTIGRAVITY_SETTINGS = "antigravity.google/docs/settings"
CURSOR_COMMANDS = "docs.cursor.com/en/cli/reference/slash-commands"

DEFINITIONS: Final[tuple[HarnessDefinition, ...]] = (
    HarnessDefinition(
        "claude-code",
        "Claude Code",
        "claude",
        ("--version",),
        ".claude",
        f"{CLAUDE}/settings",
        (
            # `~/.claude/rules/` — "personal rules ... apply to every project on
            # your machine", a directory beside `CLAUDE.md` and not inside it.
            # Declared by neither this project nor the provider until now, and
            # found the same way the last four were: by re-reading a page cited
            # for a different row.
            #
            # Discovery only, and for a reason that is not the override files'.
            # Nothing is being protected from us here — the surface is simply
            # already spoken for. `instruction` routes to `CLAUDE.md`, and one
            # component kind with two projection surfaces leaves the compiler
            # choosing between them with nothing to choose on.
            _layout("instruction", "rules", "directory", f"{CLAUDE}/memory", G),
            _layout("instruction", "CLAUDE.md", "file", f"{CLAUDE}/memory", G),
            _layout(
                "skill",
                "skills",
                "directory",
                f"{CLAUDE}/skills",
                G,
                excludes_plugin_manifest=True,
            ),
            _layout("agent", "agents", "directory", f"{CLAUDE}/sub-agents", G),
            _layout("command", "commands", "directory", f"{CLAUDE}/slash-commands", G),
            _layout("setting", "settings.json", "file", f"{CLAUDE}/settings", G),
            # Hooks live inside the settings file the row above already names,
            # under a `hooks` key — the same shape as codex's `mcp_servers`, and
            # the reason `declared_key` exists: the file's presence proves the
            # setting, never the hook.
            #
            # There was no `hook` row at all, so the capability model called
            # claude-code's hooks `unsupported`, which says the product cannot do
            # it. `#460` says the opposite and is right.
            #
            # Read from the shipped `2.1.251` bytes rather than a page, with
            # controls: two invented key names return zero, and the product's own
            # strings say "require hooks configured in settings.json — the
            # harness executes these", "Change settings: hooks, permissions,
            # environment variables", and `disableAllHooks` "in your user
            # settings". So the surface is the user-scope settings file.
            _layout(
                "hook",
                "settings.json",
                "file",
                f"{CLAUDE}/hooks",
                G,
                declared_key="hooks",
                evidence="bytes",
            ),
            # No global `mcp` row. The cited page lists three scopes and none of
            # them is a `.mcp.json` in the configuration home: `local` and `user`
            # both live in `~/.claude.json`, and `project` is `.mcp.json` at a
            # repository root. This entry took the project scope's filename and
            # called it global, which is why it read as correct and why the two
            # tables agreed with each other while both were wrong.
            _layout("instruction", "CLAUDE.md", "file", f"{CLAUDE}/memory", P),
            # Both project placements are read by the harness, and only the
            # root one was declared. Observed directly: a Claude Code session
            # opened in a repository whose instructions live at
            # `.claude/CLAUDE.md` reports them as "project instructions,
            # checked into the codebase" — this repository is such a case, so
            # `ai-stp` was blind to its own.
            _layout("instruction", ".claude/CLAUDE.md", "file", f"{CLAUDE}/memory", P),
            # The project half of the same pair, and it has consequence rather
            # than symmetry: user rules load first and a project `.claude/rules`
            # takes precedence over them, so a repository holding one changes
            # what a machine-wide floor means.
            _layout("instruction", ".claude/rules", "directory", f"{CLAUDE}/memory", P),
            _layout(
                "skill",
                ".claude/skills",
                "directory",
                f"{CLAUDE}/skills",
                P,
                excludes_plugin_manifest=True,
            ),
            _layout("agent", ".claude/agents", "directory", f"{CLAUDE}/sub-agents", P),
            _layout("command", ".claude/commands", "directory", f"{CLAUDE}/slash-commands", P),
            _layout("setting", ".claude/settings.json", "file", f"{CLAUDE}/settings", P),
            _layout("mcp", ".mcp.json", "file", f"{CLAUDE}/mcp", P),
        ),
        frozenset({"native_files", "plugin_manifest"}),
        npm_packages=("@anthropic-ai/claude-code",),
        state_paths=(
            "backups",
            "cache",
            "chrome",
            "daemon",
            "downloads",
            "file-history",
            "jobs",
            "paste-cache",
            "projects",
            "session-env",
            "sessions",
            "shell-snapshots",
            "tasks",
            "telemetry",
            "todos",
            # `plugins/` is configuration at its top level — `installed_plugins.json`
            # and `known_marketplaces.json` say what this installation uses — while
            # these three hold the fetched copies.
            "plugins/cache",
            "plugins/data",
            "plugins/marketplaces",
            # Measured 2026-09-01 on a live home rather than a page: the
            # product keeps its OAuth tokens (`.credentials.json`), updater
            # state, feedback queue, its own plan files and two caches inside
            # the configuration root, all with importable suffixes.
            ".credentials.json",
            ".last-update-result.json",
            "feedback",
            "gh-pr-status-cache.json",
            "mcp-needs-auth-cache.json",
            "plans",
        ),
    ),
    HarnessDefinition(
        "codex",
        "Codex",
        "codex",
        ("--version",),
        ".codex",
        f"{CODEX}/config-file/config-reference",
        (
            # `AGENTS.override.md` supersedes `AGENTS.md` entirely: codex reads
            # "the first non-empty file at this level", checking the override
            # first, in the codex home and in every directory from the project
            # root down. Its whole purpose is a temporary escape from a managed
            # floor without deleting one.
            #
            # Discovery only. A provider that owned this path could take that
            # escape away with `remove`, and the provider side declines it for
            # that reason. What we owe a person is not ownership but an answer:
            # a home holding one makes an installed instruction inert, the
            # install still reports `verified`, and without this row nothing
            # anywhere would say why the floor is not applying.
            _layout(
                "instruction",
                "AGENTS.override.md",
                "file",
                "developers.openai.com/codex/guides/agents-md",
                G,
            ),
            _layout("instruction", "AGENTS.md", "file", f"{CODEX}/config-file/config-reference", G),
            _layout("command", "prompts", "directory", f"{CODEX}/config-file/config-reference", G),
            _layout("setting", "config.toml", "file", f"{CODEX}/config-file/config-reference", G),
            _layout(
                "mcp",
                "config.toml",
                "file",
                f"{CODEX}/config-file/config-reference",
                G,
                declared_key=CODEX_MCP_KEY,
            ),
            _layout(
                "setting", ".codex/config.toml", "file", f"{CODEX}/config-file/config-basic", P
            ),
            _layout(
                "mcp",
                ".codex/config.toml",
                "file",
                f"{CODEX}/config-file/config-basic",
                P,
                declared_key=CODEX_MCP_KEY,
            ),
            _layout(
                "agent", ".codex/agents", "directory", f"{CODEX}/agent-configuration/subagents", P
            ),
            # A standalone `<name>.toml` under the configuration home *is* a
            # role, and both estates recorded the opposite until 2026-08-30:
            # that a codex role is only an `agents.<name>` table in the settings
            # file plus a layer it points at.
            #
            # Measured on the pinned `codex-cli 0.151.0` binary, `env -i` with a
            # temporary `CODEX_HOME`, read back through `codex doctor`, and
            # reproduced here independently of the side that found it:
            #
            #   name+description+developer_instructions  accepted, silent
            #   missing `description`   "role ... must define a description"
            #   an invented directory   silent — not scanned
            #   the same file as `.md`  silent — the scan filters on `.toml`
            #
            # That last row is why the earlier measurement was wrong: it planted
            # a `.md`, and `discovery.rs` admits only `*.toml`, so its negative
            # control could not have failed. `evidence="ran"` because the
            # product was run, not because a page was read.
            _layout(
                "agent",
                "agents",
                "directory",
                f"{CODEX}/agent-configuration/subagents",
                G,
                evidence="ran",
            ),
            _layout("hook", ".codex/hooks.json", "file", f"{CODEX}/hooks", P),
        ),
        frozenset({"native_files", "plugin_manifest", "hooks_directory"}),
        root_override="CODEX_HOME",
        npm_packages=("@openai/codex",),
        state_paths=(
            "cache",
            "logs",
            "sessions",
            "packages",
            # Measured 2026-09-01 on a live `~/.codex`: OAuth tokens in
            # `auth.json`, a models cache, OAuth lock files, a bin directory
            # and a `.tmp` staging dir — product state, not authored
            # configuration, and `auth.json` is the one that must never read
            # as somebody's setup.
            ".tmp",
            "auth.json",
            "bin",
            "mcp-oauth-locks",
            "models_cache.json",
        ),
    ),
    HarnessDefinition(
        "pi",
        "Pi",
        "pi",
        ("--version",),
        ".pi/agent",
        f"{PI}/environment-variables",
        (
            # The same escape hatch, and the same reason for discovering it
            # without owning it: a directory holding `AGENTS.override.md` makes
            # Pi load it *instead of* `AGENTS.md` or `CLAUDE.md` from that
            # directory, and `~/.pi/agent` is the directory a provider writes
            # the global floor into.
            #
            # Global only, here and for codex. A project-scope override displaces
            # files this program does not install, so discovering it would report
            # a fact with no consequence; the global one silences the floor we
            # put there and reports `verified` doing it.
            _layout("instruction", "AGENTS.override.md", "file", f"{PI}/sdk", G),
            _layout("instruction", "AGENTS.md", "file", f"{PI}/sdk", G),
            _layout("skill", "skills", "directory", f"{PI}/skills", G),
            _layout("plugin", "extensions", "directory", f"{PI}/extensions", G),
            _layout("command", "prompts", "directory", f"{PI}/prompt-templates", G),
            _layout("setting", "settings.json", "file", f"{PI}/settings", G),
            _layout("setting", "models.json", "file", f"{PI}/sdk", G),
            _layout("skill", ".pi/skills", "directory", f"{PI}/skills", P),
            _layout("plugin", ".pi/extensions", "directory", f"{PI}/extensions", P),
            _layout("command", ".pi/prompts", "directory", f"{PI}/prompt-templates", P),
            _layout("setting", ".pi/settings.json", "file", f"{PI}/settings", P),
        ),
        frozenset({"native_files"}),
        # `mcp.json` files do appear under `~/.pi/agent`, but they are written by
        # a community MCP bridge extension rather than by Pi, and the two seen in
        # the wild disagree on the key (`mcpServers` against `mcp.servers`). The
        # documentation index carries no MCP page at all, so there is no layout to
        # declare here -- only a gap to state.
        gaps=("no_project_plugin_manifest", "no_documented_mcp_client_config"),
        root_override="PI_CODING_AGENT_DIR",
        # Current vendor first. The previous name still publishes and still
        # answers Windows version fallback for an unmoved `node_modules` tree.
        npm_packages=(
            "@earendil-works/pi-coding-agent",
            "@mariozechner/pi-coding-agent",
        ),
        # Measured 2026-09-01 on a live `~/.pi/agent`: the product keeps its
        # OAuth tokens and its model store beside the settings it documents.
        state_paths=("auth.json", "models-store.json"),
    ),
    HarnessDefinition(
        "opencode",
        "OpenCode",
        "opencode",
        ("--version",),
        "opencode",
        f"{OPENCODE}/config",
        (
            *(
                _layout(kind, path, shape, f"{OPENCODE}/{doc}", scope)
                for scope, prefix in ((G, ""), (P, ".opencode/"))
                for kind, path, shape, doc in (
                    ("skill", f"{prefix}skills", "directory", "skills"),
                    ("agent", f"{prefix}agents", "directory", "agents"),
                    ("command", f"{prefix}commands", "directory", "commands"),
                    ("plugin", f"{prefix}plugins", "directory", "plugins"),
                )
            ),
            # `~/.config/opencode/AGENTS.md`, which is the target a provider
            # already writes an instruction to. Projected since the rules table
            # was written and discoverable by nothing, so a person's existing
            # global rules were invisible to `harness discover` and to every
            # plan built on it. Project scope is the shared convention's, under
            # `undefined`, rather than a second per-harness copy of one file.
            _layout("instruction", "AGENTS.md", "file", f"{OPENCODE}/rules", G),
            *(
                _layout("setting", f"opencode.{suffix}", "file", f"{OPENCODE}/config", scope)
                for scope in (G, P)
                for suffix in ("json", "jsonc")
            ),
            # The TUI half — keybinds, theme, attention, sounds — is a separate
            # document from `opencode.json`, which the same docs describe as
            # server and runtime behaviour. Both formats again, for the same
            # reason: opencode reads JSON and JSONC wherever the file sits, so
            # `.jsonc` is an alternative spelling rather than a second scope.
            #
            # Declared by neither side until 2026-08-27, and found by reading
            # the page rather than either table.
            *(
                _layout("setting", f"tui.{suffix}", "file", f"{OPENCODE}/tui", scope)
                for scope in (G, P)
                for suffix in ("json", "jsonc")
            ),
            *(
                _layout(
                    "mcp",
                    f"opencode.{suffix}",
                    "file",
                    f"{OPENCODE}/config",
                    scope,
                    declared_key=OPENCODE_MCP_KEY,
                )
                for scope in (G, P)
                for suffix in ("json", "jsonc")
            ),
        ),
        frozenset({"native_files"}),
        xdg_config=True,
        root_override="OPENCODE_CONFIG_DIR",
        npm_packages=("opencode-ai", "opencode"),
        scoop_app="opencode",
    ),
    HarnessDefinition(
        "grok-build",
        "Grok Build",
        "grok",
        ("--version",),
        ".grok",
        f"{GROK}/settings",
        (
            # `~/.grok/AGENTS.md`. The vendor page names `~/.grok/` as the
            # global rules location and `AGENTS.md` as one of the filenames read
            # there. Projected all along and discoverable by nothing, the same
            # gap as opencode's and found the same way — by resolving the
            # projection against the vendor page rather than reading the row.
            #
            # Only `AGENTS.md`. Grok also reads `Agents.md`, `AGENT.md`,
            # `CLAUDE.md`, `Claude.md`, `CLAUDE.local.md` and `.grok/rules/*.md`,
            # and modelling those would make discovery report six components
            # where a person wrote one file. They are alternative spellings of
            # the surface this row already names, and `AGENTS.md` is the one a
            # provider writes.
            _layout("instruction", "AGENTS.md", "file", f"{GROK}/features/project-rules", G),
            _layout(
                "skill", "skills", "directory", f"{GROK}/features/skills-plugins-marketplaces", G
            ),
            _layout(
                "plugin",
                "plugins",
                "directory",
                f"{GROK}/features/skills-plugins-marketplaces",
                G,
                excluded=frozenset({"marketplaces"}),
            ),
            _layout(
                "hook", "hooks", "directory", f"{GROK}/features/skills-plugins-marketplaces", G
            ),
            _layout("setting", "config.toml", "file", f"{GROK}/settings", G),
            _layout(
                "mcp", "config.toml", "file", f"{GROK}/settings", G, declared_key=CODEX_MCP_KEY
            ),
            _layout(
                "skill",
                ".grok/skills",
                "directory",
                f"{GROK}/features/skills-plugins-marketplaces",
                P,
            ),
            _layout(
                "plugin",
                ".grok/plugins",
                "directory",
                f"{GROK}/features/skills-plugins-marketplaces",
                P,
            ),
            _layout(
                "hook",
                ".grok/hooks",
                "directory",
                f"{GROK}/features/skills-plugins-marketplaces",
                P,
            ),
            _layout("setting", ".grok/config.toml", "file", f"{GROK}/settings", P),
            _layout(
                "mcp",
                ".grok/config.toml",
                "file",
                f"{GROK}/settings",
                P,
                declared_key=CODEX_MCP_KEY,
            ),
        ),
        frozenset({"native_files"}),
        gaps=("marketplace_provenance_not_public",),
        root_override="GROK_HOME",
        # Measured 2026-09-01 on a live `~/.grok`, which is the busiest state
        # root of the seven: vendor docs and changelogs, session and campaign
        # records, caches, downloads, bundled runtime, completions, memory
        # traces and OAuth tokens all live beside `config.toml` with
        # importable suffixes.
        state_paths=(
            "CHANGELOG.json",
            "CHANGELOG.md",
            "README.md",
            "active_sessions.json",
            "auth.json",
            "bin",
            "bundled",
            "campaigns_state.json",
            "completions",
            "docs",
            "downloads",
            "logs",
            "marketplace-cache",
            "memtrace",
            "models_cache.json",
            "relocations",
            "sessions",
            "slash-mru.json",
            "tip_cursor.json",
            "vendor",
            "version.json",
        ),
    ),
    HarnessDefinition(
        "cursor",
        "Cursor CLI",
        # Detection on `PATH`, which is not the name the provider exposes in its
        # own prefix. The vendor installs **two**, from the installer object in
        # the pinned bundle: `binNames: ["agent", "cursor-agent"]`, with a shim
        # that execs `~/.local/bin/agent`. Neither is more canonical, so either
        # detects an installation.
        #
        # Written down because the names collapse easily and one already did:
        # `agent` is what the provider exposes and one of the two the vendor
        # installs, `cursor-agent` is the vendor's other installed name and the
        # archive member's filename, and `dist-package/cursor-agent.cmd` is a
        # path inside the Windows archive rather than a command at all. This
        # field is the first subject only, and changing it to `agent` on a
        # sentence about exposure would be changing the answer to a different
        # question.
        "cursor-agent",
        ("--version",),
        ".cursor",
        f"{CURSOR}/cli/reference/configuration",
        (
            # The one cursor surface built by calling the config resolver
            # (`CURSOR_CONFIG_DIR`, then `$XDG_CONFIG_HOME/cursor`, else
            # `~/.cursor`); the other global surfaces are literal `~/.cursor`
            # joins in the pinned bundle. The long note below measured this and
            # said a per-surface root was "not worth inventing for a single
            # file until something depends on it" — discovery now does: with
            # the variable set, a whole-harness override sent six literal
            # surfaces to a directory the product never reads them from.
            _layout(
                "setting",
                "cli-config.json",
                "file",
                f"{CURSOR}/cli/reference/configuration",
                G,
                root="cursor_config",
            ),
            # Cursor carries components inside a plugin rather than in sibling
            # directories: `.cursor-plugin/plugin.json` declares `commands`,
            # `hooks`, `mcpServers`, `agents`, `skills` and `rules` as relative
            # paths, so the plugin is the unit this harness installs.
            # `~/.cursor/plugins/local/<name>` — "put either plugin format in
            # `~/.cursor/plugins/local`". The row said `plugins`, one level
            # short, and the discovery half of the same defect the projection
            # rule carried: a person writing their own plugin writes here, and
            # a scan of the parent finds a directory rather than a plugin.
            #
            # Cited to `cursor.com/docs/plugins` rather than the plugin
            # reference. The reference explains how to build one and never says
            # where it is installed — the third Cursor row where the page that
            # looks authoritative for a thing does not name its placement.
            _layout("plugin", "plugins/local", "directory", f"{CURSOR}/plugins", G),
            _layout("instruction", ".cursor/rules", "directory", f"{CURSOR}/rules", P),
            _layout("plugin", ".cursor/plugins", "directory", f"{CURSOR}/reference/plugins", P),
            # Five user-scope surfaces the docs page does not mention and the
            # product reads. `mcp.json` was confirmed by running the product,
            # with both controls; the rest at the line in the pinned bundle.
            # The `rules` row below is the User Rule scope, a sibling of the
            # project one two lines up rather than a correction of it.
            _layout("skill", "skills", "directory", f"{CURSOR}/skills", G),
            _layout("instruction", "rules", "directory", f"{CURSOR}/rules", G, evidence="bytes"),
            _layout("command", "commands", "directory", CURSOR_COMMANDS, G, evidence="bytes"),
            _layout("hook", "hooks.json", "file", f"{CURSOR}/hooks", G, evidence="bytes"),
            _layout("mcp", "mcp.json", "file", f"{CURSOR}/mcp", G, evidence="ran"),
        ),
        frozenset({"native_files", "plugin_manifest"}),
        # `components_are_plugin_declared` withdrawn. It said skills, agents,
        # commands, hooks and MCP entries are declared by a plugin manifest and
        # have no global layout — true of `cursor.com/docs`, false of the
        # product, which reads all of them at user scope. `agent` is the one
        # kind with no global surface found, so the gap narrows rather than
        # disappearing.
        gaps=("no_global_agent",),
        # **Not XDG, and the correction is to a fix made here yesterday.**
        #
        # `CURSOR_CONFIG_DIR`, then `XDG_CONFIG_HOME` giving `$XDG_CONFIG_HOME/cursor`,
        # else `~/.cursor` is the config *resolver*, and it was read correctly.
        # What was wrong was treating a resolver as a statement about the home:
        # of the eight namespaces this harness owns, exactly one —
        # `cli-config.json` — is built by calling it. `commands`, `rules`,
        # `hooks.json`, `mcp.json`, `plugins` and `plugins/local` are literal
        # `join(homedir(), ".cursor", …)` in the pinned bundle and move for no
        # variable at all. A separate `CURSOR_DATA_DIR` carries `projects` and
        # `computer-use`, and nothing here.
        #
        # So turning XDG on sent discovery, projection and the target survey to
        # `$XDG_CONFIG_HOME/cursor` for six of the seven surfaces this catalogue
        # carries, on any machine with the variable set. Before that change the
        # home was unconditionally `~/.cursor` and could not be wrong; the fix
        # is what broke it. Reverted.
        #
        # `~/.cursor` was right for seven of eight all along. The one surface
        # that does move needs a per-surface root, which the vocabulary here
        # (`config` and `home`) cannot express and which is not worth inventing
        # for a single file until something depends on it.
        #
        # The two counts above are unverified rather than confirmed. Re-measured
        # 2026-08-29: this catalogue carries nine cursor layouts, seven global
        # and two project, so "the seven surfaces this catalogue carries" reads
        # as the global set and "eight" as that set plus the `CURSOR_DATA_DIR`
        # surface named above, which the catalogue does not carry. That is a
        # reading, not the author's measurement, and inventing a justification
        # for a number is not checking it. The decision the paragraph records —
        # revert to XDG-blind — does not rest on either count.
        #
        # Both of the guesses considered were wrong, and neither was the shape:
        # "reads like data" would have put `plugins` under `CURSOR_DATA_DIR`,
        # and "comes off the config resolver" would have kept all seven on XDG.
        # Only following each surface's own construction answered it.
        #
        # The per-surface root exists now (`cli-config.json` above carries
        # `root="cursor_config"`), so the whole-harness override is gone: it
        # moved six literal surfaces whenever the variable was set.
        executable_aliases=("agent",),
        # Measured 2026-09-01 on a live `~/.cursor`: chat transcripts, project
        # records, telemetry caches and the agent's own state file sit beside
        # `cli-config.json` — the data-dir surfaces default into the home.
        state_paths=(
            "agent-cli-state.json",
            "ai-tracking",
            "chats",
            "projects",
            "statsig-cache.json",
        ),
    ),
    HarnessDefinition(
        "antigravity",
        "Antigravity CLI",
        "agy",
        ("--version",),
        # The home is not the product's own: Antigravity keeps its configuration
        # inside Gemini's, split between `antigravity-cli/` for what is its own
        # and `config/` for surfaces shared with Gemini CLI.
        ".gemini",
        ANTIGRAVITY_SETTINGS,
        (
            _layout(
                "setting", "antigravity-cli/settings.json", "file", f"{ANTIGRAVITY}/settings", G
            ),
            _layout(
                "setting", "antigravity-cli/keybindings.json", "file", f"{ANTIGRAVITY}/settings", G
            ),
            _layout("plugin", "antigravity-cli/plugins", "directory", f"{ANTIGRAVITY}/plugins", G),
            _layout(
                "plugin", "config/plugins", "directory", f"{ANTIGRAVITY}/plugins", G, evidence="ran"
            ),
            # Global workflows, Markdown invoked as `/workflow-name` across
            # every workspace. Discovery has to know it for the same reason
            # projection does: an object living here is one this catalogue
            # would otherwise report as somebody's loose notes.
            _layout(
                "command",
                "config/global_workflows",
                "directory",
                ANTIGRAVITY_COMMANDS,
                G,
                evidence="ran",
            ),
            _layout("skill", "config/skills", "directory", f"{ANTIGRAVITY}/skills", G),
            _layout("agent", "config/agents", "directory", ANTIGRAVITY_AGENTS, G),
            _layout("hook", "config/hooks.json", "file", f"{ANTIGRAVITY}/hooks", G),
            _layout("mcp", "config/mcp_config.json", "file", f"{ANTIGRAVITY}/mcp", G),
            _layout("plugin", ".agents/plugins", "directory", f"{ANTIGRAVITY}/plugins", P),
            _layout("skill", ".agents/skills", "directory", f"{ANTIGRAVITY}/skills", P),
            _layout("agent", ".agents/agents", "directory", ANTIGRAVITY_AGENTS, P),
            _layout("hook", ".agents/hooks.json", "file", f"{ANTIGRAVITY}/hooks", P),
            _layout("mcp", ".agents/mcp_config.json", "file", f"{ANTIGRAVITY}/mcp", P),
        ),
        frozenset({"native_files", "plugin_manifest"}),
        # The product documents instructions and commands only per project, in
        # `.agents/`, so there is nothing global to declare for either. There is
        # also no documented variable that moves the home.
        #
        # `no_global_command` is now known to be a claim about the documentation
        # rather than about the product. The provider author found
        # `config/workflows/`, `config/workflows.json` and
        # `config/global_workflows/<name>.md` as path literals in the pinned
        # `1.1.22` binary — a global workflow surface, which is the first
        # evidence against the sentence above.
        #
        # Somebody ran it. Global workflows are Markdown invoked as
        # `/workflow-name` across every workspace, so `no_global_command` was
        # false — a gap asserted from a vendor page, which is exactly how
        # `.mcp.json` came to be called global on two harnesses. Withdrawn, and
        # `command` now routes to `config/global_workflows` in `composition.py`.
        gaps=("no_global_instruction", "no_documented_root_override"),
    ),
    HarnessDefinition(
        "undefined",
        "Shared conventions",
        None,
        (),
        None,
        "agentskills.io/specification",
        (
            _layout(
                "skill",
                ".agents/skills",
                "directory",
                f"{CODEX}/build-skills",
                G,
                root="home",
                evidence="ran",
            ),
            _layout(
                "command",
                ".agents/commands",
                "directory",
                f"{GROK}/features/skills-plugins-marketplaces",
                G,
                root="home",
            ),
            _layout("instruction", "AGENTS.md", "file", "agents.md", P),
            _layout("skill", ".agents/skills", "directory", f"{CODEX}/build-skills", P),
        ),
        frozenset({"native_files"}),
        gaps=("no_single_harness_owner",),
    ),
)


BY_ID: Final[dict[str, HarnessDefinition]] = {item.harness_id: item for item in DEFINITIONS}
