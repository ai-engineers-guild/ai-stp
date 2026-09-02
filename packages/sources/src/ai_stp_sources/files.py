"""Digest of selected component-root files."""

from __future__ import annotations

from collections.abc import Mapping

from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes

ARTIFACT_DIGEST_DOMAIN = "ai-stp:artifact:v1"


def files_digest(files: Mapping[str, bytes]) -> str:
    """Digest path-ordered file digests; never includes local absolute paths."""
    ordered = sorted((path.replace("\\", "/"), content) for path, content in files.items())
    manifest: JsonValue = {
        "files": [
            {
                "path": path,
                "digest": digest_bytes(ARTIFACT_DIGEST_DOMAIN, content),
                "byte_length": len(content),
            }
            for path, content in ordered
        ]
    }
    return digest_bytes(ARTIFACT_DIGEST_DOMAIN, canonize(manifest))
