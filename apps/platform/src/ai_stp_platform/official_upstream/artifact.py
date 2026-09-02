"""Deterministic component-tree zip for an official upstream snapshot."""

from __future__ import annotations

import io
import stat
import zipfile
from collections.abc import Mapping

from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN

COMPONENT_TREE_FORMAT = "ai-stp-component-tree/1"
_COMPONENT_TREE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def package_component_tree(files: Mapping[str, bytes]) -> bytes:
    """Pack component-root files into the closed component-tree zip."""
    ordered = sorted((path.replace("\\", "/"), content) for path, content in files.items())
    manifest: dict[str, JsonValue] = {
        "format": COMPONENT_TREE_FORMAT,
        "files": [
            {
                "path": path,
                "digest": digest_bytes(ARTIFACT_DIGEST_DOMAIN, content),
                "byte_length": len(content),
                "mode": 0o644,
            }
            for path, content in ordered
        ],
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        members: list[tuple[str, bytes]] = [("component.json", canonize(manifest))]
        members.extend((f"files/{path}", content) for path, content in ordered)
        for name, payload in members:
            info = zipfile.ZipInfo(name, date_time=_COMPONENT_TREE_TIMESTAMP)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payload)
    return output.getvalue()
