"""Immutable detector snapshots refresh facts, never owner decisions or project links."""

from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import authorize, authorize_idempotent
from ai_stp_api.slices.technology.service import (
    finish_mutation,
    mutation_effect,
)
from ai_stp_contracts.technology import (
    TechnologyMappingEntry,
    TechnologyMappingRequest,
    TechnologyMappingView,
    TechnologyObservation,
    TechnologyScanRequest,
    TechnologyScanResult,
    TechnologyScanView,
    TechnologyUnmappedEntry,
    TechnologyUnmappedView,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_platform.organization_models import CorporateProject, ProjectIdentity
from ai_stp_platform.technology_models import (
    Technology,
    TechnologyCoordinateMapping,
    TechnologyScan,
    TechnologyUnmappedCoordinate,
)
from ai_stp_platform.technology_scan_merge import merge_scan_facts


def _mapping_view(
    organization_id: str, version: str, entries: list[TechnologyMappingEntry]
) -> TechnologyMappingView:
    ordered = sorted(entries, key=lambda entry: (entry.kind, entry.coordinate, entry.technology_id))
    snapshot = {
        "kind": "technology_mapping",
        "organization_id": organization_id,
        "version": version,
        "entries": [entry.model_dump(mode="json") for entry in ordered],
    }
    return TechnologyMappingView(
        organization_id=organization_id,
        version=version,
        entries=ordered,
        digest=digest_canonical("ai-stp:plan:v1", cast(JsonValue, snapshot)),
    )


async def _mapped_entries(
    db: AsyncSession, organization_id: str, version: str
) -> list[TechnologyMappingEntry]:
    rows = await db.scalars(
        select(TechnologyCoordinateMapping).where(
            TechnologyCoordinateMapping.organization_id == organization_id,
            TechnologyCoordinateMapping.version == version,
        )
    )
    return [
        TechnologyMappingEntry.model_validate(
            {
                "kind": row.kind,
                "coordinate": row.coordinate,
                "technology_id": row.technology_id,
                "provenance": row.provenance,
            }
        )
        for row in rows
    ]


async def _technology_authority(
    db: AsyncSession,
    ctx: AuthContext,
    organization_id: str,
    technology_id: str,
    *,
    update: bool = False,
) -> str:
    # Redirect traversal checks every original/current endpoint, including historical mappings.
    seen: set[str] = set()
    current = technology_id
    while current not in seen:
        seen.add(current)
        for permission in (
            ("technology.read", "technology.update") if update else ("technology.read",)
        ):
            await authorize(
                db,
                ctx=ctx,
                organization_id=organization_id,
                permission=permission,
                scope_kind="technology",
                scope_id=current,
            )
        row = await db.get(Technology, (organization_id, current))
        if row is None:
            raise ApiError(ErrorCategory.PERMISSION, "technology endpoint is unavailable")
        if row.redirect_id is None:
            return current
        current = row.redirect_id
    raise ApiError(ErrorCategory.CONFLICT, "technology redirect cycle")


async def read_mapping(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    version: str,
    request_id: str | None,
) -> TechnologyMappingView:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="technology.list")
    entries = await _mapped_entries(db, organization_id, version)
    if not entries:
        raise ApiError(ErrorCategory.PERMISSION, "mapping snapshot is unavailable")
    for entry in entries:
        await _technology_authority(db, ctx, organization_id, entry.technology_id)
    response = _mapping_view(organization_id, version, entries)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="technology.mapping.read",
        target_table="technology_coordinate_mapping",
        target_id=version,
        request_id=request_id,
    )
    return response


