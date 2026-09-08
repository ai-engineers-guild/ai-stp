"""Publish the sealed version's bytes without changing its immutable identity."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import components, content
from ai_stp_passports.versions import ComponentVersionPassport


def bind(
    passport: ComponentVersionPassport,
    *,
    visibility: str,
    digest: str,
    size_bytes: int,
) -> ComponentVersionPassport:
    """Check publication identity; distribution visibility never reseals X.Y."""
    if visibility not in {"public", "private"}:
        raise ValueError("visibility must be public or private")
    if passport.artifact.digest != digest or passport.artifact.size_bytes != size_bytes:
        raise CliFailure(
            "AI_STP_PLAN_STALE",
            "publication bytes differ from the released component; "
            "release the changed content first",
            details={"id": passport.stable_id, "version": passport.version},
            next_actions=[f"component version release --id {passport.stable_id} --json"],
        )
    return passport


def prepared_bytes(
    connection: sqlite3.Connection,
    passport: ComponentVersionPassport,
    *,
    root: Path | None = None,
) -> tuple[bytes, tuple[str, ...]]:
    """Read the immutable artifact and optionally compare a supplied source tree."""
    payload = content.get(connection, passport.artifact.digest)
    bind(
        passport,
        visibility=passport.visibility,
        digest=content.address_of(payload),
        size_bytes=len(payload),
    )
    content_format = str(passport.model_dump().get("artifact_format") or "")
    files = components.expand(payload, content_format)
    inventory = tuple(sorted(item.path for item in files if item.path))
    if root is not None:
        selected, _inventory = components.package_publication_root(root)
        selected_files = components.expand(selected, components.COMPONENT_TREE_FORMAT)
        if content_format == components.COMPONENT_FILE_FORMAT:
            matches = len(selected_files) == 1 and selected_files[0].content == payload
            inventory = tuple(item.path for item in selected_files)
        else:
            matches = sorted(files, key=lambda item: item.path) == sorted(
                selected_files, key=lambda item: item.path
            )
        if not matches:
            raise CliFailure(
                "AI_STP_PLAN_STALE",
                "the selected directory differs from the released artifact; publish the sealed "
                "version without a source root or release the changed content first",
                details={"id": passport.stable_id, "version": passport.version},
                next_actions=[f"component version release --id {passport.stable_id} --json"],
            )
    return payload, inventory
