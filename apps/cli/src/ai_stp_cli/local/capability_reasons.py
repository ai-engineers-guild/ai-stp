"""Why a `(harness, kind)` cell is not `supported`, in a form a machine reads.

`#462` asks for `projection_missing` to carry a machine reason. These reasons
existed and were correct — in code comments beside each rule, and in a contract
test's tables. Neither is reachable by a caller, which is the whole complaint:
an agent seeing a refusal could not tell whether waiting helps, and the answer
was written down twice in places it could not look.

One table, read by the CLI that answers the question and by the contract test
that holds it to the sources. A second copy would agree until somebody edited
one.
"""

from __future__ import annotations

from typing import Final

#: Native at a scope a provider owns, and this compiler has no route. Waiting
#: helps here and nowhere else: the surface exists and the work is ours.
PROJECTION_MISSING: Final[dict[tuple[str, str], str]] = {
    ("codex", "mcp"): "`mcp_servers` is a key inside the owned `config.toml`; ADR-0129, #456",
    ("grok-build", "mcp"): "`mcp_servers` inside the owned `config.toml`; ADR-0129, #456",
    ("opencode", "mcp"): "`mcp` inside the owned `opencode.json`; ADR-0129, #456",
    ("claude-code", "hook"): (
        "hooks are a `hooks` key inside the owned `settings.json`, the same "
        "shape as codex's `mcp_servers`; ADR-0129, #460. There was no catalogue "
        "row at all, so this cell read `unsupported` — which says the product "
        "cannot do it, and `#460` is right that it can."
    ),
}

#: Routed by this compiler and absent from the catalogue at an owned scope. Each
#: is deliberate and each names what it was established from.
ROUTED_WITHOUT_A_CATALOGUE_ROW: Final[dict[tuple[str, str], str]] = {
    ("claude-code", "plugin"): (
        "plugin and skill project to the same `skills` directory and the product "
        "separates them by a manifest, not by location. Discovery is a walk with "
        "no marker test, so the catalogue row waits for a directory rule that can "
        "carry one."
    ),
    ("codex", "skill"): (
        "`user_root` — the shared-convention root, not codex's configuration home. "
        "The catalogue records `global` and `project` roots; ADR-0127."
    ),
    ("codex", "hook"): (
        "the catalogue cites `hooks.json` at project scope; the compiler owns the "
        "harness home copy the provider declares."
    ),
    ("pi", "mcp"): (
        "pi declares no `mcp` kind and says so itself. An adapter is an extension "
        "package: the passport keeps `mcp` and the provider hears `plugin`. A "
        "translation, not a claim about pi's contract; #454."
    ),
    ("grok-build", "agent"): (
        "absent from the vendor page the catalogue cites and present in the "
        "provider's own `grok-baseline` `native_discovery` — a source rather than "
        "a memory."
    ),
    ("antigravity", "instruction"): (
        "declared by the released provider `0.0.29`, read from the downloaded "
        "binary: `instruction` in `component_kinds`, `config/rules` in "
        "`native_namespaces`."
    ),
}

#: Native only where no provider writes. `unsupported` would be a lie and
#: `projection_missing` would promise work that is not ours to do.
PROJECT_SCOPE_ONLY: Final[dict[tuple[str, str], str]] = {
    ("claude-code", "mcp"): (
        "`.mcp.json` is the project file committed to a repository root; the user "
        "scope lives in `~/.claude.json`, which the provider holds in "
        "`never_touch`. There is no surface a provider can own."
    ),
}
