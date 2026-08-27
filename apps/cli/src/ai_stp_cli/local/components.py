"""Finding native components, and adopting them only when asked (`#158`).

`SPEC-005` REQ-517 and REQ-518 split this in two and the split is the whole
design. **Discovery** looks in the configuration roots the harness detectors
already established and reports what is there; it opens nothing it does not have
to and writes nothing at all. **Adoption** is a separate act the user asks for,
and only then does anything reach the local registry.

Two rules that shape every function here.

A secret is never read. REQ-518 says values of secrets are not read, and the way
to honour that is to decide by *name and shape* — a file called `.env`, a key
called `apiKey` — and never to open the thing to find out. Reading it to check
whether it holds a secret is the harm the rule exists to prevent.

Adoption copies an allowlist. A passport carries the fields named in
`ADOPTED_FIELDS` and no others. Building it by removing fields from a native
configuration would have to be right about every key the harness invents next;
naming what goes in cannot leak a key nobody listed.
"""

import io
import os
import sqlite3
import stat
import zipfile
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Final

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    component_sources,
    content,
    harness_catalog,
    harnesses,
    interop_sources,
    journal,
    mcp_clients,
    mcp_sources,
    project_index,
    revisions,
)
from ai_stp_cli.local.passports import moment, owner
from ai_stp_cli.paths import redact_home
from ai_stp_foundation.canonical import JsonValue, canonize, from_json_bytes
from ai_stp_foundation.digests import digest_bytes, digest_canonical
from ai_stp_foundation.ids import new_id

#: The eight kinds, from `packages/passports`. Restated here only as a guard:
#: a detector naming something outside this set is a bug in this file, and the
#: check that catches it is at the bottom of the module.
COMPONENT_TYPES: Final[frozenset[str]] = frozenset(
    {"instruction", "skill", "mcp", "hook", "command", "agent", "plugin", "setting"}
)

#: Where a component was found. `global` is a harness's own configuration root;
#: `project` is inside a project the user named.
SCOPE_GLOBAL: Final[str] = "global"
SCOPE_PROJECT: Final[str] = "project"

#: The largest native file adoption will read. A component is something a person
#: wrote; past this it is data that happens to live in a config directory.
MAX_COMPONENT_BYTES: Final[int] = 4 * 1024 * 1024
MAX_COMPONENT_TREE_BYTES: Final[int] = 32 * 1024 * 1024
MAX_COMPONENT_FILES: Final[int] = 1000
MAX_PORTABLE_SKILL_DEPTH: Final[int] = 4
MAX_PORTABLE_SKILL_DIRECTORIES: Final[int] = 2000
PORTABLE_SKILL_SOURCE: Final[str] = "agentskills.io/specification"
PORTABLE_SKILL_EXCLUDED_NAMES: Final[frozenset[str]] = frozenset(
    {".git", ".venv", "__pycache__", "cache", "fixtures", "node_modules", "vendor"}
)
MAX_CODEX_PLUGIN_ENTRIES: Final[int] = 1000
CODEX_AGENTS_SOURCE: Final[str] = "learn.chatgpt.com/docs/agent-configuration/subagents"
CODEX_HOOKS_SOURCE: Final[str] = "learn.chatgpt.com/docs/hooks"
CODEX_PLUGIN_SOURCE: Final[str] = "learn.chatgpt.com/docs/build-plugins"
CLAUDE_PLUGIN_SOURCE: Final[str] = "code.claude.com/docs/en/plugins"
CLAUDE_MCP_SOURCE: Final[str] = "code.claude.com/docs/en/mcp"
CURSOR_PLUGIN_SOURCE: Final[str] = "cursor.com/docs/reference/plugins"
COMPONENT_FILE_FORMAT: Final[str] = "ai-stp-component-file/1"
COMPONENT_TREE_FORMAT: Final[str] = "ai-stp-component-tree/1"
COMPONENT_TREE_TIMESTAMP: Final[tuple[int, int, int, int, int, int]] = (
    1980,
    1,
    1,
    0,
    0,
    0,
)

#: Candidate identity has its own hash domain. It is stable for one declared
#: layout and redacted path, but is deliberately not the logical Component ID
#: created only by explicit adoption.
DISCOVERY_DIGEST_DOMAIN: Final[str] = "ai-stp:native-discovery:v1"


@dataclass(frozen=True)
class Rule:
    """One declared place a component of one kind lives.

    Relative to a harness configuration root, or to a project root. Declared
    rather than inferred: every harness spells these differently, and a walk
    that guessed would report a user's notes as an agent definition.
    """

    component_type: str
    relative: str

    #: `directory` — every entry inside is one component; `file` — the path
    #: itself is one; `glob` — a pattern inside the root.
    shape: str

    #: Which harness this belongs to, matching `harnesses.DETECTORS`.
    harness_id: str

    #: The documentation this layout was read from.
    source: str = ""

    #: Global rules are normally relative to the harness configuration root.
    #: Cross-harness conventions such as `$HOME/.agents/skills` use `home`.
    root: str = "config"

    #: Harness-owned service buckets inside a component directory. These are
    #: containers, not components, and must never be offered for adoption.
    excluded_names: frozenset[str] = frozenset()

    #: Native packaging selected by the target provider.  Discovery rules use
    #: native files unless a provider projection explicitly declares another
    #: package family.
    projection_kind: str = "native_files"

    #: When set, the file at `relative` is a component only if it structurally
    #: declares at least one entry under this key. Set where a kind lives
    #: inside a file that is also a setting and presence alone proves nothing.
    declared_key: str = ""


