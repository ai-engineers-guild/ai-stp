"""Project the Git-owned Official inventory into PostgreSQL (SPEC-056 REQ-5601)."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.official_manifest import (
    OfficialManifest,
    OfficialManifestEntry,
    load_official_manifest,
)
from ai_stp_foundation.identity import normalize_display_key
from ai_stp_platform.identity import ensure_catalog_identity
from ai_stp_platform.models import (
    AuditEvent,
    CatalogIdentity,
    CatalogIdentityLocale,
    OfficialSyncOutbox,
    OfficialUpstreamSource,
    OfficialUpstreamSync,
)
from ai_stp_platform.official_upstream import OFFICIAL_ACCOUNT_ID, OPERATOR_DEVICE_ID
from ai_stp_platform.official_upstream.errors import (
    INVALID_SOURCE,
    MANIFEST_MISMATCH,
    OfficialUpstreamError,
)
from ai_stp_platform.official_upstream.source import SourceUpsert, upsert_source


def _empty_strings() -> list[str]:
    return []


@dataclass
class ManifestReconcileReport:
    digest: str
    added: list[str] = field(default_factory=_empty_strings)
    changed: list[str] = field(default_factory=_empty_strings)
    disabled: list[str] = field(default_factory=_empty_strings)
    removed: list[str] = field(default_factory=_empty_strings)
    preserved: list[str] = field(default_factory=_empty_strings)
    unchanged: list[str] = field(default_factory=_empty_strings)


def _entry_command(entry: OfficialManifestEntry) -> SourceUpsert:
    return SourceUpsert(
        source_id=entry.source_id,
        kind=entry.kind,
        repository_url=entry.repository_url,
        tracked_ref=entry.tracked_ref,
        component_subpath=entry.component_subpath,
        ecosystem=entry.ecosystem,
        package_name=entry.package_name,
        package_version=entry.package_version,
        package_filename=entry.package_filename,
        package_platform=entry.package_platform,
        component_type=entry.component_type,
        owner_account_id=OFFICIAL_ACCOUNT_ID,
        name=entry.display_name_en,
        upstream_project_name=entry.upstream_project_name,
        upstream_maintainer=entry.upstream_maintainer,
        reviewed_description=entry.reviewed_description,
        reviewed_license=entry.reviewed_license,
        harness_id=entry.harness_id,
        tags=entry.tags,
        target_scope=entry.target_scope,
        projection_root=entry.projection_root,
        projection_shape=entry.projection_shape,
        projection_kind=entry.projection_kind,
        actor_device_id=OPERATOR_DEVICE_ID,
        enabled=entry.enabled,
        stable_id=entry.stable_id,
        canonical_name=entry.canonical_name,
        display_name_en=entry.display_name_en,
        display_name_ru=entry.display_name_ru,
        update_policy=entry.update_policy,
    )


def _material_fields(source: OfficialUpstreamSource) -> tuple[object, ...]:
    return (
        source.kind,
        source.repository_url,
        source.tracked_ref,
        source.component_subpath,
        source.ecosystem,
        source.package_name,
        source.package_version,
        source.component_type,
        source.harness_id,
        source.target_scope,
        source.projection_root,
        source.projection_shape,
        source.projection_kind,
        source.name,
        source.upstream_project_name,
        source.upstream_maintainer,
        source.reviewed_description,
        source.reviewed_license,
        list(source.tags or []),
        source.enabled,
        source.canonical_name,
        source.display_name_en,
        source.display_name_ru,
        source.update_policy,
    )


async def reconcile_official_manifest(
    session: AsyncSession,
    *,
    manifest: OfficialManifest | None = None,
    actor_account_id: str = OFFICIAL_ACCOUNT_ID,
) -> ManifestReconcileReport:
    """Project one exact manifest revision. Undeclared production rows are rejected."""
    loaded = manifest or load_official_manifest()
    digest = loaded.digest()
    declared = {entry.source_id: entry for entry in loaded.entries}
    existing_rows = list(
        (await session.scalars(select(OfficialUpstreamSource).with_for_update())).all()
    )
    undeclared = [
        row
        for row in existing_rows
        if row.id not in declared
        and (row.inventory_state or "enabled") not in {"removed", "transferred"}
    ]
    if undeclared:
        names = ",".join(sorted(row.id for row in undeclared))
        raise OfficialUpstreamError(
            MANIFEST_MISMATCH,
            f"production Official source state does not match the Git manifest: {names}",
        )
    report = ManifestReconcileReport(digest=digest)
    for entry in loaded.entries:
        before = await session.get(OfficialUpstreamSource, entry.source_id)
        if before is not None and (before.inventory_state or "enabled") in {
            "removed",
            "transferred",
        }:
            report.preserved.append(entry.source_id)
            continue
        if before is not None:
            identity = await session.get(CatalogIdentity, before.stable_id)
            if identity is not None and identity.owner_account_id != OFFICIAL_ACCOUNT_ID:
                before.enabled = False
                before.inventory_state = "transferred"
                before.update_policy = "disabled"
                report.preserved.append(entry.source_id)
                continue
        snapshot = None if before is None else _material_fields(before)
        source = await upsert_source(session, _entry_command(entry))
        source.stable_id = entry.stable_id
        source.canonical_name = entry.canonical_name
        source.display_name_en = entry.display_name_en
        source.display_name_ru = entry.display_name_ru
        source.update_policy = entry.update_policy
        source.manifest_digest = digest
        source.enabled = entry.enabled and entry.update_policy != "disabled"
        source.inventory_state = "enabled" if source.enabled else "paused"
        identity = await ensure_catalog_identity(
            session,
            stable_id=entry.stable_id,
            owner_account_id=OFFICIAL_ACCOUNT_ID,
            canonical_name=entry.canonical_name,
            display_name_en=entry.display_name_en,
            display_name_ru=entry.display_name_ru,
        )
        identity.canonical_name = entry.canonical_name
        identity.canonical_name_normalized = entry.canonical_name
        try:
            await session.flush()
        except IntegrityError as exc:
            raise OfficialUpstreamError(
                MANIFEST_MISMATCH,
                f"manifest identity conflicts with an existing catalog line: {entry.source_id}",
            ) from exc
        locale_rows = list(
            (
                await session.scalars(
                    select(CatalogIdentityLocale).where(
                        CatalogIdentityLocale.stable_id == entry.stable_id
                    )
                )
            ).all()
        )
        by_locale = {row.locale: row for row in locale_rows}
        for locale, display_name in (("en", entry.display_name_en), ("ru", entry.display_name_ru)):
            row = by_locale.get(locale)
            if row is None:
                row = CatalogIdentityLocale(
                    stable_id=entry.stable_id,
                    locale=locale,
                    display_name=display_name,
                    display_name_normalized=normalize_display_key(display_name),
                )
                session.add(row)
            row.display_name = display_name
            row.display_name_normalized = normalize_display_key(display_name)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise OfficialUpstreamError(
                MANIFEST_MISMATCH,
                f"manifest identity conflicts with an existing catalog line: {entry.source_id}",
            ) from exc
        after = _material_fields(source)
        if snapshot is None:
            report.added.append(entry.source_id)
            action = "official_upstream.manifest_added"
        elif snapshot != after:
            report.changed.append(entry.source_id)
            action = "official_upstream.manifest_changed"
            if not source.enabled:
                report.disabled.append(entry.source_id)
        else:
            report.unchanged.append(entry.source_id)
            action = ""
        if action:
            session.add(
                AuditEvent(
                    actor_account_id=actor_account_id,
                    action=action,
                    target_table="official_upstream_source",
                    target_id=entry.source_id,
                    payload={"manifest_digest": digest, "enabled": source.enabled},
                )
            )
    for row in existing_rows:
        if row.id in declared:
            continue
        if (row.inventory_state or "enabled") in {"removed", "transferred"}:
            continue
        row.enabled = False
        row.inventory_state = "removed"
        report.removed.append(row.id)
        session.add(
            AuditEvent(
                actor_account_id=actor_account_id,
                action="official_upstream.manifest_removed",
                target_table="official_upstream_source",
                target_id=row.id,
                payload={"manifest_digest": digest},
            )
        )
    await session.flush()
    return report


async def official_status(session: AsyncSession) -> dict[str, object]:
    """Read-only operator view of the projected Official inventory."""
    manifest = load_official_manifest()
    rows = list((await session.scalars(select(OfficialUpstreamSource))).all())
    attempts = list(
        (
            await session.scalars(
                select(OfficialUpstreamSync).order_by(OfficialUpstreamSync.id.desc())
            )
        ).all()
    )
    outboxes = list((await session.scalars(select(OfficialSyncOutbox))).all())
    outbox_by_attempt = {row.attempt_id: row for row in outboxes}
    return {
        "manifest_digest": manifest.digest(),
        "manifest_entries": len(manifest.entries),
        "projected": [
            {
                "source_id": row.id,
                "stable_id": row.stable_id,
                "enabled": row.enabled,
                "inventory_state": row.inventory_state,
                "update_policy": row.update_policy,
                "canonical_name": row.canonical_name,
                "display_name_en": row.display_name_en,
                "display_name_ru": row.display_name_ru,
                "repository_url": row.repository_url,
                "tracked_ref": row.tracked_ref,
                "component_subpath": row.component_subpath,
                "manifest_digest": row.manifest_digest,
            }
            for row in rows
        ],
        "sync_attempts": [
            {
                "attempt_id": row.id,
                "source_id": row.source_id,
                "trigger_key": row.trigger_key,
                "state": row.state,
                "result": row.result,
                "attempt_count": row.attempt_count,
                "retry_at": row.retry_at.isoformat() if row.retry_at else None,
                "job_id": row.job_id,
                "outbox_state": (
                    outbox_by_attempt[row.id].state if row.id in outbox_by_attempt else None
                ),
                "manifest_digest": row.manifest_digest,
                "provenance": row.provenance,
                "error_class": row.error_class,
                "error_code": row.error_code,
                "plan_id": row.plan_id,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "cancelled_at": row.cancelled_at.isoformat() if row.cancelled_at else None,
            }
            for row in attempts
        ],
    }


def validate_checked_in_manifest() -> OfficialManifest:
    """Load and validate the repository Official inventory without database writes."""
    try:
        return load_official_manifest()
    except Exception as exc:
        raise OfficialUpstreamError(INVALID_SOURCE, str(exc)) from exc
