"""Operator-only official upstream source writes (SPEC-056 REQ-5601, REQ-5608)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_foundation.ids import new_id
from ai_stp_passports.markdown import validate_safe_markdown
from ai_stp_passports.versions import TAG_PATTERN
from ai_stp_platform.github_metadata import canonical_github_source
from ai_stp_platform.models import Account, AuditEvent, OfficialUpstreamSource
from ai_stp_platform.official_upstream import (
    OFFICIAL_ACCOUNT_ID,
    OPERATOR_DEVICE_ID,
    SOURCE_ID,
    SOURCE_SLOT,
)
from ai_stp_platform.official_upstream.errors import INVALID_SOURCE, OfficialUpstreamError

_TRAVERSAL = re.compile(r"(^|/)\.\.(/|$)")
_SOURCE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_COMPONENT_TYPES: frozenset[str] = frozenset(
    {"instruction", "skill", "mcp", "hook", "command", "agent", "plugin", "setting"}
)
_PACKAGE_ECOSYSTEMS: frozenset[str] = frozenset({"npm", "pypi", "crates.io", "go", "pub.dev"})
_TAG_RE = re.compile(TAG_PATTERN)


@dataclass(frozen=True)
class SourceUpsert:
    component_type: str
    owner_account_id: str
    name: str
    upstream_project_name: str
    upstream_maintainer: str
    reviewed_description: str
    reviewed_license: str
    harness_id: str
    tags: tuple[str, ...]
    source_id: str = SOURCE_ID
    kind: str = "git"
    repository_url: str = ""
    tracked_ref: str = ""
    component_subpath: str = ""
    ecosystem: str | None = None
    package_name: str | None = None
    package_version: str | None = None
    package_filename: str | None = None
    package_platform: str | None = None
    projection_kind: str = "native_files"
    actor_device_id: str | None = None
    enabled: bool = True


def _common_fields(command: SourceUpsert) -> None:
    source_id = command.source_id.strip()
    if _SOURCE_ID_RE.fullmatch(source_id) is None:
        raise OfficialUpstreamError(INVALID_SOURCE, "source id is invalid")
    if command.kind not in {"git", "package"}:
        raise OfficialUpstreamError(INVALID_SOURCE, "source kind is unknown")
    if command.component_type not in _COMPONENT_TYPES:
        raise OfficialUpstreamError(INVALID_SOURCE, "component type is unknown")
    if command.owner_account_id != OFFICIAL_ACCOUNT_ID:
        raise OfficialUpstreamError(INVALID_SOURCE, "owner must be the AI STP Official account")
    if command.harness_id not in HARNESS_IDS:
        raise OfficialUpstreamError(INVALID_SOURCE, "harness_id is unknown")
    if command.projection_kind not in {"marketplace", "plugin", "native_files", "package"}:
        raise OfficialUpstreamError(INVALID_SOURCE, "projection_kind is unknown")
    for field_name, value in (
        ("name", command.name),
        ("upstream_project_name", command.upstream_project_name),
        ("upstream_maintainer", command.upstream_maintainer),
        ("reviewed_description", command.reviewed_description),
        ("reviewed_license", command.reviewed_license),
    ):
        if not value.strip():
            raise OfficialUpstreamError(INVALID_SOURCE, f"{field_name} is required")
    if not command.tags:
        raise OfficialUpstreamError(INVALID_SOURCE, "at least one tag is required")
    for tag in command.tags:
        if _TAG_RE.fullmatch(tag) is None:
            raise OfficialUpstreamError(INVALID_SOURCE, "tag is not a vocabulary identifier")
    try:
        validate_safe_markdown(command.reviewed_description)
    except ValueError as exc:
        raise OfficialUpstreamError(
            INVALID_SOURCE, "reviewed description is not safe markdown"
        ) from exc


def validate_source(command: SourceUpsert) -> tuple[str | None, str | None]:
    """Return canonical git URL and subpath, or None for a package source."""
    _common_fields(command)
    if command.kind == "package":
        ecosystem = (command.ecosystem or "").strip()
        name = (command.package_name or "").strip()
        version = (command.package_version or "").strip()
        if ecosystem not in _PACKAGE_ECOSYSTEMS:
            raise OfficialUpstreamError(INVALID_SOURCE, "package ecosystem is unknown")
        if not name:
            raise OfficialUpstreamError(INVALID_SOURCE, "package name is required")
        if not version:
            raise OfficialUpstreamError(INVALID_SOURCE, "package version is required")
        return None, None
    repository = canonical_github_source(command.repository_url)
    if repository is None:
        raise OfficialUpstreamError(
            INVALID_SOURCE, "repository must be a public https://github.com URL"
        )
    ref = command.tracked_ref.strip()
    if not ref:
        raise OfficialUpstreamError(INVALID_SOURCE, "tracked ref is required")
    subpath = command.component_subpath.strip().replace("\\", "/")
    if not subpath or subpath.startswith("/") or _TRAVERSAL.search(subpath):
        raise OfficialUpstreamError(INVALID_SOURCE, "component subpath is empty or unsafe")
    return repository, subpath


async def upsert_source(session: AsyncSession, command: SourceUpsert) -> OfficialUpstreamSource:
    """Create or update one independently identified official source."""
    repository, subpath = validate_source(command)
    owner = await session.get(Account, command.owner_account_id)
    if owner is None:
        raise OfficialUpstreamError(INVALID_SOURCE, "official owner account is missing")
    source_id = command.source_id.strip()
    existing = await session.get(OfficialUpstreamSource, source_id)
    if existing is None:
        source = OfficialUpstreamSource(
            id=source_id,
            slot=SOURCE_SLOT if source_id == SOURCE_ID else source_id[:16],
            stable_id=new_id("component"),
            actor_device_id=command.actor_device_id or OPERATOR_DEVICE_ID,
        )
        session.add(source)
    else:
        source = existing
        if command.actor_device_id:
            source.actor_device_id = command.actor_device_id
    source.kind = command.kind
    source.repository_url = repository
    source.tracked_ref = command.tracked_ref.strip() or None
    source.component_subpath = subpath
    source.ecosystem = (command.ecosystem or "").strip() or None
    source.package_name = (command.package_name or "").strip() or None
    source.package_version = (command.package_version or "").strip() or None
    source.package_filename = (command.package_filename or "").strip() or None
    source.package_platform = (command.package_platform or "").strip() or None
    source.component_type = command.component_type
    source.projection_kind = command.projection_kind
    source.harness_id = command.harness_id
    source.owner_account_id = command.owner_account_id
    source.name = command.name.strip()
    source.upstream_project_name = command.upstream_project_name.strip()
    source.upstream_maintainer = command.upstream_maintainer.strip()
    source.reviewed_description = command.reviewed_description.strip()
    source.reviewed_license = command.reviewed_license.strip()
    source.tags = list(command.tags)
    source.enabled = command.enabled
    session.add(
        AuditEvent(
            actor_account_id=command.owner_account_id,
            action="official_upstream.source_upserted",
            target_table="official_upstream_source",
            target_id=source_id,
            payload={
                "kind": command.kind,
                "repository_url": repository,
                "tracked_ref": command.tracked_ref.strip() or None,
                "component_subpath": subpath,
                "ecosystem": source.ecosystem,
                "package_name": source.package_name,
                "enabled": command.enabled,
            },
        )
    )
    await session.flush()
    return source


async def disable_source(
    session: AsyncSession, source_id: str = SOURCE_ID
) -> OfficialUpstreamSource | None:
    source = await session.get(OfficialUpstreamSource, source_id)
    if source is None:
        return None
    source.enabled = False
    session.add(
        AuditEvent(
            actor_account_id=source.owner_account_id,
            action="official_upstream.source_disabled",
            target_table="official_upstream_source",
            target_id=source_id,
            payload={"enabled": False},
        )
    )
    await session.flush()
    return source


async def delete_source(session: AsyncSession, source_id: str = SOURCE_ID) -> bool:
    source = await session.get(OfficialUpstreamSource, source_id)
    if source is None:
        return False
    owner_id = source.owner_account_id
    await session.delete(source)
    session.add(
        AuditEvent(
            actor_account_id=owner_id,
            action="official_upstream.source_deleted",
            target_table="official_upstream_source",
            target_id=source_id,
            payload={},
        )
    )
    await session.flush()
    return True
