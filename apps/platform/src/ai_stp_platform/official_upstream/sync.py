"""Acquire a shared source snapshot and enter the shared publication flow (SPEC-056)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_foundation.versioning import format_version, parse_version
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentVersionPassport
from ai_stp_platform.artifact_bind import bind_plan_artifact
from ai_stp_platform.models import (
    CatalogMetadata,
    ObjectLocation,
    OfficialUpstreamSource,
    OfficialUpstreamSync,
    PublicationPlan,
)
from ai_stp_platform.official_upstream.artifact import package_component_tree
from ai_stp_platform.official_upstream.attribution import build_description
from ai_stp_platform.official_upstream.errors import (
    CHANGED_REPOSITORY_IDENTITY,
    FAILED_VALIDATION,
    OfficialUpstreamError,
)
from ai_stp_platform.official_upstream.github import FetchFn
from ai_stp_platform.official_upstream.resolve import resolve_official_snapshot
from ai_stp_platform.publication_logic import (
    PLAN_TTL,
    compute_plan_hash,
    validate_publication_passport,
)
from ai_stp_platform.queue.engine import enqueue
from ai_stp_platform.queue.states import JobType
from ai_stp_platform.safety.artifact_fetch import close_env_object_store, open_env_object_store
from ai_stp_platform.safety.policy import POLICY_VERSION
from ai_stp_platform.storage.object_store import ARTIFACT_DIGEST_DOMAIN, ImmutableObjectStore
from ai_stp_sources.models import SourceSnapshot

_PACKAGE_ORIGINS = {
    "npm": "https://registry.npmjs.org",
    "pypi": "https://pypi.org/project",
    "crates.io": "https://crates.io/crates",
    "go": "https://proxy.golang.org",
    "pub.dev": "https://pub.dev/packages",
}


async def run_sync(
    session: AsyncSession,
    source_id: str,
    *,
    fetch: FetchFn | None = None,
    store: ImmutableObjectStore | None = None,
    now: datetime | None = None,
) -> str:
    """Return unchanged, publication_started, or raise a typed failure."""
    moment = now or datetime.now(UTC)
    source = await session.get(OfficialUpstreamSource, source_id)
    if source is None or not source.enabled:
        return "skipped"
    try:
        snapshot = await resolve_official_snapshot(source, fetch=fetch, now=moment)
    except OfficialUpstreamError as error:
        await _record_sync(session, source, moment.date(), "failed", error_code=error.code)
        raise
    if (
        source.kind == "git"
        and source.last_github_repo_id is not None
        and snapshot.github_repo_id is not None
        and source.last_github_repo_id != snapshot.github_repo_id
    ):
        error = OfficialUpstreamError(
            CHANGED_REPOSITORY_IDENTITY, "GitHub repository identity changed"
        )
        await _record_sync(
            session,
            source,
            moment.date(),
            "failed",
            snapshot=snapshot,
            error_code=error.code,
        )
        raise error
    artifact = package_component_tree(snapshot.files)
    component_digest = digest_bytes(ARTIFACT_DIGEST_DOMAIN, artifact)
    if await _already_published(session, source.stable_id, component_digest):
        _store_identity(source, snapshot, component_digest)
        await _record_sync(
            session,
            source,
            moment.date(),
            "unchanged",
            snapshot=snapshot,
            component_digest=component_digest,
        )
        return "unchanged"
    owned_store = store
    opened = False
    if owned_store is None:
        owned_store = await open_env_object_store()
        opened = owned_store is not None
    if owned_store is None:
        error = OfficialUpstreamError(FAILED_VALIDATION, "object store is unavailable")
        await _record_sync(session, source, moment.date(), "failed", error_code=error.code)
        raise error
    try:
        plan = await _start_publication(
            session,
            source,
            snapshot,
            artifact=artifact,
            component_digest=component_digest,
            store=owned_store,
            now=moment,
        )
    except OfficialUpstreamError as error:
        await _record_sync(
            session,
            source,
            moment.date(),
            "failed",
            snapshot=snapshot,
            component_digest=component_digest,
            error_code=error.code,
        )
        raise
    finally:
        if opened:
            await close_env_object_store(owned_store)
    _store_identity(source, snapshot, component_digest)
    await _record_sync(
        session,
        source,
        moment.date(),
        "publication_started",
        snapshot=snapshot,
        component_digest=component_digest,
        plan_id=plan.id,
    )
    return "publication_started"


def _store_identity(
    source: OfficialUpstreamSource, snapshot: SourceSnapshot, component_digest: str
) -> None:
    source.last_github_repo_id = snapshot.github_repo_id
    source.last_commit = snapshot.exact_identity
    source.last_canonical_coordinate = snapshot.canonical_coordinate
    source.last_archive_digest = snapshot.archive_digest
    source.last_component_digest = component_digest


async def _already_published(session: AsyncSession, stable_id: str, digest: str) -> bool:
    found = await session.scalar(
        select(ObjectLocation.id)
        .join(CatalogMetadata, CatalogMetadata.id == ObjectLocation.catalog_metadata_id)
        .where(
            CatalogMetadata.stable_id == stable_id,
            CatalogMetadata.object_kind == "component",
            ObjectLocation.digest == digest,
        )
    )
    return found is not None


async def _start_publication(
    session: AsyncSession,
    source: OfficialUpstreamSource,
    snapshot: SourceSnapshot,
    *,
    artifact: bytes,
    component_digest: str,
    store: ImmutableObjectStore,
    now: datetime,
) -> PublicationPlan:
    existing = await session.scalar(
        select(PublicationPlan).where(
            PublicationPlan.actor_account_id == source.owner_account_id,
            PublicationPlan.idempotency_key == f"official-upstream:{source.id}:{component_digest}",
        )
    )
    if existing is not None and existing.state not in {"failed", "cancelled", "stale"}:
        return existing
    version = await _next_unused_minor(session, source.stable_id)
    license_spdx = snapshot.observed_license or source.reviewed_license
    origin = _attribution_origin(source, snapshot)
    description = build_description(
        project_name=source.upstream_project_name,
        maintainer=source.upstream_maintainer,
        repository=origin,
        license_spdx=license_spdx,
        reviewed_body=source.reviewed_description,
    )
    passport = _passport(
        source,
        snapshot,
        version=version,
        component_digest=component_digest,
        size_bytes=len(artifact),
        description=description,
        license_spdx=license_spdx,
        created_at=format_timestamp(now),
    )
    model, invalid = validate_publication_passport(
        passport,
        object_kind="component",
        stable_id=source.stable_id,
        version=version,
        content_digest=component_digest,
        owner_account_id=source.owner_account_id,
    )
    if model is None:
        raise OfficialUpstreamError(
            FAILED_VALIDATION, f"passport invalid for publication: {', '.join(invalid)}"
        )
    sealed = model.model_dump(mode="json")
    plan_key = f"official-upstream:{source.id}:{component_digest}"
    if existing is not None:
        plan_key = f"{plan_key}:{now.date().isoformat()}"
    plan_hash = compute_plan_hash(
        actor_account_id=source.owner_account_id,
        device_id=source.actor_device_id,
        object_kind="component",
        stable_id=source.stable_id,
        version=version,
        content_digest=component_digest,
        policy_version=POLICY_VERSION,
        passport=sealed,
        attestations=[],
    )
    plan = PublicationPlan(
        id=new_id("plan"),
        actor_account_id=source.owner_account_id,
        device_id=source.actor_device_id,
        object_kind="component",
        stable_id=source.stable_id,
        version=version,
        content_digest=component_digest,
        policy_version=POLICY_VERSION,
        plan_hash=plan_hash,
        state="validating",
        passport=sealed,
        attestations=[],
        effects=["validate", "publish_catalog_version"],
        idempotency_key=plan_key,
        expires_at=now + PLAN_TTL,
    )
    session.add(plan)
    await session.flush()
    await bind_plan_artifact(
        store=store,
        payload=artifact,
        expected_digest=component_digest,
        expected_size=len(artifact),
    )
    await enqueue(
        session,
        job_type=JobType.VALIDATE,
        payload={"plan_id": plan.id},
        idempotency_key=f"validate:{plan.id}",
    )
    return plan


async def _next_unused_minor(session: AsyncSession, stable_id: str) -> str:
    catalog = list(
        (
            await session.scalars(
                select(CatalogMetadata.version).where(
                    CatalogMetadata.stable_id == stable_id,
                    CatalogMetadata.object_kind == "component",
                )
            )
        ).all()
    )
    plans = list(
        (
            await session.scalars(
                select(PublicationPlan.version).where(
                    PublicationPlan.stable_id == stable_id,
                    PublicationPlan.object_kind == "component",
                    PublicationPlan.state.notin_(("failed", "cancelled", "stale")),
                )
            )
        ).all()
    )
    return next_unused_minor([item for item in (*catalog, *plans) if item])


def next_unused_minor(versions: Sequence[str]) -> str:
    parsed = [parse_version(item) for item in versions]
    if not parsed:
        return "1.0"
    major = max(item[0] for item in parsed)
    minor = max(item[1] for item in parsed if item[0] == major)
    return format_version(major, minor + 1)


def _attribution_origin(source: OfficialUpstreamSource, snapshot: SourceSnapshot) -> str:
    if source.kind == "git" and source.repository_url:
        return source.repository_url
    return snapshot.canonical_coordinate


def _git_source_fields(source: OfficialUpstreamSource, snapshot: SourceSnapshot) -> dict[str, str]:
    if snapshot.kind == "git" and snapshot.repository_url and snapshot.subpath:
        return {
            "repository": snapshot.repository_url,
            "commit": snapshot.exact_identity,
            "path": snapshot.subpath,
        }
    origin = _PACKAGE_ORIGINS.get(source.ecosystem or "", "https://registry.npmjs.org")
    name = source.package_name or "package"
    commit = hashlib.sha256(snapshot.canonical_coordinate.encode("utf-8")).hexdigest()[:40]
    return {
        "repository": f"{origin}/{name}",
        "commit": commit,
        "path": source.package_filename or name.replace("@", ""),
    }


def _passport(
    source: OfficialUpstreamSource,
    snapshot: SourceSnapshot,
    *,
    version: str,
    component_digest: str,
    size_bytes: int,
    description: str,
    license_spdx: str,
    created_at: str,
) -> dict[str, object]:
    passport: dict[str, object] = {
        "schema_version": 1,
        "kind": "component",
        "stable_id": source.stable_id,
        "revision_id": "revision_" + "0" * 64,
        "parent_revision_ids": [],
        "owner_id": source.owner_account_id,
        "created_at": created_at,
        "visibility": "public",
        "facts": {
            "upstream_source": {
                "value": snapshot.canonical_coordinate,
                "origin": "observed",
                "confirmation": "none",
                "observed_at": created_at,
            }
        },
        "name": source.name,
        "description": description,
        "version": version,
        "license": {"spdx_id": license_spdx, "redistribution_allowed": True},
        "tags": list(source.tags),
        "source": _git_source_fields(source, snapshot),
        "artifact": {"digest": component_digest, "size_bytes": size_bytes},
        "harness_id": source.harness_id,
        "harness_ids": [],
        "supported_os": [],
        "required_env": [],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "compatibility_evidence_refs": [],
        "component_type": source.component_type,
        "projection_kind": source.projection_kind,
        "variant_id": None,
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
        "managed_paths": [],
        "native_ids": [],
    }
    passport["revision_id"] = derive_revision_id(cast(Any, passport))
    sealed = cast(
        dict[str, object], ComponentVersionPassport.model_validate(passport).model_dump(mode="json")
    )
    sealed["revision_id"] = derive_revision_id(cast(Any, sealed))
    return sealed


async def _record_sync(
    session: AsyncSession,
    source: OfficialUpstreamSource,
    utc_day: date,
    result: str,
    *,
    snapshot: SourceSnapshot | None = None,
    component_digest: str | None = None,
    plan_id: str | None = None,
    error_code: str | None = None,
) -> None:
    row = await session.scalar(
        select(OfficialUpstreamSync).where(
            OfficialUpstreamSync.source_id == source.id,
            OfficialUpstreamSync.utc_day == utc_day,
        )
    )
    if row is None:
        row = OfficialUpstreamSync(source_id=source.id, utc_day=utc_day, result=result)
        session.add(row)
    row.result = result
    row.error_code = error_code
    row.plan_id = plan_id
    row.fetched_at = datetime.now(UTC)
    if snapshot is not None:
        row.commit = snapshot.exact_identity
        row.archive_digest = snapshot.archive_digest
        row.observed_license = snapshot.observed_license or source.reviewed_license
        row.github_owner = snapshot.github_owner
        row.github_name = snapshot.github_name
        row.github_repo_id = snapshot.github_repo_id
        row.component_digest = component_digest
    await session.flush()