_MIGRATION_GLOBAL_ORACLE: Final[tuple[Rule, ...]] = (
    Rule("instruction", "CLAUDE.md", "file", "claude-code", "code.claude.com/docs/en/memory"),
    Rule("skill", "skills", "directory", "claude-code", "code.claude.com/docs/en/skills"),
    Rule("agent", "agents", "directory", "claude-code", "code.claude.com/docs/en/sub-agents"),
    Rule(
        "command", "commands", "directory", "claude-code", "code.claude.com/docs/en/slash-commands"
    ),
    Rule("setting", "settings.json", "file", "claude-code", "code.claude.com/docs/en/settings"),
    Rule("mcp", ".mcp.json", "file", "claude-code", "code.claude.com/docs/en/mcp"),
    Rule(
        "instruction",
        "AGENTS.md",
        "file",
        "codex",
        "learn.chatgpt.com/docs/config-file/config-reference",
    ),
    Rule(
        "command",
        "prompts",
        "directory",
        "codex",
        "learn.chatgpt.com/docs/config-file/config-reference",
    ),
    Rule(
        "setting",
        "config.toml",
        "file",
        "codex",
        "learn.chatgpt.com/docs/config-file/config-reference",
    ),
    Rule(
        "skill",
        ".agents/skills",
        "directory",
        "",
        "learn.chatgpt.com/docs/build-skills",
        "home",
    ),
    Rule("instruction", "AGENTS.md", "file", "pi", "pi.dev/docs/latest/sdk"),
    Rule("skill", "skills", "directory", "pi", "pi.dev/docs/latest/skills"),
    Rule("plugin", "extensions", "directory", "pi", "pi.dev/docs/latest/extensions"),
    Rule("command", "prompts", "directory", "pi", "pi.dev/docs/latest/prompt-templates"),
    Rule("setting", "settings.json", "file", "pi", "pi.dev/docs/latest/settings"),
    Rule("setting", "models.json", "file", "pi", "pi.dev/docs/latest/sdk"),
    Rule("skill", "skills", "directory", "opencode", "opencode.ai/docs/skills"),
    Rule("agent", "agents", "directory", "opencode", "opencode.ai/docs/agents"),
    Rule("command", "commands", "directory", "opencode", "opencode.ai/docs/commands"),
    Rule("plugin", "plugins", "directory", "opencode", "opencode.ai/docs/plugins"),
    Rule("setting", "opencode.json", "file", "opencode", "opencode.ai/docs/config"),
    Rule("setting", "opencode.jsonc", "file", "opencode", "opencode.ai/docs/config"),
    Rule(
        "skill",
        "skills",
        "directory",
        "grok-build",
        "docs.x.ai/build/features/skills-plugins-marketplaces",
    ),
    Rule(
        "plugin",
        "plugins",
        "directory",
        "grok-build",
        "docs.x.ai/build/features/skills-plugins-marketplaces",
        excluded_names=frozenset({"marketplaces"}),
    ),
    Rule(
        "hook",
        "hooks",
        "directory",
        "grok-build",
        "docs.x.ai/build/features/skills-plugins-marketplaces",
    ),
    Rule("setting", "config.toml", "file", "grok-build", "docs.x.ai/build/settings"),
    Rule(
        "mcp",
        "config.toml",
        "file",
        "codex",
        "learn.chatgpt.com/docs/config-file/config-reference",
        declared_key="mcp_servers",
    ),
    Rule("mcp", "opencode.json", "file", "opencode", "opencode.ai/docs/config", declared_key="mcp"),
    Rule(
        "mcp", "opencode.jsonc", "file", "opencode", "opencode.ai/docs/config", declared_key="mcp"
    ),
    Rule(
        "mcp",
        "config.toml",
        "file",
        "grok-build",
        "docs.x.ai/build/settings",
        declared_key="mcp_servers",
    ),
    Rule(
        "command",
        ".agents/commands",
        "directory",
        "",
        "docs.x.ai/build/features/skills-plugins-marketplaces",
        "home",
    ),
)

#: Inside a project, the same kinds live under the harness's project directory.
#: `AGENTS.md` at a project root is the cross-harness convention and belongs to
#: no single harness, which is why its `harness_id` is empty.
_MIGRATION_PROJECT_ORACLE: Final[tuple[Rule, ...]] = (
    Rule("instruction", "AGENTS.md", "file", "", "agents.md"),
    Rule("instruction", "CLAUDE.md", "file", "claude-code", "code.claude.com/docs/en/memory"),
    Rule(
        "instruction",
        ".claude/CLAUDE.md",
        "file",
        "claude-code",
        "code.claude.com/docs/en/memory",
    ),
    Rule("skill", ".claude/skills", "directory", "claude-code", "code.claude.com/docs/en/skills"),
    Rule(
        "agent", ".claude/agents", "directory", "claude-code", "code.claude.com/docs/en/sub-agents"
    ),
    Rule(
        "command",
        ".claude/commands",
        "directory",
        "claude-code",
        "code.claude.com/docs/en/slash-commands",
    ),
    Rule(
        "setting",
        ".claude/settings.json",
        "file",
        "claude-code",
        "code.claude.com/docs/en/settings",
    ),
    Rule("mcp", ".mcp.json", "file", "claude-code", "code.claude.com/docs/en/mcp"),
    Rule(
        "setting",
        ".codex/config.toml",
        "file",
        "codex",
        "learn.chatgpt.com/docs/config-file/config-basic",
    ),
    Rule("agent", ".codex/agents", "directory", "codex", CODEX_AGENTS_SOURCE),
    Rule("hook", ".codex/hooks.json", "file", "codex", CODEX_HOOKS_SOURCE),
    Rule("skill", ".agents/skills", "directory", "", "learn.chatgpt.com/docs/build-skills"),
    Rule("skill", ".pi/skills", "directory", "pi", "pi.dev/docs/latest/skills"),
    Rule("plugin", ".pi/extensions", "directory", "pi", "pi.dev/docs/latest/extensions"),
    Rule("command", ".pi/prompts", "directory", "pi", "pi.dev/docs/latest/prompt-templates"),
    Rule("setting", ".pi/settings.json", "file", "pi", "pi.dev/docs/latest/settings"),
    Rule("skill", ".opencode/skills", "directory", "opencode", "opencode.ai/docs/skills"),
    Rule("agent", ".opencode/agents", "directory", "opencode", "opencode.ai/docs/agents"),
    Rule("command", ".opencode/commands", "directory", "opencode", "opencode.ai/docs/commands"),
    Rule("plugin", ".opencode/plugins", "directory", "opencode", "opencode.ai/docs/plugins"),
    Rule("setting", "opencode.json", "file", "opencode", "opencode.ai/docs/config"),
    Rule("setting", "opencode.jsonc", "file", "opencode", "opencode.ai/docs/config"),
    Rule(
        "skill",
        ".grok/skills",
        "directory",
        "grok-build",
        "docs.x.ai/build/features/skills-plugins-marketplaces",
    ),
    Rule(
        "plugin",
        ".grok/plugins",
        "directory",
        "grok-build",
        "docs.x.ai/build/features/skills-plugins-marketplaces",
    ),
    Rule(
        "hook",
        ".grok/hooks",
        "directory",
        "grok-build",
        "docs.x.ai/build/features/skills-plugins-marketplaces",
    ),
    Rule("setting", ".grok/config.toml", "file", "grok-build", "docs.x.ai/build/settings"),
    Rule(
        "mcp",
        ".codex/config.toml",
        "file",
        "codex",
        "learn.chatgpt.com/docs/config-file/config-basic",
        declared_key="mcp_servers",
    ),
    Rule("mcp", "opencode.json", "file", "opencode", "opencode.ai/docs/config", declared_key="mcp"),
    Rule(
        "mcp", "opencode.jsonc", "file", "opencode", "opencode.ai/docs/config", declared_key="mcp"
    ),
    Rule(
        "mcp",
        ".grok/config.toml",
        "file",
        "grok-build",
        "docs.x.ai/build/settings",
        declared_key="mcp_servers",
    ),
)


