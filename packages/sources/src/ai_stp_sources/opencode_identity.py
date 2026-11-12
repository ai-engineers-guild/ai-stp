"""Path identities and scanning observed in the OpenCode 2.2.7 skill reader."""

from __future__ import annotations

from collections.abc import Mapping

from ai_stp_sources.native_frontmatter import invalid, parse
from ai_stp_sources.native_markdown import captured

PROJECTION_FORMAT = "ai-stp-adaptation-projection/2"
HARNESS_VERSIONS = ["2.2.7"]
_IGNORED = {"node_modules", ".git", ".venv", "venv", "__pycache__"}


def skills(files: Mapping[str, bytes]) -> dict[str, list[str]]:
    """Observe each file's ID; display names never grant another native name."""
    local = captured(files, (".opencode/", ".agents/"), ("skills/", "skill/"))
    result: dict[str, list[str]] = {path: [] for path in files}
    for relative, (path, payload) in local.items():
        parts = relative.split("/")
        parents = parts[:-1]
        if (
            parts[-1].startswith(".")
            or len(parents) > 6
            or any(part.startswith(".") or part in _IGNORED for part in parents)
        ):
            continue
        if any("/".join([*parents[:depth], "SKILL.md"]) in local for depth in range(len(parents))):
            continue
        if parts[-1] != "SKILL.md" and (parents or not parts[-1].endswith(".md")):
            continue
        header = parse(payload, optional=True, legacy=True, empty=True)
        if any(
            field in header and not isinstance(header[field], str)
            for field in ("name", "description")
        ):
            raise invalid()
        name = parents[-1] if parents else "skills" if parts[-1] == "SKILL.md" else parts[-1][:-3]
        result[path] = [name]
    return result
