"""Byte-derived local Codex skill identities over exact captured files."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from yaml.nodes import MappingNode

from ai_stp_sources.native_frontmatter import (
    fields as _fields,
)
from ai_stp_sources.native_frontmatter import (
    header as _header,
)
from ai_stp_sources.native_frontmatter import (
    invalid as _invalid,
)
from ai_stp_sources.native_frontmatter import (
    lexical_string as _string,
)

_SPACE = re.compile(
    r"[\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+"
)
_PLUGIN_DIRECTORIES = (".codex-plugin", ".claude-plugin", ".cursor-plugin")


def skill_identities(files: Mapping[str, bytes]) -> dict[str, list[str]]:
    """Return IDs on visible SKILL.md members, rejecting collisions and plugins."""
    captured: dict[str, tuple[str, bytes]] = {}
    for path, payload in files.items():
        local = (
            path.removeprefix(".codex/")
            if path.startswith(".codex/")
            else path.removeprefix(".agents/")
        )
        if not local.startswith("skills/") or local in captured:
            raise _invalid()
        captured[local] = (path, payload)
    result: dict[str, list[str]] = {path: [] for path in files}
    names: set[str] = set()
    for local, (path, payload) in captured.items():
        parts = local.removeprefix("skills/").split("/")
        if parts[-1] != "SKILL.md" or len(parts) > 7 or any(part.startswith(".") for part in parts):
            continue
        ancestor = local.rsplit("/", 1)[0]
        while True:
            prefix = ancestor + "/" if ancestor else ""
            if any(
                prefix + directory + "/plugin.json" in captured for directory in _PLUGIN_DIRECTORIES
            ):
                raise _invalid()
            if not ancestor:
                break
            ancestor = ancestor.rsplit("/", 1)[0] if "/" in ancestor else ""
        fields = _fields(_header(payload))
        metadata = fields.get("metadata")
        if metadata is not None:
            if not isinstance(metadata, MappingNode):
                raise _invalid()
            _string(_fields(metadata).get("short-description"))
        description = _string(fields.get("description"))
        if description is None or not _SPACE.sub(" ", description).strip(" "):
            raise _invalid()
        declared = _string(fields.get("name"))
        name = _SPACE.sub(" ", declared or "").strip(" ") or _SPACE.sub(
            " ", parts[-2] if len(parts) > 1 else "skills"
        ).strip(" ")
        if (
            not name
            or len(name) > 64
            or unicodedata.normalize("NFC", name) != name
            or any(unicodedata.category(char) == "Cc" for char in name)
            or name in names
        ):
            raise _invalid()
        names.add(name)
        result[path] = [name]
    if not names:
        raise _invalid()
    return result