def _declared_rules(scope: str) -> tuple[Rule, ...]:
    return tuple(
        Rule(
            layout.component_type,
            layout.relative,
            layout.shape,
            "" if definition.harness_id == "undefined" else definition.harness_id,
            layout.source,
            layout.root,
            layout.excluded_names,
            layout.projection_kind,
            layout.declared_key,
        )
        for definition in harness_catalog.DEFINITIONS
        for layout in definition.layouts
        if layout.scope == scope
    )


# Discovery consumes only the declarative catalog. The independent frozen
# oracle proves that centralizing the facts did not silently widen or narrow
# the already released discovery contract.
GLOBAL_RULES: Final[tuple[Rule, ...]] = _declared_rules(harness_catalog.G)
PROJECT_RULES: Final[tuple[Rule, ...]] = _declared_rules(harness_catalog.P)

#: Exactly what an adopted passport records about a native component. A
#: whitelist, because a passport built by removing keys would have to be right
#: about every key a harness invents next.
ADOPTED_FIELDS: Final[tuple[str, ...]] = (
    "component_type",
    "native_role",
    "harness_id",
    "scope",
    "source_path",
    "source_repository",
    "source_revision",
    "source_subpath",
    "source_package_name",
    "source_package_version",
    "source_digest",
    "source_name",
    "entry_points",
    "transport_capabilities",
    "evidence_refs",
    "content_format",
    "content_digest",
    "byte_length",
)


@dataclass(frozen=True)
class ComponentContent:
    """One immutable file or deterministic directory artifact."""

    payload: bytes
    format: str


@dataclass(frozen=True)
class ComponentFile:
    """One verified member expanded from a stored component artifact."""

    path: str
    content: bytes
    mode: int


@dataclass(frozen=True)
class Provenance:
    """Allowlisted origin of one candidate; never inferred from a directory name."""

    kind: str
    state: str
    repository: str | None = None
    revision: str | None = None
    subpath: str | None = None
    package_name: str | None = None
    package_version: str | None = None
    digest: str | None = None
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class Found:
    """One native component, described without its content being read."""

    component_type: str
    native_role: str | None
    harness_id: str
    scope: str

    #: Stable identity of this discovery candidate. This is not the logical
    #: Component ID, which adoption creates separately.
    candidate_id: str

    #: Official documentation that declares the layout used to find it.
    layout_source: str
    provenance: Provenance

    #: Where it is, redacted for display. `redact_home` substitutes the home
    #: prefix — it does not make a path relative, so for anything outside the
    #: home this stays absolute. Useful to show; never a passport fact.
    source_path: str
    absolute: Path

    #: Where it sits inside the layout that matched, always relative — the only
    #: form a passport may record (`SPEC-013` REQ-1313). Absolute paths are
    #: machine-specific, carry the account name, and `check_sync_payload`
    #: refuses them, so one recorded as a fact makes the component unsyncable
    #: for good: no patch schema can remove it afterwards.
    native_path: str

    #: `None` when the file was not read, which is every discovery.
    byte_length: int | None

    #: Set when the path's *name* says it holds a credential. Decided by name
    #: only — opening it to find out is the harm the rule exists to prevent.
    holds_secret: bool
    reason: str
    entry_points: tuple[str, ...]
    transport_capabilities: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Discovery:
    """Complete component listing plus safe optional-adapter diagnostics."""

    components: tuple[Found, ...]
    diagnostics: tuple[component_sources.Diagnostic, ...]


def discover(
    *,
    project: Path | None = None,
    environment: dict[str, str] | None = None,
) -> tuple[Found, ...]:
    """List native components. Writes nothing and reads no file's content.

    The configuration roots come from `harnesses.config_root`, so this and the
    harness survey cannot disagree about where a harness keeps its files. Sizes
    are read from the directory entry, not by opening anything.
    """
    return discover_report(project=project, environment=environment).components


def discover_report(
    *,
    project: Path | None = None,
    environment: dict[str, str] | None = None,
) -> Discovery:
    """List components and explain optional source-adapter failures safely."""
    found: list[Found] = []
    diagnostics: list[component_sources.Diagnostic] = []
    held = environment if environment is not None else None
    home = Path((held or {}).get("HOME", "~")).expanduser() if held is not None else Path.home()
    for rule in GLOBAL_RULES:
        if rule.root == "home":
            base = home
        else:
            detector = next(
                (item for item in harnesses.DETECTORS if item.harness_id == rule.harness_id), None
            )
            if detector is None:  # pragma: no cover - guarded by the checker
                continue
            base = harnesses.config_root(detector, environment)
        found.extend(_at(base / rule.relative, rule, SCOPE_GLOBAL))

    global_imported = interop_sources.discover_skill_lock(home)
    diagnostics.extend(global_imported.diagnostics)
    found = _merge_interop(found, global_imported.candidates, SCOPE_GLOBAL)

    claude = next(item for item in harnesses.DETECTORS if item.harness_id == "claude-code")
    sourced = component_sources.claude_plugins(harnesses.config_root(claude, environment))
    diagnostics.extend(sourced.diagnostics)
    plugin_rule = Rule(
        "plugin",
        "plugins/cache",
        "directory",
        "claude-code",
        "code.claude.com/docs/en/plugin-marketplaces",
    )
    for item in sourced.candidates:
        found.append(
            _describe(
                item.absolute,
                plugin_rule,
                SCOPE_GLOBAL,
                provenance=Provenance(
                    kind=item.kind,
                    state=item.state,
                    repository=item.repository,
                    revision=item.revision,
                    subpath=item.subpath,
                    package_name=item.package_name,
                    package_version=item.package_version,
                    evidence=item.evidence,
                ),
            )
        )

    pi = next(item for item in harnesses.DETECTORS if item.harness_id == "pi")
    pi_packages = component_sources.pi_git_packages(harnesses.config_root(pi, environment))
    diagnostics.extend(pi_packages.diagnostics)
    pi_package_rule = Rule(
        "plugin",
        "git",
        "directory",
        "pi",
        "pi.dev/docs/latest/packages",
    )
    for item in pi_packages.candidates:
        found.append(
            _describe(
                item.absolute,
                pi_package_rule,
                SCOPE_GLOBAL,
                provenance=Provenance(
                    kind=item.kind,
                    state=item.state,
                    repository=item.repository,
                    revision=item.revision,
                    subpath=item.subpath,
                    package_name=item.package_name,
                    package_version=item.package_version,
                    evidence=item.evidence,
                ),
            )
        )

    if project is not None:
        for rule in PROJECT_RULES:
            found.extend(_at(project / rule.relative, rule, SCOPE_PROJECT))
        portable, portable_diagnostics = _portable_skills(project)
        found.extend(portable)
        diagnostics.extend(portable_diagnostics)
        imported = interop_sources.discover(project)
        diagnostics.extend(imported.diagnostics)
        found = _merge_interop(found, imported.candidates, SCOPE_PROJECT)
        codex, codex_diagnostics, codex_seen = _codex_project_plugins(project)
        found.extend(codex)
        diagnostics.extend(codex_diagnostics)
        claude, claude_diagnostics, claude_seen = _claude_project_plugins(project)
        found.extend(claude)
        diagnostics.extend(claude_diagnostics)
        cursor, cursor_diagnostics, cursor_seen = _cursor_project_plugins(project)
        found.extend(cursor)
        diagnostics.extend(cursor_diagnostics)
        # Said once, and only when no harness recognised the collection. A pack
        # is a pack even when it carries no manifest for the other harness, and
        # complaining about that on every project with one would be noise. An
        # empty inventory with no reason given is still worse than a refusal, so
        # the case where nobody recognised anything keeps its diagnostic.
        if max(codex_seen, claude_seen, cursor_seen) and not codex and not claude and not cursor:
            diagnostics.append(
                component_sources.Diagnostic(
                    code="unsupported_manifest",
                    source="project-plugins",
                    reason="no directory under plugins/ carries a declared plugin manifest",
                )
            )
        mcp = mcp_sources.discover(project)
        diagnostics.extend(mcp.diagnostics)
        server_rule = Rule("mcp", ".", "directory", "", mcp_sources.MCP_SOURCE)
        for candidate in mcp.candidates:
            found.append(
                _describe(
                    candidate.root,
                    server_rule,
                    SCOPE_PROJECT,
                    native_role="mcp_server",
                    entry_points=candidate.entry_points,
                    transport_capabilities=candidate.transports,
                    evidence_refs=candidate.evidence,
                )
            )
    return Discovery(
        components=tuple(
            sorted(
                found,
                key=lambda item: (
                    item.scope,
                    item.harness_id,
                    item.component_type,
                    item.source_path,
                    item.layout_source,
                ),
            )
        ),
        diagnostics=tuple(diagnostics),
    )


