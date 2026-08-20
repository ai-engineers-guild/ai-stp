"""Versioned safety policy assets (opengrep rules, etc.)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ai_stp_platform.safety.types import ArtifactManifest

# Rule files that only apply when the artifact is an MCP component / has mcp flag.
MCP_ONLY_RULE_FILES: frozenset[str] = frozenset(
    {
        "mcp-config-security.yml",
    }
)

# CI/GitHub/GitLab packs — skip for pure skill trees without those flags.
CI_ONLY_RULE_FILES: frozenset[str] = frozenset(
    {
        "github-actions-security.yml",
        "gitlab-ci-security.yml",
    }
)


def policy_pack_root() -> Path:
    return Path(__file__).resolve().parent


def opengrep_rules_dir() -> Path:
    return policy_pack_root() / "opengrep"


def select_opengrep_rule_files(
    manifest: ArtifactManifest | None = None,
    *,
    component_type: str | None = None,
    flags: Iterable[str] | None = None,
) -> list[Path]:
    """Return vendored opengrep rule paths applicable to this artifact.

    MCP config rules are excluded for pure skills/hooks without mcp flags so
    markdown skill text does not bulk-match MCP scope patterns.
    """
    rules_dir = opengrep_rules_dir()
    if not rules_dir.is_dir():
        return []
    ctype = (component_type or (manifest.component_type if manifest else "") or "").lower()
    flag_set = set(flags or ())
    if manifest is not None:
        flag_set |= set(manifest.flags)
        if not ctype:
            ctype = (manifest.component_type or "").lower()

    include_mcp = ctype == "mcp" or "mcp" in flag_set
    include_ci = bool(flag_set & {"github_actions", "gitlab_ci", "ci"}) or ctype in {
        "hook",
        "setting",
        "plugin",
    }

    selected: list[Path] = []
    for path in sorted(rules_dir.glob("*.yml")):
        name = path.name
        if name in MCP_ONLY_RULE_FILES and not include_mcp:
            continue
        if name in CI_ONLY_RULE_FILES and not include_ci:
            continue
        selected.append(path)
    return selected
