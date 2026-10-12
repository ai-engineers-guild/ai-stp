"""Byte-derived identities for newly frozen native embedded projections."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping

from ai_stp_sources import (
    antigravity_identity,
    codex_identity,
    native_markdown,
    native_mcp,
    pi_identity,
)
from ai_stp_sources.native_frontmatter import invalid


def checked(result: dict[str, list[str]]) -> dict[str, list[str]]:
    """Require canonical invocation names and unambiguous file ownership."""
    names: set[str] = set()
    for values in result.values():
        for name in values:
            if (
                not name.strip()
                or len(name) > 512
                or unicodedata.normalize("NFC", name) != name
                or any(unicodedata.category(char) == "Cc" for char in name)
                or name in names
            ):
                raise invalid()
            names.add(name)
    if not names:
        raise invalid()
    return result


def identities(harness: str, kind: str, files: Mapping[str, bytes]) -> dict[str, list[str]]:
    """Observe supported native entry names without consulting display labels."""
    if harness == "codex" and kind == "skill":
        return codex_identity.skill_identities(files)
    if harness == "antigravity" and kind in {"skill", "agent"}:
        return checked(antigravity_identity.identities(kind, files))
    if harness == "pi" and kind in {"skill", "command"}:
        return checked(pi_identity.identities(kind, files))
    if kind == "mcp":
        return checked(native_mcp.identities(harness, files))
    if (
        (harness == "claude-code" and kind in {"skill", "command", "agent"})
        or (harness == "cursor" and kind in {"skill", "agent"})
        or (harness == "opencode" and kind in {"skill", "command", "agent"})
        or (harness == "grok-build" and kind == "skill")
    ):
        return checked(native_markdown.identities(harness, kind, files))
    return {}