def _merge_interop(
    found: list[Found], candidates: tuple[interop_sources.Candidate, ...], scope: str
) -> list[Found]:
    """Prefer manifest-backed metadata over a generic layout for one exact path."""
    merged = list(found)
    for candidate in candidates:
        merged = [
            item
            for item in merged
            if not (
                item.absolute == candidate.absolute
                and item.component_type == candidate.component_type
            )
        ]
        merged.append(
            _describe(
                candidate.absolute,
                Rule(candidate.component_type, ".", "directory", "", candidate.source),
                scope,
                provenance=Provenance(
                    kind="package",
                    state="observed",
                    package_name=candidate.package_name,
                    package_version=candidate.package_version,
                    digest=candidate.digest,
                    evidence=candidate.evidence_refs,
                ),
                evidence_refs=candidate.evidence_refs,
            )
        )
    return merged


def adopt(
    connection: sqlite3.Connection,
    item: Found,
    *,
    device_id: str,
) -> revisions.StoredRevision:
    """Register one found component, on the user's explicit say-so (`REQ-519`).

    This is the first thing here that writes. The bytes go to the content store
    and the passport records their address rather than the bytes themselves, so
    two identical components adopted from two projects are one object with two
    registrations.

    A file whose name says it holds a credential is refused rather than adopted
    with its content skipped. Adopting it would put its path and size in a
    passport that syncs, and "we stored everything about your `.env` except the
    values" is not a promise worth making.
    """
    if item.holds_secret:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this path is named as a credential file and is not adopted",
            details={"source_path": item.source_path, "reason": item.reason},
            next_actions=["component discover --json"],
        )
    if item.component_type not in COMPONENT_TYPES:  # pragma: no cover - guarded below
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"unknown component type: {item.component_type}",
            details={"source_path": item.source_path},
        )

    adopted = _read(item.absolute)
    at = moment()
    stored_bytes = content.put(connection, adopted.payload, at=at)

    stable_id = new_id("component")
    connection.execute(
        "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'component', ?)",
        (stable_id, at),
    )
    operation_id = journal.begin(connection, "component.adopt", at)
    try:
        stored = revisions.commit(
            connection,
            _passport(
                item,
                stable_id,
                adopted.format,
                stored_bytes.digest,
                len(adopted.payload),
                at,
            ),
            device_id=device_id,
            operation_id=operation_id,
        )
    except BaseException as error:
        journal.settle(connection, operation_id, "failed", moment(), type(error).__name__)
        raise
    journal.settle(connection, operation_id, "verified", moment())
    return stored


def _passport(
    item: Found,
    stable_id: str,
    content_format: str,
    digest: str,
    byte_length: int,
    at: str,
) -> dict[str, JsonValue]:
    """A passport built from the allowlist, one fact per adopted field."""
    values: dict[str, JsonValue] = {
        "component_type": item.component_type,
        "native_role": item.native_role,
        "harness_id": item.harness_id,
        "scope": item.scope,
        # The layout-relative form, never the absolute one: a passport is shared
        # and content-addressed, and `SPEC-013` REQ-1313 keeps source paths in
        # local detector state.
        "source_path": item.native_path,
        "source_repository": item.provenance.repository,
        "source_revision": item.provenance.revision,
        "source_subpath": item.provenance.subpath,
        "source_package_name": item.provenance.package_name,
        "source_package_version": item.provenance.package_version,
        "source_digest": item.provenance.digest,
        "source_name": _source_name(item),
        "entry_points": list(item.entry_points),
        "transport_capabilities": list(item.transport_capabilities),
        "evidence_refs": list(item.evidence_refs),
        "content_format": content_format,
        "content_digest": digest,
        "byte_length": byte_length,
    }
    facts: dict[str, JsonValue] = {
        name: {
            "value": values[name],
            "origin": "observed",
            "confirmation": "none",
            "observed_at": at,
        }
        for name in ADOPTED_FIELDS
    }
    return {
        "schema_version": 1,
        "kind": "component",
        "stable_id": stable_id,
        "owner_id": owner().account_id,
        "created_at": at,
        "visibility": "private",
        "parent_revision_ids": [],
        "facts": facts,
    }


def _source_name(item: Found) -> str:
    """Stable native identifier chosen from exact provenance before local paths."""
    if item.provenance.subpath:
        name = Path(item.provenance.subpath).name
        if name:
            return name
    return item.absolute.name