async def publish_mapping(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    version: str,
    payload: TechnologyMappingRequest,
    request_id: str | None,
) -> TechnologyMappingView:
    operation = "technology.mapping.publish"
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="technology.update",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=mutation_effect(payload, version),
        request_id=request_id,
    )
    for entry in payload.entries:
        await _technology_authority(db, ctx, organization_id, entry.technology_id, update=True)
    if receipt is not None:
        return TechnologyMappingView.model_validate(receipt.response_body)
    response = _mapping_view(organization_id, version, payload.entries)
    existing = await _mapped_entries(db, organization_id, version)
    before = _mapping_view(organization_id, version, existing) if existing else None
    if before is not None and before.digest != response.digest:
        raise ApiError(ErrorCategory.CONFLICT, "mapping version is immutable")
    if before is None:
        for entry in response.entries:
            db.add(
                TechnologyCoordinateMapping(
                    organization_id=organization_id,
                    version=version,
                    **entry.model_dump(),
                )
            )
        organization.policy_revision += 1
        await db.flush()
    await finish_mutation(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        target=version,
        response=response,
        before=before.model_dump(mode="json") if before else None,
        request_id=request_id,
        target_table="technology_coordinate_mapping",
        reason="immutable_mapping_snapshot",
        source="detector",
    )
    return response


async def _pair_authority(
    db: AsyncSession,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    action: str,
) -> None:
    for permission in ("project.read", "project_technology.read", f"project_technology.{action}"):
        await authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission=permission,
            scope_kind="project",
            scope_id=project_id,
        )


async def publish_scan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    payload: TechnologyScanRequest,
    request_id: str | None,
) -> TechnologyScanResult:
    operation = "technology.scan.publish"
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=operation,
        scope_kind="project",
        scope_id=project_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=mutation_effect(payload, project_id),
        request_id=request_id,
    )
    handoff = payload.handoff
    if handoff.organization_id != organization_id or handoff.project_id != project_id:
        raise ApiError(ErrorCategory.PERMISSION, "scan publication identity does not match")
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.read",
        scope_kind="project",
        scope_id=project_id,
    )
    observations: dict[tuple[str, str], TechnologyObservation] = {}
    for observation in handoff.observations:
        current = await _technology_authority(db, ctx, organization_id, observation.technology_id)
        key = (current, observation.fact.context)
        if key in observations:
            raise ApiError(ErrorCategory.VALIDATION, "scan technology/context is ambiguous")
        if not observation.fact.evidence or any(
            entry.source == "manual"
            or entry.detector_version != handoff.detector_version
            or entry.mapping_version != handoff.mapping_version
            for entry in observation.fact.evidence
        ):
            raise ApiError(
                ErrorCategory.VALIDATION, "scan evidence must name its detector and mapping"
            )
        observations[key] = TechnologyObservation(technology_id=current, fact=observation.fact)
        if observation.fact.version_kind == "observed_version" and not any(
            entry.source == "observed" for entry in observation.fact.evidence
        ):
            raise ApiError(
                ErrorCategory.VALIDATION, "observed versions require observation evidence"
            )
    if receipt is not None:
        response = TechnologyScanResult.model_validate(receipt.response_body)
        for usage in response.usages:
            await _technology_authority(db, ctx, organization_id, usage.technology_id)
            await _pair_authority(
                db,
                ctx,
                organization_id,
                project_id,
                "create" if usage.relation_id in response.created_relation_ids else "update",
            )
        return response
    mappings = await _mapped_entries(db, organization_id, handoff.mapping_version)
    if not mappings:
        raise ApiError(ErrorCategory.PERMISSION, "scan mapping snapshot is unavailable")
    mapped_ids = {
        await _technology_authority(db, ctx, organization_id, entry.technology_id)
        for entry in mappings
    }
    if any(key[0] not in mapped_ids for key in observations):
        raise ApiError(ErrorCategory.VALIDATION, "observation is outside its mapping snapshot")
    digest = mutation_effect(payload, project_id)
    retained = await db.get(TechnologyScan, (organization_id, handoff.scan_id))
    if retained is not None:
        if retained.project_id != project_id or retained.fingerprint != digest:
            raise ApiError(ErrorCategory.CONFLICT, "scan ID is immutable")
        response = TechnologyScanResult.model_validate(retained.handoff["result"])
        for usage in response.usages:
            await _technology_authority(db, ctx, organization_id, usage.technology_id)
            await _pair_authority(
                db,
                ctx,
                organization_id,
                project_id,
                "create" if usage.relation_id in response.created_relation_ids else "update",
            )
        await finish_mutation(
            db,
            ctx=ctx,
            organization_id=organization_id,
            payload=payload,
            operation=operation,
            target=project_id,
            response=response,
            before=None,
            request_id=request_id,
            target_table="technology_scan",
            audit_target=handoff.scan_id,
            reason="scan_replay",
            source="detector",
        )
        return response
    project = await db.scalar(
        select(CorporateProject).where(
            CorporateProject.organization_id == organization_id,
            CorporateProject.id == project_id,
            CorporateProject.lifecycle == "active",
        )
    )
    identity = await db.get(ProjectIdentity, project_id)
    if (
        project is None
        or identity is None
        or identity.organization_id != organization_id
        or identity.state != "active"
    ):
        raise ApiError(ErrorCategory.PERMISSION, "scan project is unavailable")
    if project.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "scan project revision changed")

    async def _resolve(technology_id: str) -> str:
        return await _technology_authority(db, ctx, organization_id, technology_id)

    async def _authorize_pair(action: str) -> None:
        await _pair_authority(db, ctx, organization_id, project_id, action)

    # All authorization, identity and mapping checks finish before structural mutation.
    response, before = await merge_scan_facts(
        db,
        organization_id=organization_id,
        organization=organization,
        project=project,
        handoff=handoff,
        observations=observations,
        digest=digest,
        resolve_technology=_resolve,
        authorize_pair=_authorize_pair,
    )
    await finish_mutation(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        target=project_id,
        response=response,
        before=before,
        request_id=request_id,
        target_table="technology_scan",
        audit_target=handoff.scan_id,
        reason="scan_refresh",
        source="detector",
    )
    return response


