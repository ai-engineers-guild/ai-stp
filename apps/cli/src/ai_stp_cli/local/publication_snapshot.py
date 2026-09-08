"""Seal a component passport to the exact directory bytes being published."""

from __future__ import annotations

from typing import cast

from ai_stp_cli.local import components
from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentVersionPassport


def bind(
    passport: ComponentVersionPassport,
    *,
    visibility: str,
    digest: str,
    size_bytes: int,
) -> ComponentVersionPassport:
    """Bind unpublished artifact bytes without rewriting sealed identity.

    `visibility` is the requested distribution for the publication plan. ADR-0169
    keeps that field off the passport: opening or closing access uses a separate
    owner plan and must not mint a new `revision_id`.
    """
    if visibility not in {"public", "private"}:
        raise ValueError("visibility must be public or private")
    if passport.artifact.digest == digest and passport.artifact.size_bytes == size_bytes:
        return passport
    document = cast(dict[str, object], passport.model_dump(mode="json"))
    document["artifact"] = {"digest": digest, "size_bytes": size_bytes}
    document["artifact_format"] = components.COMPONENT_TREE_FORMAT
    document["revision_id"] = derive_revision_id(cast(dict[str, JsonValue], document))
    return ComponentVersionPassport.model_validate(document)