def _shape_of(place: Path) -> str:
    """`file`, `directory`, `unreadable` or `absent`, without ever raising.

    `Path.is_file` is not the safe check it looks like: it ignores the error of
    a path that is absent and **re-raises** the error of one the user may not
    reach — and on Python 3.12 it re-raises `PermissionError` while 3.14
    swallows it. A file inside a directory with no execute bit therefore crashed
    discovery on one supported version and not the other, which is the shape of
    failure only a second runner finds.

    `unreadable` is kept apart from `absent` because they are different answers.
    A path that is not there contributes nothing and saying so would be noise. A
    path that is there and cannot be measured is a fact the user wants: it is
    the difference between "you have no global instruction" and "I could not
    look at yours".
    """
    try:
        mode = place.stat().st_mode
    except FileNotFoundError:
        return "absent"
    except NotADirectoryError:
        # A parent in the path is a file, so nothing can exist here either.
        return "absent"
    except OSError:
        return "unreadable"
    if stat.S_ISREG(mode):
        return "file"
    return "directory" if stat.S_ISDIR(mode) else "absent"


#: Suffix chains a directory layout never offers as a component, and the file
#: names that are a directory's table of contents rather than a member of it.
#:
#: Closed and enumerated, not matched by resemblance. A rule that asked whether
#: a name "looks like a backup" would decide differently as people invent new
#: habits, and the thing it decides is whether a user's real work appears in
#: their own inventory. Adding a suffix here is a deliberate edit.
_BACKUP_SUFFIXES: Final[frozenset[str]] = frozenset({"bak", "orig"})
_LISTING_NAMES: Final[frozenset[str]] = frozenset({"index.json"})


def _is_offered(name: str) -> bool:
    """Whether a directory entry is a candidate component at all.

    `Rule.excluded_names` answers the harness-specific half — buckets a harness
    owns inside a component directory. This answers the filesystem half, which
    is the same for every harness and would otherwise be repeated in fourteen
    rules: an editor's `~`, a copy left as `.bak-<date>` beside the original,
    and a generated `index.json` listing the directory it sits in.

    Measured on a live machine before it was written: `component discover`
    reported `~/.claude/skills/ai-repo-safety.bak-20260801-103930` as a skill
    beside the real one, and `index.json` as a skill, a command and a plugin in
    three different directories (`#379`).
    """
    if name in _LISTING_NAMES or name.endswith("~"):
        return False
    return not any(
        part in _BACKUP_SUFFIXES or any(part.startswith(f"{s}-") for s in _BACKUP_SUFFIXES)
        for part in name.split(".")[1:]
    )


def _at(place: Path, rule: Rule, scope: str) -> list[Found]:
    """Whatever this rule matches at this path, described without opening it."""
    shape = _shape_of(place)
    if rule.shape == "file":
        if shape not in {"file", "unreadable"}:
            return []
        if not rule.declared_key:
            return [_describe(place, rule, scope)]
        # This path is also a setting, so its presence is not evidence. Only a
        # file that actually declares servers is a client configuration, and
        # only their names are read.
        names = mcp_clients.declared_servers(place, rule.declared_key)
        if not names:
            return []
        return [
            _describe(
                place,
                rule,
                scope,
                evidence_refs=tuple(f"{rule.declared_key}.{name}" for name in names),
            )
        ]
    if shape != "directory":
        return []
    try:
        entries = sorted(
            item
            for item in place.iterdir()
            if item.name not in rule.excluded_names and _is_offered(item.name)
        )
    except OSError:
        return []
    # A skill is a directory holding `SKILL.md`; a command is a single file.
    # Both are one component, so the entry itself is what is reported.
    return [
        _describe(entry, rule, scope)
        for entry in entries
        if _shape_of(entry) in {"file", "directory", "unreadable"}
    ]


def _portable_skills(
    project: Path,
) -> tuple[list[Found], list[component_sources.Diagnostic]]:
    """Find exact portable Skill manifests inside one explicitly named root.

    This is not a source-tree search. Only the root manifest and the bounded
    `skills/` family are eligible; links are never followed, known generated
    or vendored buckets are skipped, and a depth/directory ceiling makes the
    worst case independent of an untrusted tree's total size.
    """
    try:
        project_mode = project.lstat().st_mode
    except OSError:
        return [], []
    if stat.S_ISLNK(project_mode):
        return [], [
            component_sources.Diagnostic(
                code="invalid_record",
                source="portable-skills",
                reason="the explicit portable skill root is a link and was not traversed",
            )
        ]
    if not stat.S_ISDIR(project_mode):
        return [], []

    rule = Rule("skill", "SKILL.md", "file", "", PORTABLE_SKILL_SOURCE)
    found = _at(project / "SKILL.md", rule, SCOPE_PROJECT)
    collection = project / "skills"
    try:
        collection_mode = collection.lstat().st_mode
    except OSError:
        return found, []
    if stat.S_ISLNK(collection_mode):
        return found, [
            component_sources.Diagnostic(
                code="invalid_record",
                source="portable-skills",
                reason="the portable skills collection is a link and was not traversed",
            )
        ]
    if not stat.S_ISDIR(collection_mode):
        return found, []

    diagnostics: list[component_sources.Diagnostic] = []
    stack: list[tuple[Path, int]] = [(collection, 0)]
    visited = 0
    while stack:
        directory, depth = stack.pop()
        visited += 1
        if visited > MAX_PORTABLE_SKILL_DIRECTORIES:
            diagnostics.append(
                component_sources.Diagnostic(
                    code="bounded_limit",
                    source="portable-skills",
                    reason="the portable skill collection exceeded its bounded directory limit",
                )
            )
            break
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name, reverse=True)
        except OSError:
            continue
        for entry in entries:
            if entry.name in PORTABLE_SKILL_EXCLUDED_NAMES:
                continue
            try:
                held = entry.lstat()
            except OSError:
                continue
            if stat.S_ISLNK(held.st_mode) or not stat.S_ISDIR(held.st_mode):
                continue
            child_depth = depth + 1
            if child_depth <= MAX_PORTABLE_SKILL_DEPTH and _shape_of(entry / "SKILL.md") in {
                "file",
                "unreadable",
            }:
                found.append(_describe(entry, rule, SCOPE_PROJECT))
            if child_depth < MAX_PORTABLE_SKILL_DEPTH:
                stack.append((entry, child_depth))
    return found, diagnostics


@dataclass(frozen=True)
class _PluginSubtree:
    """One directory a manifest-backed plugin may carry, and what it holds.

    `members` means every child that carries `marker` is one component — the
    shape a skill has. An empty `marker` with `members` means every child is one
    component, which is how a plugin's `agents/` and `commands/` are laid out.
    `whole` means the directory itself is the component when `marker` is there,
    which is what a hooks bundle is. `file` means one declared file, which is
    how a plugin ships the MCP client configuration it wants registered.
    """

    component_type: str
    relative: str
    kind: str
    marker: str = ""
    source: str = ""