async def read_scan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    scan_id: str,
    request_id: str | None,
) -> TechnologyScanView:
    for permission in ("project.read", "project_technology.read"):
        await authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission=permission,
            scope_kind="project",
            scope_id=project_id,
        )
    row = await db.get(TechnologyScan, (organization_id, scan_id))
    if row is None or row.project_id != project_id:
        raise ApiError(ErrorCategory.PERMISSION, "scan history is unavailable")
    response = TechnologyScanView.model_validate(row.handoff)
    for observation in response.handoff.observations:
        await _technology_authority(db, ctx, organization_id, observation.technology_id)
    for usage in response.result.usages:
        await _technology_authority(db, ctx, organization_id, usage.technology_id)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="technology.scan.read",
        target_table="technology_scan",
        target_id=scan_id,
        request_id=request_id,
    )
    return response


async def read_unmapped(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    request_id: str | None,
) -> TechnologyUnmappedView:
    """Every coordinate the organization's published scans could not resolve."""
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="technology.list")
    rows = list(
        (
            await db.execute(
                select(
                    TechnologyUnmappedCoordinate.kind,
                    TechnologyUnmappedCoordinate.coordinate,
                    TechnologyUnmappedCoordinate.project_id,
                ).where(TechnologyUnmappedCoordinate.organization_id == organization_id)
            )
        ).all()
    )
    grouped: dict[tuple[str, str], set[str]] = {}
    for kind, coordinate, project_id in rows:
        grouped.setdefault((kind, coordinate), set()).add(project_id)
    response = TechnologyUnmappedView(
        organization_id=organization_id,
        coordinates=[
            TechnologyUnmappedEntry(
                # The check constraint keeps kind inside the literal set.
                kind=cast(
                    Literal["package", "image", "executable", "configuration", "alias"], kind
                ),
                coordinate=coordinate,
                project_ids=sorted(project_ids),
            )
            for (kind, coordinate), project_ids in sorted(grouped.items())
        ],
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="technology.unmapped.read",
        target_table="technology_unmapped_coordinate",
        target_id=organization_id,
        request_id=request_id,
    )
    return response
