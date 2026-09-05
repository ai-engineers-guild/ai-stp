"""Acquire a shared source snapshot and enter the shared publication flow (SPEC-056)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.harnesses import HarnessId
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.provider_surfaces import TargetScope, provider_surface
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_foundation.versioning import format_version, parse_version
from ai_stp_passports import ScopeAdaptation, build_projection, seal_adaptation
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import ComponentType, ComponentVersionPassport
from ai_stp_platform.artifact_bind import bind_plan_artifact
from ai_stp_platform.identity import IdentityError, ensure_catalog_identity
from ai_stp_platform.models import (
    CatalogIdentity,
    CatalogMetadata,
    ObjectLocation,
    OfficialUpstreamSource,
    OfficialUpstreamSync,
    PublicationPlan,
)
from ai_stp_platform.official_upstream.attribution import build_description
from ai_stp_platform.official_upstream.errors import (
    CHANGED_REPOSITORY_IDENTITY,
    FAILED_VALIDATION,
    STALE_OWNERSHIP,
    OfficialUpstreamError,
)
from ai_stp_platform.official_upstream.github import FetchFn
from ai_stp_platform.official_upstream.ledger import fence_attempt, mark_attempt
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
from ai_stp_sources.definition import source_links_for_snapshot
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
    attempt_id: int | None = None,
) -> str:
    """Return unchanged, publication_started, or raise a typed failure."""
    moment = now or datetime.now(UTC)
    source = await session.get(OfficialUpstreamSource, source_id)
    if source is None or not source.enabled:
        return "skipped"
    attempt = None
    if attempt_id is not None:
        attempt = await session.get(OfficialUpstreamSync, attempt_id)
    if attempt is None:
        attempt = await session.scalar(
            select(OfficialUpstreamSync).where(
                OfficialUpstreamSync.source_id == source.id,
                OfficialUpstreamSync.utc_day == moment.date(),
            )
        )
    cancelled = await fence_attempt(session, source, attempt)
    if cancelled is not None:
        return "skipped"
    await mark_attempt(session, attempt, "resolving")
    try:
        snapshot = await resolve_official_snapshot(source, fetch=fetch, now=moment)
    except OfficialUpstreamError as error:
        cancelled = await fence_attempt(session, source, attempt)
        if cancelled is not None:
            return "skipped"
        await _record_sync(
            session,
            source,
            moment.date(),
            "failed",
            error_code=error.code,
            attempt=attempt,
            state="retry_wait",
        )
        raise
    cancelled = await fence_attempt(session, source, attempt)
    if cancelled is not None:
        return "skipped"
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
            attempt=attempt,
            state="retry_wait",
        )
        raise error
    artifact, adaptation = _projection(source, snapshot)
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
            attempt=attempt,
            state="unchanged",
        )
        return "unchanged"
    owned_store = store
    opened = False
    if owned_store is None:
        owned_store = await open_env_object_store()
        opened = owned_store is not None
    if owned_store is None:
        error = OfficialUpstreamError(FAILED_VALIDATION, "object store is unavailable")
        await _record_sync(
            session,
            source,
            moment.date(),
            "failed",
            error_code=error.code,
            attempt=attempt,
            state="retry_wait",
        )
        raise error
    try:
        plan = await _start_publication(
            session,
            source,
            snapshot,
            artifact=artifact,
            adaptation=adaptation,
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
            attempt=attempt,
            state="retry_wait",
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
        attempt=attempt,
        state="publishing",
    )
    return "publication_started"


def _projection(
    source: OfficialUpstreamSource, snapshot: SourceSnapshot
) -> tuple[bytes, JsonValue]:
    """Materialize one operator-declared native projection without path inference."""
    target_scope = source.target_scope or ""
    projection_root = source.projection_root or ""
    projection_shape = source.projection_shape or ""
    if not projection_root or projection_shape not in {"file", "tree"}:
        raise OfficialUpstreamError(
            FAILED_VALIDATION, "official source has no supported explicit projection target"
        )
    try:
        surface = provider_surface(
            cast(HarnessId, source.harness_id), cast(TargetScope, target_scope)
        )
    except KeyError as error:
        raise OfficialUpstreamError(
            FAILED_VALIDATION, "official source harness is unsupported"
        ) from error
    ordered = sorted(snapshot.files.items())
    if not ordered and source.kind == "package":
        # Registry packages such as PyPI wheels are intentionally not unpacked
        # into a native tree. Publish one deterministic descriptor; the sealed
        # passport retains the exact registry coordinate used for installation.
        descriptor = json.dumps(
            {
                "ecosystem": source.ecosystem,
                "name": source.package_name,
                "version": source.package_version,
                "filename": source.package_filename,
                "platform": source.package_platform,
                "coordinate": snapshot.canonical_coordinate,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        ordered = [("package.json", descriptor)]
    if not ordered or (projection_shape == "file" and len(ordered) != 1):
        raise OfficialUpstreamError(FAILED_VALIDATION, "official source projection shape differs")
    source_prefix = (source.component_subpath or "").strip("/")
    projected: dict[str, bytes] = {}
    for source_path, content in ordered:
        relative = source_path.strip("/")
        if source_prefix and relative.startswith(f"{source_prefix}/"):
            relative = relative[len(source_prefix) + 1 :]
        target_path = (
            projection_root
            if projection_shape == "file"
            else f"{projection_root.rstrip('/')}/{relative}"
        )
        projected[target_path] = content
    members: list[JsonValue] = [
        {
            "path": path,
            "object_type": "file",
            "mode": 0o644,
            "content_artifact": {
                "digest": digest_bytes(ARTIFACT_DIGEST_DOMAIN, content),
                "size_bytes": len(content),
            },
            "native_ids": [],
            "content_format": "application/octet-stream",
            "parser_id": None,
            "ownership": "whole",
            "ownership_key": None,
            "write_semantics": "replace",
            "withdrawal_semantics": "remove_path",
        }
        for path, content in projected.items()
    ]
    scope_document: dict[str, JsonValue] = {
        "scope": target_scope,
        "projection_format": "ai-stp-adaptation-projection/1",
        "projection_artifact": {"digest": "sha256:" + "0" * 64, "size_bytes": 1},
        "provider_component_kind": source.component_type,
        "projection_kind": source.projection_kind,
        "required_surface": {
            "profile_id": surface.profile_id,
            "profile_digest": surface.profile_digest,
            "bundle_format": surface.bundle_format,
        },
        "permissions": {"filesystem": [], "network": [], "process": []},
        "members": members,
        "supported_harness_versions": [],
        "supported_os": [],
        "supported_arch": [],
        "technical_support": "experimental",
        "technical_support_reason": "operator-reviewed official upstream projection",
        "semantic_losses": [],
    }
    provisional = ScopeAdaptation.model_validate(scope_document)
    projection = build_projection(provisional, projected)
    scope_document["projection_artifact"] = {
        "digest": digest_bytes(ARTIFACT_DIGEST_DOMAIN, projection),
        "size_bytes": len(projection),
    }
    adaptation = seal_adaptation(
        {
            "harness_id": source.harness_id,
            "implementation_mode": "native",
            "source_artifact": None,
            "transform": None,
            "logical_component_type": cast(ComponentType, source.component_type),
            "scope_adaptations": [scope_document],
        }
    )
    return projection, cast(JsonValue, adaptation.model_dump(mode="json"))


def _store_identity(
    source: OfficialUpstreamSource, snapshot: SourceSnapshot, component_digest: str
) -> None:
    source.last_github_repo_id = snapshot.github_repo_id
    source.last_commit = snapshot.exact_identity
    source.last_canonical_coordinate = snapshot.canonical_coordinate
    source.last_archive_digest = snapshot.archive_digest
    source.last_component_digest = component_digest


async def _already_published(session: AsyncSession, stable_id: str, digest: str) -> bool:
    passports = (
        await session.scalars(
            select(CatalogMetadata.passport_document)
            .select_from(ObjectLocation)
            .join(CatalogMetadata, CatalogMetadata.id == ObjectLocation.catalog_metadata_id)
            .where(
                CatalogMetadata.stable_id == stable_id,
                CatalogMetadata.object_kind == "component",
                ObjectLocation.digest == digest,
            )
        )
    ).all()
    return any(
        isinstance(passport, dict)
        and passport.get("artifact_format") == "ai-stp-adaptation-projection/1"
        for passport in passports
    )


async def _start_publication(
    session: AsyncSession,
    source: OfficialUpstreamSource,
    snapshot: SourceSnapshot,
    *,
    artifact: bytes,
    adaptation: JsonValue,
    component_digest: str,
    store: ImmutableObjectStore,
    now: datetime,
) -> PublicationPlan:
    existing_plans = (
        await session.scalars(
            select(PublicationPlan).where(
                PublicationPlan.actor_account_id == source.owner_account_id,
                PublicationPlan.stable_id == source.stable_id,
                PublicationPlan.content_digest == component_digest,
            )
        )
    ).all()
    for existing in existing_plans:
        if existing.state not in {"failed", "cancelled", "stale", "published"}:
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
        adaptation=adaptation,
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
    # publication_plan.idempotency_key is varchar(128). Keep the stable source
    # prefix and enough digest entropy for retries without allowing long
    # manifest source ids to overflow the database column.
    digest_key = component_digest[:39]
    plan_key = f"official-upstream:{source.id}:{digest_key}"
    used_keys = {plan.idempotency_key for plan in existing_plans}
    if plan_key in used_keys:
        retry = now.strftime("%Y%m%dT%H%M%S")
        plan_key = f"{plan_key}:{retry}"
        if plan_key in used_keys:
            plan_key = f"{plan_key}{now.microsecond // 1000:03d}"
    identity = await session.get(CatalogIdentity, source.stable_id)
    display_en = source.display_name_en or source.name
    display_ru = source.display_name_ru or source.name
    try:
        identity = await ensure_catalog_identity(
            session,
            stable_id=source.stable_id,
            owner_account_id=source.owner_account_id,
            canonical_name=source.canonical_name or source.name,
            display_name_en=display_en,
            display_name_ru=display_ru,
            expected_ownership_revision_id=(
                identity.ownership_revision_id if identity is not None else None
            ),
        )
    except IdentityError as error:
        code = STALE_OWNERSHIP if "OWNERSHIP" in error.code else FAILED_VALIDATION
        raise OfficialUpstreamError(code, error.message) from error
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
        expected_ownership_revision_id=identity.ownership_revision_id,
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
    adaptation: JsonValue,
) -> dict[str, object]:
    source_links = source_links_for_snapshot(snapshot)
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
            },
            **(
                {
                    "source_links": {
                        "value": list(source_links),
                        "origin": "observed",
                        "confirmation": "none",
                        "observed_at": created_at,
                    }
                }
                if source_links
                else {}
            ),
        },
        "name": source.name,
        "description": description,
        "version": version,
        "license": {"spdx_id": license_spdx, "redistribution_allowed": True},
        "tags": list(source.tags),
        "source": _git_source_fields(source, snapshot),
        "artifact": {"digest": component_digest, "size_bytes": size_bytes},
        "artifact_format": "ai-stp-adaptation-projection/1",
        "required_env": [],
        "requires_credentials": False,
        "requires_authorization": "none",
        "permissions": {"filesystem": [], "network": [], "process": []},
        "external_endpoints": [],
        "compatibility_evidence_refs": [],
        "component_type": source.component_type,
        "origin_harness_id": source.harness_id,
        "adaptations": [adaptation],
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
    attempt: OfficialUpstreamSync | None = None,
    state: str | None = None,
) -> None:
    row = attempt
    if row is None:
        row = await session.scalar(
            select(OfficialUpstreamSync).where(
                OfficialUpstreamSync.source_id == source.id,
                OfficialUpstreamSync.utc_day == utc_day,
            )
        )
    if row is None:
        identity = await session.get(CatalogIdentity, source.stable_id)
        row = OfficialUpstreamSync(
            source_id=source.id,
            utc_day=utc_day,
            trigger_key=utc_day.isoformat(),
            result=result,
            state=state or "desired",
            expected_owner_account_id=source.owner_account_id,
            expected_ownership_revision_id=(
                identity.ownership_revision_id
                if identity is not None
                else source.ownership_revision_id
            ),
        )
        session.add(row)
    row.result = result
    row.error_code = error_code
    row.plan_id = plan_id
    row.fetched_at = datetime.now(UTC)
    if state is not None:
        row.state = state
        if state in {"unchanged", "published", "dead_lettered", "failed_permanent"}:
            row.completed_at = datetime.now(UTC)
        if state == "retry_wait":
            row.error_class = row.error_class or "retryable"
    if snapshot is not None:
        row.commit = snapshot.exact_identity
        row.archive_digest = snapshot.archive_digest
        row.observed_license = snapshot.observed_license or source.reviewed_license
        row.github_owner = snapshot.github_owner
        row.github_name = snapshot.github_name
        row.github_repo_id = snapshot.github_repo_id
        row.component_digest = component_digest
    await session.flush()