#: Codex and Claude Code lay their plugin packs out the same way and spell the
#: manifest differently. Kept as data rather than as two functions: the bounded
#: walk, the link refusal, the entry ceiling and the diagnostics are the part
#: that has to stay identical, and a second copy of it is a second thing to fix
#: when one of them is wrong (`#378`).
_CODEX_PLUGIN_SUBTREES: Final[tuple[_PluginSubtree, ...]] = (
    _PluginSubtree("skill", "skills", "members", "SKILL.md", CODEX_PLUGIN_SOURCE),
    _PluginSubtree("hook", "hooks", "whole", "hooks.json", CODEX_HOOKS_SOURCE),
)
_CLAUDE_PLUGIN_SUBTREES: Final[tuple[_PluginSubtree, ...]] = (
    _PluginSubtree("skill", "skills", "members", "SKILL.md", CLAUDE_PLUGIN_SOURCE),
    _PluginSubtree("agent", "agents", "members", "", CLAUDE_PLUGIN_SOURCE),
    _PluginSubtree("command", "commands", "members", "", CLAUDE_PLUGIN_SOURCE),
    _PluginSubtree("hook", "hooks", "whole", "hooks.json", CLAUDE_PLUGIN_SOURCE),
    # Where the MCP servers of a pack actually live. Measured rather than
    # assumed: on this machine eleven working servers are declared in
    # `plugins/rldyour-mcps/.mcp.json`, while `~/.claude.json`,
    # `~/.claude/settings.json` and `~/.claude/.mcp.json` carry no MCP key at
    # all — which is why `component discover` answered `mcp: 0` on a machine
    # visibly running them (`#377`).
    _PluginSubtree("mcp", ".mcp.json", "file", "", CLAUDE_MCP_SOURCE),
)
# Cursor spells the manifest `.cursor-plugin/plugin.json` and keeps rules,
# skills, agents and commands inside the plugin. Official docs also name
# `hooks` and `mcpServers`; those keys are absent from the measured OpenNetwork
# sample, and this walker does not invent files the tree does not carry.
_CURSOR_PLUGIN_SUBTREES: Final[tuple[_PluginSubtree, ...]] = (
    _PluginSubtree("skill", "skills", "members", "SKILL.md", CURSOR_PLUGIN_SOURCE),
    _PluginSubtree("agent", "agents", "members", "", CURSOR_PLUGIN_SOURCE),
    _PluginSubtree("command", "commands", "members", "", CURSOR_PLUGIN_SOURCE),
    _PluginSubtree("instruction", "rules", "members", "", CURSOR_PLUGIN_SOURCE),
)


def _claude_project_plugins(
    project: Path,
) -> tuple[list[Found], list[component_sources.Diagnostic], int]:
    """Find a Claude Code plugin pack, the way a marketplace repository ships it.

    A complete Claude setup does not have to put anything in `.claude/`. The
    canonical shape is a marketplace: `.claude-plugin/marketplace.json` beside
    `plugins/<name>/.claude-plugin/plugin.json`, with the skills, agents,
    commands and hooks inside each plugin.

    Before this, the project rules for Claude were six paths under `.claude/`
    and `CLAUDE.md`, so such a repository answered zero project-scoped
    components while the same family pack for Codex answered fifty-five
    (`#378`). An unmanifested `plugins/` directory is still not a plugin.
    """
    return _manifest_backed_plugins(
        project,
        harness_id="claude-code",
        manifest=(".claude-plugin", "plugin.json"),
        source=CLAUDE_PLUGIN_SOURCE,
        subtrees=_CLAUDE_PLUGIN_SUBTREES,
        collection="claude-plugins",
    )


def _codex_project_plugins(
    project: Path,
) -> tuple[list[Found], list[component_sources.Diagnostic], int]:
    """Find only manifest-backed plugins inside an explicit source collection."""
    found: list[Found] = []
    diagnostics: list[component_sources.Diagnostic] = []
    legacy = project / "CODEX.md"
    if _shape_of(legacy) in {"file", "unreadable"}:
        diagnostics.append(
            component_sources.Diagnostic(
                code="unsupported_manifest",
                source="codex-project-instructions",
                reason="CODEX.md is not an official Codex instruction layout; use AGENTS.md",
            )
        )
    plugins, plugin_diagnostics, directories = _manifest_backed_plugins(
        project,
        harness_id="codex",
        manifest=(".codex-plugin", "plugin.json"),
        source=CODEX_PLUGIN_SOURCE,
        subtrees=_CODEX_PLUGIN_SUBTREES,
        collection="codex-plugins",
    )
    return found + plugins, diagnostics + plugin_diagnostics, directories


def _cursor_project_plugins(
    project: Path,
) -> tuple[list[Found], list[component_sources.Diagnostic], int]:
    """Find a Cursor plugin pack by its exact manifest, the way a setup ships it.

    Cursor does not scatter skills next to `.cursor/`. The unit is
    `plugins/<name>/.cursor-plugin/plugin.json`, with rules, skills, agents
    and commands inside that plugin. The JSON is proof the directory is a
    plugin; its values are not read.
    """
    return _manifest_backed_plugins(
        project,
        harness_id="cursor",
        manifest=(".cursor-plugin", "plugin.json"),
        source=CURSOR_PLUGIN_SOURCE,
        subtrees=_CURSOR_PLUGIN_SUBTREES,
        collection="cursor-plugins",
    )


def _manifest_backed_plugins(
    project: Path,
    *,
    harness_id: str,
    manifest: tuple[str, ...],
    source: str,
    subtrees: tuple[_PluginSubtree, ...],
    collection: str,
) -> tuple[list[Found], list[component_sources.Diagnostic], int]:
    """Every manifest-backed plugin in one collection, and how many it looked at."""
    found: list[Found] = []
    diagnostics: list[component_sources.Diagnostic] = []
    root = project / "plugins"
    try:
        root_mode = root.lstat().st_mode
    except OSError:
        return found, diagnostics, 0
    if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode):
        return found, diagnostics, 0
    try:
        entries = list(islice(root.iterdir(), MAX_CODEX_PLUGIN_ENTRIES + 1))
    except OSError:
        return found, diagnostics, 0
    if len(entries) > MAX_CODEX_PLUGIN_ENTRIES:
        diagnostics.append(
            component_sources.Diagnostic(
                code="bounded_limit",
                source=collection,
                reason="the plugin collection exceeded its bounded entry limit",
            )
        )
        return found, diagnostics, 0

    plugin_rule = Rule("plugin", "plugins", "directory", harness_id, source)
    directories = 0
    for plugin in sorted(entries, key=lambda item: item.name):
        try:
            mode = plugin.lstat().st_mode
        except OSError:
            continue
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            continue
        directories += 1
        if _shape_of(plugin.joinpath(*manifest)) not in {"file", "unreadable"}:
            continue
        found.append(_describe(plugin, plugin_rule, SCOPE_PROJECT))
        for subtree in subtrees:
            held, limited = _plugin_subtree(plugin, subtree, harness_id, collection)
            found.extend(held)
            diagnostics.extend(limited)
    # `directories` is reported, not judged. Whether an unmanifested collection
    # deserves a diagnostic depends on the other harness's walk over the same
    # `plugins/`: a Codex pack is a pack even though it carries no Claude
    # manifest, and saying otherwise on every project with one would be noise
    # that trains a reader to ignore diagnostics.
    return found, diagnostics, directories


