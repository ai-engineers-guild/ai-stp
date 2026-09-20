"""Publication fixtures shared by the API and CLI boundary tests.

Real content digests, not canned strings: the safety validate leg re-hashes
the bound bytes, so the artifact bodies, their digests, and the passport
builder all live here as the single source.
"""

from __future__ import annotations

import io
import zipfile
from typing import cast

from tests.support.component_passports import adaptation_fields

from ai_stp_foundation.digests import digest_bytes
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN


def skill_zip(body: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("SKILL.md", body)
    return buf.getvalue()


CLEAN_ARTIFACT = skill_zip("# demo-skill\n\nClean publication fixture.\n")
CLEAN_ARTIFACT_B = skill_zip("# demo-skill-b\n\nSecond publication fixture.\n")
DIGEST = digest_bytes(ARTIFACT_DIGEST_DOMAIN, CLEAN_ARTIFACT)
DIGEST2 = digest_bytes(ARTIFACT_DIGEST_DOMAIN, CLEAN_ARTIFACT_B)
ARTIFACT_BY_DIGEST = {
    DIGEST: CLEAN_ARTIFACT,
    DIGEST2: CLEAN_ARTIFACT_B,
}
PROJECTION_ARTIFACT = b"codex projection bytes"
PROJECTION_DIGEST = digest_bytes(ARTIFACT_DIGEST_DOMAIN, PROJECTION_ARTIFACT)


def publication_passport(
    *,
    owner_id: str,
    version: str = "1.0",
    digest: str = DIGEST,
    requires_credentials: bool = False,
    extra_projection: bool = False,
) -> dict[str, object]:
    payload = ARTIFACT_BY_DIGEST.get(digest, CLEAN_ARTIFACT)
    passport: dict[str, object] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        "revision_id": "revision_" + "0" * 64,
        "parent_revision_ids": [],
        "owner_id": owner_id,
        "created_at": "2026-08-10T00:00:00.000Z",
        "visibility": "public",
        "facts": {},
        "name": "demo-skill",
        "description": "Demo publication component.",
        "version": version,
        "tags": ["review"],
        "license": {"spdx_id": "MIT", "redistribution_allowed": True},
        "source": {
            "repository": "https://github.com/example/demo",
            "commit": "a" * 40,
            "path": "skills/demo",
        },
        "artifact": {"digest": digest, "size_bytes": len(payload)},
        "requires_credentials": requires_credentials,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "compatibility_evidence_refs": [],
        **adaptation_fields(digest=digest, size=len(payload)),
        "required_env": [],
        "component_type": "skill",
        "provides_capabilities": [],
        "requires_components": [],
        "requires_capabilities": [],
        "conflicts": {
            "paths": [],
            "commands": [],
            "hooks": [],
            "mcp": [],
            "agents": [],
            "plugins": [],
        },
    }
    if extra_projection:
        adaptations = cast(list[object], passport["adaptations"])
        extra = adaptation_fields(
            digest=PROJECTION_DIGEST,
            size=len(PROJECTION_ARTIFACT),
            harness_id="codex",
        )["adaptations"]
        passport["adaptations"] = [*adaptations, *cast(list[object], extra)]
    passport["revision_id"] = derive_revision_id(passport)  # type: ignore[arg-type]
    return passport
