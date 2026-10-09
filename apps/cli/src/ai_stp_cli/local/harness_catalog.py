"""Typed Python view of the shared runtime harness catalog."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Final, Literal, cast

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

    #: Other command names the vendor installs for the same product, beside
    #: the primary. Cursor ships two — `binNames: ["agent", "cursor-agent"]`
    #: from the installer object in the pinned bundle — into one directory,
    #: and the pair is the attribution: measured on a live machine,
    #: `~/.grok/bin/agent` answers the grok banner, so an alias standing alone
    #: is another product's command that happens to share a word, never an
    #: installation of this one.
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


def _layout(raw: dict[str, Any]) -> Layout:
    values: dict[str, Any] = dict(raw)
    values["excluded_names"] = frozenset(values["excluded_names"])
    return Layout(**values)


def _definition(raw: dict[str, Any]) -> HarnessDefinition:
    values: dict[str, Any] = dict(raw)
    values["layouts"] = tuple(_layout(layout) for layout in values["layouts"])
    values["native_authoring"] = frozenset(values["native_authoring"])
    for name in ("version_arguments", "gaps", "npm_packages", "executable_aliases", "state_paths"):
        values[name] = tuple(values[name])
    return HarnessDefinition(**values)


def _definitions() -> tuple[HarnessDefinition, ...]:
    resource = files("ai_stp_foundation").joinpath("harness_catalog.json")
    document = json.loads(resource.read_text(encoding="utf-8"))
    if document["schema_version"] != 1:
        raise ValueError("unsupported bundled harness catalog")
    return tuple(_definition(item) for item in document["harnesses"])


DEFINITIONS: Final[tuple[HarnessDefinition, ...]] = _definitions()
BY_ID: Final[dict[str, HarnessDefinition]] = {item.harness_id: item for item in DEFINITIONS}