def _plugin_subtree(
    plugin: Path, subtree: _PluginSubtree, harness_id: str, collection: str
) -> tuple[list[Found], list[component_sources.Diagnostic]]:
    """What one declared directory inside a plugin contributes."""
    place = plugin / subtree.relative
    rule = Rule(subtree.component_type, subtree.relative, "directory", harness_id, subtree.source)
    try:
        mode = place.lstat().st_mode
    except OSError:
        return [], []
    if stat.S_ISLNK(mode):
        return [], []
    if subtree.kind != "file" and not stat.S_ISDIR(mode):
        return [], []
    if subtree.kind == "file":
        return ([_describe(place, rule, SCOPE_PROJECT)] if stat.S_ISREG(mode) else []), []
    if subtree.kind == "whole":
        held = (
            _shape_of(place / subtree.marker) in {"file", "unreadable"} if subtree.marker else True
        )
        return ([_describe(place, rule, SCOPE_PROJECT)] if held else []), []
    try:
        entries = list(islice(place.iterdir(), MAX_CODEX_PLUGIN_ENTRIES + 1))
    except OSError:
        return [], []
    if len(entries) > MAX_CODEX_PLUGIN_ENTRIES:
        return [], [
            component_sources.Diagnostic(
                code="bounded_limit",
                source=f"{collection}-{subtree.relative}",
                reason="a plugin subtree exceeded its bounded entry limit",
            )
        ]
    found: list[Found] = []
    for entry in sorted(entries, key=lambda item: item.name):
        if not _is_offered(entry.name):
            continue
        try:
            entry_mode = entry.lstat().st_mode
        except OSError:
            continue
        if stat.S_ISLNK(entry_mode):
            continue
        if subtree.marker:
            if stat.S_ISDIR(entry_mode) and _shape_of(entry / subtree.marker) in {
                "file",
                "unreadable",
            }:
                found.append(_describe(entry, rule, SCOPE_PROJECT))
        elif stat.S_ISREG(entry_mode):
            found.append(_describe(entry, rule, SCOPE_PROJECT))
    return found, []


def _native_path(place: Path, rule: Rule) -> str:
    """The component's place inside the layout that found it, always relative.

    The rule declares where a kind lives, so the meaningful part of an absolute
    path is the tail starting at that declaration: `.claude/CLAUDE.md`, or
    `.claude/skills/<name>` for a directory rule. That is portable, says more to
    a reader than a local absolute path, and cannot be absolute by construction.

    The fallback is the file name rather than the absolute path: if the rule
    cannot be located in the path, recording the whole thing is exactly the
    outcome this exists to prevent.
    """
    posix = place.as_posix()
    marker = "/" + rule.relative.strip("/")
    at = posix.rfind(marker)
    tail = posix[at + 1 :] if at >= 0 else place.name
    return tail.lstrip("/")


def _describe(
    place: Path,
    rule: Rule,
    scope: str,
    *,
    provenance: Provenance | None = None,
    native_role: str | None = None,
    entry_points: tuple[str, ...] = (),
    transport_capabilities: tuple[str, ...] = (),
    evidence_refs: tuple[str, ...] = (),
) -> Found:
    secret = project_index.is_secret_name(place.name)
    try:
        held = place.stat()
        size = held.st_size if stat.S_ISREG(held.st_mode) else None
        reason = (
            "found in a declared portable skill layout"
            if rule.source == PORTABLE_SKILL_SOURCE
            else (
                "found from a bounded MCP package manifest and exact entry source"
                if rule.source == mcp_sources.MCP_SOURCE
                else "found where this harness declares this kind lives"
            )
        )
    except OSError as error:
        size = None
        reason = f"listed but not measurable: {type(error).__name__}"
    if secret:
        reason = "named as a credential file; its content is never read"
    source_path = redact_home(place)
    origin = provenance or Provenance(
        kind="filesystem",
        state="local",
        evidence=(f"layout:{rule.source}",),
    )
    candidate_id = digest_canonical(
        DISCOVERY_DIGEST_DOMAIN,
        {
            "component_type": rule.component_type,
            "native_role": native_role
            or ("mcp_client_config" if rule.component_type == "mcp" else None),
            "harness_id": rule.harness_id,
            "layout_source": rule.source,
            "scope": scope,
            "source_path": source_path,
            "provenance": {
                "kind": origin.kind,
                "package_name": origin.package_name,
                "package_version": origin.package_version,
                "repository": origin.repository,
                "revision": origin.revision,
                "state": origin.state,
                "subpath": origin.subpath,
                "digest": origin.digest,
            },
            "entry_points": list(entry_points),
            "transport_capabilities": list(transport_capabilities),
            "evidence_refs": list(evidence_refs),
        },
    )
    return Found(
        component_type=rule.component_type,
        native_role=native_role or ("mcp_client_config" if rule.component_type == "mcp" else None),
        harness_id=rule.harness_id,
        scope=scope,
        candidate_id=candidate_id,
        layout_source=rule.source,
        provenance=origin,
        source_path=source_path,
        absolute=place,
        native_path=_native_path(place, rule),
        byte_length=size,
        holds_secret=secret,
        reason=reason,
        entry_points=entry_points,
        transport_capabilities=transport_capabilities,
        evidence_refs=evidence_refs,
    )


def _read(place: Path) -> ComponentContent:
    """Read one file or every safe member of one native component directory."""
    try:
        held = place.lstat()
        if stat.S_ISLNK(held.st_mode):
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "a linked component is not adopted",
                details={"source_path": redact_home(place)},
            )
        if stat.S_ISDIR(held.st_mode):
            return ComponentContent(_tree_artifact(place), COMPONENT_TREE_FORMAT)
        if not stat.S_ISREG(held.st_mode) or held.st_nlink != 1:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "a component must be one regular file or real directory",
                details={"source_path": redact_home(place)},
            )
        return ComponentContent(_read_regular(place, held), COMPONENT_FILE_FORMAT)
    except CliFailure:
        raise
    except OSError as error:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            f"the component could not be read: {type(error).__name__}",
            details={"source_path": redact_home(place)},
        ) from error


def inspect_content(place: Path) -> ComponentContent:
    """Read one candidate through the same bounded rules adoption will use."""
    return _read(place)


def _read_regular(place: Path, held: os.stat_result) -> bytes:
    if held.st_size > MAX_COMPONENT_BYTES:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the component is larger than one may be",
            details={"source_path": redact_home(place)},
        )
    descriptor = os.open(
        place,
        os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (held.st_dev, held.st_ino):
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the component changed while it was being adopted",
                details={"source_path": redact_home(place)},
            )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read(MAX_COMPONENT_BYTES + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(payload) > MAX_COMPONENT_BYTES:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the component is larger than one may be",
            details={"source_path": redact_home(place)},
        )
    return payload


