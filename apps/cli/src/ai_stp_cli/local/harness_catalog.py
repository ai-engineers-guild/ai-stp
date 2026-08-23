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
    excluded_names: frozenset[str] = frozenset()
    projection_kind: str = "native_files"

    #: When set, this file is a component only if it structurally declares at
    #: least one entry under this key. Used where a kind lives inside a file
    #: that is also a setting, so its mere presence proves nothing. Only key
    #: names are read; see `ai_stp_cli.local.mcp_clients`.
    declared_key: str = ""


@dataclass(frozen=True)
class HarnessDefinition:
    harness_id: str
    title: str
    executable: str | None
    version_arguments: tuple[str, ...]
    config_root: str | None
    source: str
    layouts: tuple[Layout, ...]
    projection_capabilities: frozenset[str]
    gaps: tuple[str, ...] = ()
    xdg_config: bool = False
    root_override: str | None = None
    npm_packages: tuple[str, ...] = ()
    scoop_app: str | None = None

    @property
    def support(self) -> HarnessSupport:
        """The declared support level, read from its owner rather than restated.

        For the five real harnesses this is the product tier owned by
        `ai_stp_foundation.harnesses`. It used to be the third positional field
        of every definition here, and the same table also existed in the
        platform catalog projection; deriving it removes the second copy
        instead of keeping two in agreement by hand.

        `undefined` is not a harness and has no product tier. It is the shared
        conventions entry, and `portable` says exactly that. Answering it here
        rather than storing it keeps the special case visible instead of hiding
        it as a third literal among five tiers.
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
) -> Layout:
    return Layout(
        component_type, relative, shape, source, scope, root, excluded, declared_key=declared_key
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

DEFINITIONS: Final[tuple[HarnessDefinition, ...]] = (
    HarnessDefinition(
        "claude-code",
        "Claude Code",
        "claude",
        ("--version",),
        ".claude",
        f"{CLAUDE}/settings",
        (
            _layout("instruction", "CLAUDE.md", "file", f"{CLAUDE}/memory", G),
            _layout("skill", "skills", "directory", f"{CLAUDE}/skills", G),
            _layout("agent", "agents", "directory", f"{CLAUDE}/sub-agents", G),
            _layout("command", "commands", "directory", f"{CLAUDE}/slash-commands", G),
            _layout("setting", "settings.json", "file", f"{CLAUDE}/settings", G),
            _layout("mcp", ".mcp.json", "file", f"{CLAUDE}/mcp", G),
            _layout("instruction", "CLAUDE.md", "file", f"{CLAUDE}/memory", P),
            # Both project placements are read by the harness, and only the
            # root one was declared. Observed directly: a Claude Code session
            # opened in a repository whose instructions live at
            # `.claude/CLAUDE.md` reports them as "project instructions,
            # checked into the codebase" — this repository is such a case, so
            # `ai-stp` was blind to its own.
            _layout("instruction", ".claude/CLAUDE.md", "file", f"{CLAUDE}/memory", P),
            _layout("skill", ".claude/skills", "directory", f"{CLAUDE}/skills", P),
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
            _layout("hook", ".codex/hooks.json", "file", f"{CODEX}/hooks", P),
        ),
        frozenset({"native_files", "plugin_manifest", "hooks_directory"}),
        root_override="CODEX_HOME",
        npm_packages=("@openai/codex",),
        state_paths=("cache", "logs", "sessions", "packages"),
    ),
    HarnessDefinition(
        "pi",
        "Pi",
        "pi",
        ("--version",),
        ".pi/agent",
        f"{PI}/environment-variables",
        (
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
        npm_packages=("@mariozechner/pi-coding-agent",),
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
            *(
                _layout("setting", f"opencode.{suffix}", "file", f"{OPENCODE}/config", scope)
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
    ),
    HarnessDefinition(
        "cursor",
        "Cursor CLI",
        "cursor-agent",
        ("--version",),
        ".cursor",
        f"{CURSOR}/cli/reference/configuration",
        (
            _layout("instruction", "AGENTS.md", "file", f"{CURSOR}/rules", G),
            _layout(
                "setting", "cli-config.json", "file", f"{CURSOR}/cli/reference/configuration", G
            ),
            # Cursor carries components inside a plugin rather than in sibling
            # directories: `.cursor-plugin/plugin.json` declares `commands`,
            # `hooks`, `mcpServers`, `agents`, `skills` and `rules` as relative
            # paths, so the plugin is the unit this harness installs.
            _layout("plugin", "plugins", "directory", f"{CURSOR}/reference/plugins", G),
            _layout("instruction", ".cursor/rules", "directory", f"{CURSOR}/rules", P),
            _layout("plugin", ".cursor/plugins", "directory", f"{CURSOR}/reference/plugins", P),
        ),
        frozenset({"native_files", "plugin_manifest"}),
        # Skills, agents, commands, hooks and MCP entries are declared by a
        # plugin manifest rather than discovered as free-standing global
        # directories, so there is no global layout to state for them.
        gaps=("components_are_plugin_declared",),
        root_override="CURSOR_CONFIG_DIR",
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
        f"{ANTIGRAVITY}/configuration",
        (
            _layout(
                "setting", "antigravity-cli/settings.json", "file", f"{ANTIGRAVITY}/settings", G
            ),
            _layout(
                "setting", "antigravity-cli/keybindings.json", "file", f"{ANTIGRAVITY}/settings", G
            ),
            _layout("plugin", "antigravity-cli/plugins", "directory", f"{ANTIGRAVITY}/plugins", G),
            _layout("plugin", "config/plugins", "directory", f"{ANTIGRAVITY}/plugins", G),
            _layout("skill", "config/skills", "directory", f"{ANTIGRAVITY}/skills", G),
            _layout("agent", "config/agents", "directory", f"{ANTIGRAVITY}/agents", G),
            _layout("hook", "config/hooks.json", "file", f"{ANTIGRAVITY}/hooks", G),
            _layout("mcp", "config/mcp_config.json", "file", f"{ANTIGRAVITY}/mcp", G),
            _layout("plugin", ".agents/plugins", "directory", f"{ANTIGRAVITY}/plugins", P),
            _layout("skill", ".agents/skills", "directory", f"{ANTIGRAVITY}/skills", P),
            _layout("agent", ".agents/agents", "directory", f"{ANTIGRAVITY}/agents", P),
            _layout("hook", ".agents/hooks.json", "file", f"{ANTIGRAVITY}/hooks", P),
            _layout("mcp", ".agents/mcp_config.json", "file", f"{ANTIGRAVITY}/mcp", P),
        ),
        frozenset({"native_files", "plugin_manifest"}),
        # The product documents instructions and commands only per project, in
        # `.agents/`, so there is nothing global to declare for either. There is
        # also no documented variable that moves the home.
        gaps=("no_global_instruction", "no_global_command", "no_documented_root_override"),
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
                "skill", ".agents/skills", "directory", f"{CODEX}/build-skills", G, root="home"
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