def _tree_artifact(root: Path) -> bytes:
    files: list[ComponentFile] = []
    stack = [root]
    total = 0
    while stack:
        directory = stack.pop()
        for place in sorted(directory.iterdir(), key=lambda item: item.name, reverse=True):
            relative = place.relative_to(root).as_posix()
            held = place.lstat()
            if stat.S_ISLNK(held.st_mode):
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED",
                    "a component directory contains a link",
                    details={"source_path": redact_home(place)},
                )
            if stat.S_ISDIR(held.st_mode):
                stack.append(place)
                continue
            if not stat.S_ISREG(held.st_mode) or held.st_nlink != 1:
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED",
                    "a component directory contains a special or hard-linked file",
                    details={"source_path": redact_home(place)},
                )
            if any(project_index.is_secret_name(part) for part in Path(relative).parts):
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED",
                    "a component directory contains a credential-named path",
                    details={"source_path": redact_home(place)},
                )
            payload = _read_regular(place, held)
            total += len(payload)
            if total > MAX_COMPONENT_TREE_BYTES or len(files) >= MAX_COMPONENT_FILES:
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED",
                    "the component directory exceeds its bounded artifact limits",
                    details={"source_path": redact_home(root)},
                )
            mode = 0o755 if stat.S_IMODE(held.st_mode) & 0o111 else 0o644
            files.append(ComponentFile(relative, payload, mode))
    manifest_names = {
        "SKILL.md",
        "AGENTS.md",
        "plugin.json",
        ".claude-plugin/plugin.json",
        ".codex-plugin/plugin.json",
        ".cursor-plugin/plugin.json",
        "hooks.json",
        "package.json",
        "pyproject.toml",
    }
    if not any(item.path in manifest_names for item in files):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this directory holds no manifest to adopt",
            details={"source_path": redact_home(root)},
        )
    ordered = sorted(files, key=lambda item: item.path)
    manifest: dict[str, JsonValue] = {
        "format": COMPONENT_TREE_FORMAT,
        "files": [
            {
                "path": item.path,
                "digest": digest_bytes("ai-stp:artifact:v1", item.content),
                "byte_length": len(item.content),
                "mode": item.mode,
            }
            for item in ordered
        ],
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload, mode in (
            ("component.json", canonize(manifest), 0o644),
            *((f"files/{item.path}", item.content, item.mode) for item in ordered),
        ):
            info = zipfile.ZipInfo(name, date_time=COMPONENT_TREE_TIMESTAMP)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, payload)
    return output.getvalue()


def expand(payload: bytes, content_format: str) -> tuple[ComponentFile, ...]:
    """Expand only the closed component artifact formats stored at adoption."""
    if content_format == COMPONENT_FILE_FORMAT:
        return (ComponentFile("", payload, 0o644),)
    if content_format != COMPONENT_TREE_FORMAT:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the component content format is unsupported",
            details={"content_format": content_format},
        )
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or "component.json" not in names:
                raise ValueError("component artifact members are incomplete or repeated")
            total_size = 0
            for info in archive.infolist():
                mode = info.external_attr >> 16
                total_size += info.file_size
                if (
                    info.compress_type != zipfile.ZIP_STORED
                    or not stat.S_ISREG(mode)
                    or info.file_size > MAX_COMPONENT_BYTES
                    or total_size > MAX_COMPONENT_TREE_BYTES
                ):
                    raise ValueError("component artifact member metadata is unsafe")
            parsed = from_json_bytes(archive.read("component.json"))
            if not isinstance(parsed, dict) or set(parsed) != {"format", "files"}:
                raise ValueError("component artifact manifest is not closed")
            files_value = parsed.get("files")
            if parsed.get("format") != COMPONENT_TREE_FORMAT or not isinstance(files_value, list):
                raise ValueError("component artifact format differs")
            if canonize(parsed) != archive.read("component.json"):
                raise ValueError("component artifact manifest is not canonical")
            answer: list[ComponentFile] = []
            expected = {"component.json"}
            for raw in files_value:
                if not isinstance(raw, dict) or set(raw) != {
                    "path",
                    "digest",
                    "byte_length",
                    "mode",
                }:
                    raise ValueError("component artifact file entry is invalid")
                path = raw.get("path")
                if (
                    not isinstance(path, str)
                    or not path
                    or path.startswith(("/", "~"))
                    or any(part in {"", ".", ".."} for part in Path(path).parts)
                ):
                    raise ValueError("component artifact path is unsafe")
                name = f"files/{path}"
                if name in expected:
                    raise ValueError("component artifact path is repeated")
                expected.add(name)
                content_bytes = archive.read(name)
                mode_value = raw.get("mode")
                if (
                    digest_bytes("ai-stp:artifact:v1", content_bytes) != raw.get("digest")
                    or len(content_bytes) != raw.get("byte_length")
                    or not isinstance(mode_value, int)
                    or isinstance(mode_value, bool)
                    or mode_value not in {0o644, 0o755}
                ):
                    raise ValueError("component artifact member identity differs")
                answer.append(ComponentFile(path, content_bytes, mode_value))
            if set(names) != expected or len(answer) > MAX_COMPONENT_FILES:
                raise ValueError("component artifact has undeclared members")
            return tuple(answer)
    except (KeyError, ValueError, zipfile.BadZipFile) as error:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the stored component artifact is corrupt",
            details={"reason": str(error)},
        ) from error


def declared_consistently() -> tuple[str, ...]:
    """Every problem in the tables above. Empty when they are sound.

    A function rather than an import-time assertion so the gate reports all of
    them at once instead of the first. Two harnesses are checked: every rule
    names one of the eight kinds, and every rule names a harness that a detector
    actually knows how to find — a layout for a harness nothing detects would
    never be reached and nothing else would say so.
    """
    known = {item.harness_id for item in harnesses.DETECTORS}
    problems: list[str] = []
    for rule in (*GLOBAL_RULES, *PROJECT_RULES):
        if rule.component_type not in COMPONENT_TYPES:
            problems.append(f"{rule.relative}: unknown component type {rule.component_type}")
        if rule.harness_id and rule.harness_id not in known:
            problems.append(f"{rule.relative}: no detector finds harness {rule.harness_id}")
        if not rule.source:
            problems.append(f"{rule.relative}: no documentation recorded for this layout")
        if rule.root not in {"config", "home"}:
            problems.append(f"{rule.relative}: unknown global root {rule.root}")
        if rule.root == "home" and rule.harness_id:
            problems.append(f"{rule.relative}: a shared home layout names one harness")
    return tuple(problems)
