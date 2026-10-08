"""Immutable detector snapshots refresh facts, never owner decisions or project links."""

from typing import Literal, cast

from sqlalchemy import func, select, update
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
    TechnologyMappingList,
    TechnologyMappingRequest,
    TechnologyMappingSummary,
    TechnologyMappingView,
    TechnologyObservation,
    TechnologyScanDetail,
    TechnologyScanFinding,
    TechnologyScanHandoff,
    TechnologyScanLaunchItem,
    TechnologyScanLaunchRequest,
    TechnologyScanLaunchResult,
    TechnologyScanList,
    TechnologyScanListEntry,
    TechnologyScanRequest,
    TechnologyScanResult,
    TechnologyScanSource,
    TechnologyScanStatus,
    TechnologyScanView,
    TechnologyUnmappedEntry,
    TechnologyUnmappedReviewRequest,
    TechnologyUnmappedView,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.organization_models import (
    CorporateProject,
    ProjectIdentity,
    ProjectLink,
)
from ai_stp_platform.queue.engine import enqueue
from ai_stp_platform.queue.models import Job
from ai_stp_platform.queue.states import JobState, JobType
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


async def list_mappings(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    request_id: str | None,
) -> TechnologyMappingList:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="technology.list")
    rows = (
        await db.execute(
            select(TechnologyCoordinateMapping.version, func.count())
            .where(TechnologyCoordinateMapping.organization_id == organization_id)
            .group_by(TechnologyCoordinateMapping.version)
            .order_by(TechnologyCoordinateMapping.version)
        )
    ).all()
    items: list[TechnologyMappingSummary] = []
    for version, count in rows:
        entries = await _mapped_entries(db, organization_id, str(version))
        items.append(
            TechnologyMappingSummary(
                version=str(version),
                entries=int(count),
                digest=_mapping_view(organization_id, str(version), entries).digest,
            )
        )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="technology.mapping.list",
        target_table="technology_coordinate_mapping",
        target_id=organization_id,
        request_id=request_id,
    )
    return TechnologyMappingList(organization_id=organization_id, items=items)


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
    merged: dict[tuple[str, str], TechnologyMappingEntry] = {}
    if payload.base_version is not None:
        base = await _mapped_entries(db, organization_id, payload.base_version)
        if not base:
            raise ApiError(ErrorCategory.PERMISSION, "base mapping snapshot is unavailable")
        for entry in base:
            await _technology_authority(db, ctx, organization_id, entry.technology_id)
        merged.update({(entry.kind, entry.coordinate): entry for entry in base})
    merged.update({(entry.kind, entry.coordinate): entry for entry in payload.entries})
    response = _mapping_view(organization_id, version, list(merged.values()))
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
        # The freshest snapshot defines coverage: every queued coordinate it
        # names is resolved, everything it drops reopens for review.
        resolved = (
            select(TechnologyCoordinateMapping.technology_id)
            .where(
                TechnologyCoordinateMapping.organization_id == organization_id,
                TechnologyCoordinateMapping.version == version,
                TechnologyCoordinateMapping.kind == TechnologyUnmappedCoordinate.kind,
                TechnologyCoordinateMapping.coordinate == TechnologyUnmappedCoordinate.coordinate,
            )
            .order_by(TechnologyCoordinateMapping.technology_id)
            .limit(1)
            .correlate(TechnologyUnmappedCoordinate)
            .scalar_subquery()
        )
        await db.execute(
            update(TechnologyUnmappedCoordinate)
            .where(TechnologyUnmappedCoordinate.organization_id == organization_id)
            .values(resolved_technology_id=resolved)
        )
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
        provenance={"source": payload.source},
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


def _unmapped_entry(rows: list[TechnologyUnmappedCoordinate]) -> TechnologyUnmappedEntry:
    """One grouped queue entry; review fields are uniform across its rows."""
    first = rows[0]
    candidate = next(
        (row.candidate_technology_id for row in rows if row.candidate_technology_id is not None),
        None,
    )
    resolved = next(
        (row.resolved_technology_id for row in rows if row.resolved_technology_id is not None),
        None,
    )
    return TechnologyUnmappedEntry(
        # The check constraint keeps kind inside the literal set.
        kind=cast(Literal["package", "image", "executable", "configuration", "alias"], first.kind),
        coordinate=first.coordinate,
        project_ids=sorted({row.project_id for row in rows}),
        candidate_technology_id=candidate,
        resolved_technology_id=resolved,
        state="resolved" if resolved is not None else "open",
    )


async def read_unmapped(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str | None = None,
    scan_id: str | None = None,
    request_id: str | None,
) -> TechnologyUnmappedView:
    """Every coordinate the organization's published scans could not resolve."""
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="technology.list")
    statement = select(TechnologyUnmappedCoordinate).where(
        TechnologyUnmappedCoordinate.organization_id == organization_id
    )
    if project_id is not None:
        statement = statement.where(TechnologyUnmappedCoordinate.project_id == project_id)
    if scan_id is not None:
        statement = statement.where(TechnologyUnmappedCoordinate.scan_id == scan_id)
    rows = list((await db.scalars(statement)).all())
    grouped: dict[tuple[str, str], list[TechnologyUnmappedCoordinate]] = {}
    for row in rows:
        grouped.setdefault((row.kind, row.coordinate), []).append(row)
    response = TechnologyUnmappedView(
        organization_id=organization_id,
        coordinates=[_unmapped_entry(group) for _, group in sorted(grouped.items())],
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


async def review_unmapped(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: TechnologyUnmappedReviewRequest,
    request_id: str | None,
) -> TechnologyUnmappedEntry:
    """Propose or clear the candidate technology for one queued coordinate.

    A candidate is a suggestion, not a mapping: the coordinate stays open until
    a published snapshot names it. Review fields are held org-wide — every
    project's row for the coordinate shows the same candidate.
    """
    operation = "technology.unmapped.review"
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="technology.update",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=mutation_effect(payload, f"{payload.kind}:{payload.coordinate}"),
        request_id=request_id,
    )
    if receipt is not None:
        return TechnologyUnmappedEntry.model_validate(receipt.response_body)
    candidate: str | None = None
    if payload.candidate_technology_id is not None:
        candidate = await _technology_authority(
            db, ctx, organization_id, payload.candidate_technology_id, update=True
        )
    rows = list(
        (
            await db.scalars(
                select(TechnologyUnmappedCoordinate).where(
                    TechnologyUnmappedCoordinate.organization_id == organization_id,
                    TechnologyUnmappedCoordinate.kind == payload.kind,
                    TechnologyUnmappedCoordinate.coordinate == payload.coordinate,
                )
            )
        ).all()
    )
    if not rows:
        raise ApiError(ErrorCategory.PERMISSION, "unmapped coordinate is unavailable")
    for row in rows:
        row.candidate_technology_id = candidate
    organization.policy_revision += 1
    await db.flush()
    response = _unmapped_entry(rows)
    await finish_mutation(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        target=f"{payload.kind}:{payload.coordinate}",
        response=response,
        before=None,
        request_id=request_id,
        target_table="technology_unmapped_coordinate",
    )
    return response


_SCAN_JOB_TYPES = (JobType.GITLAB_TECHNOLOGY_SCAN, JobType.GITHUB_TECHNOLOGY_SCAN)
_QUEUED_JOB_STATES = {JobState.QUEUED, JobState.RETRY_SCHEDULED}


def _scan_status(job: Job | None, scan: TechnologyScan | None) -> TechnologyScanStatus:
    if scan is not None:
        return "succeeded"
    if job is None:
        return "failed"
    if job.state in _QUEUED_JOB_STATES:
        return "queued"
    if job.state == JobState.RUNNING:
        return "running"
    if job.state == JobState.SUCCEEDED:
        return "succeeded"
    return "failed"


async def _latest_mapping_version(db: AsyncSession, organization_id: str) -> str | None:
    return await db.scalar(
        select(func.max(TechnologyCoordinateMapping.version)).where(
            TechnologyCoordinateMapping.organization_id == organization_id
        )
    )


def _observation_count(scan: TechnologyScan) -> int:
    handoff = scan.handoff.get("handoff")
    if not isinstance(handoff, dict):
        return 0
    return len(TechnologyScanHandoff.model_validate(handoff).observations)


async def list_scans(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str | None = None,
    request_id: str | None,
) -> TechnologyScanList:
    """The organization's scan journal: queued jobs and published scans."""
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="landscape.read")
    scan_filter = select(TechnologyScan).where(TechnologyScan.organization_id == organization_id)
    job_filter = select(Job).where(
        Job.organization_id == organization_id,
        Job.job_type.in_([str(job_type) for job_type in _SCAN_JOB_TYPES]),
    )
    if project_id is not None:
        scan_filter = scan_filter.where(TechnologyScan.project_id == project_id)
        job_filter = job_filter.where(Job.payload["project_id"].as_string() == project_id)
    scans = {row.id: row for row in (await db.scalars(scan_filter)).all()}
    jobs = list((await db.scalars(job_filter)).all())
    project_names = {
        row.id: row.name
        for row in (
            await db.scalars(
                select(CorporateProject).where(CorporateProject.organization_id == organization_id)
            )
        ).all()
    }
    pending_counts = {
        str(scan_id): int(count)
        for scan_id, count in (
            await db.execute(
                select(
                    TechnologyUnmappedCoordinate.scan_id,
                    func.count(),
                )
                .where(
                    TechnologyUnmappedCoordinate.organization_id == organization_id,
                    TechnologyUnmappedCoordinate.resolved_technology_id.is_(None),
                )
                .group_by(TechnologyUnmappedCoordinate.scan_id)
            )
        ).all()
    }
    entries: dict[str, TechnologyScanListEntry] = {}
    for job in jobs:
        scan_id = job.payload.get("scan_id")
        job_project = job.payload.get("project_id")
        if not isinstance(scan_id, str):
            continue
        scan = scans.pop(scan_id, None)
        entries[scan_id] = TechnologyScanListEntry(
            scan_id=scan_id,
            project_id=cast("str", scan.project_id if scan is not None else job_project),
            project_name=project_names.get(
                cast("str", scan.project_id if scan is not None else job_project)
            ),
            repository=scan.repository
            if scan is not None
            else cast("str | None", job.payload.get("provider_project_id")),
            source=cast(
                "TechnologyScanSource",
                scan.source
                if scan is not None and scan.source is not None
                else "gitlab"
                if job.job_type == str(JobType.GITLAB_TECHNOLOGY_SCAN)
                else "github",
            ),
            branch=scan.branch if scan is not None else None,
            commit=scan.commit if scan is not None else None,
            created_at=format_timestamp((scan or job).created_at),
            status=_scan_status(job, scan),
            found=_observation_count(scan) if scan is not None else 0,
            pending=pending_counts.get(scan_id, 0),
        )
    for scan_id, scan in scans.items():
        entries[scan_id] = TechnologyScanListEntry(
            scan_id=scan_id,
            project_id=scan.project_id,
            project_name=project_names.get(scan.project_id),
            repository=scan.repository,
            source=cast("TechnologyScanSource", scan.source or "local"),
            branch=scan.branch,
            commit=scan.commit,
            created_at=format_timestamp(scan.created_at),
            status="succeeded",
            found=_observation_count(scan),
            pending=pending_counts.get(scan_id, 0),
        )
    items = sorted(entries.values(), key=lambda entry: entry.created_at, reverse=True)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="technology.scan.list",
        target_table="technology_scan",
        target_id=organization_id,
        request_id=request_id,
    )
    return TechnologyScanList(organization_id=organization_id, items=items, total=len(items))


async def launch_scans(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: TechnologyScanLaunchRequest,
    request_id: str | None,
) -> TechnologyScanLaunchResult:
    """Queue one repository scan per selected project.

    Each project is validated independently: a rejected item never blocks the
    others, matching the journal's per-scan status model.
    """
    operation = "technology.scan.launch"
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="technology.scan.publish",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=mutation_effect(payload, organization_id),
        request_id=request_id,
    )
    if receipt is not None:
        return TechnologyScanLaunchResult.model_validate(receipt.response_body)
    mapping_version = await _latest_mapping_version(db, organization_id)
    if mapping_version is None:
        raise ApiError(ErrorCategory.PRECONDITION, "a mapping snapshot is required before scanning")
    items: list[TechnologyScanLaunchItem] = []
    for project_id in payload.project_ids:
        scan_id = new_id("scan")
        try:
            await authorize(
                db,
                ctx=ctx,
                organization_id=organization_id,
                permission="technology.scan.publish",
                scope_kind="project",
                scope_id=project_id,
            )
            link = await db.scalar(
                select(ProjectLink).where(
                    ProjectLink.organization_id == organization_id,
                    ProjectLink.remote_project_id == project_id,
                    ProjectLink.state == "linked",
                )
            )
            provider_identity = (
                await db.get(ProjectIdentity, link.provider_project_id)
                if link is not None and link.provider_project_id is not None
                else None
            )
            provider = (
                provider_identity.provider_kind
                if provider_identity is not None
                and provider_identity.organization_id == organization_id
                else None
            )
            if provider_identity is None or provider not in ("gitlab", "github"):
                raise ApiError(
                    ErrorCategory.VALIDATION,
                    "project has no linked GitHub/GitLab repository",
                )
            job = await enqueue(
                db,
                job_type=(
                    JobType.GITLAB_TECHNOLOGY_SCAN
                    if provider == "gitlab"
                    else JobType.GITHUB_TECHNOLOGY_SCAN
                ),
                payload={
                    "provider_project_id": provider_identity.id,
                    "project_id": project_id,
                    "scan_id": scan_id,
                    "mapping_version": mapping_version,
                },
                idempotency_key=f"{provider}_technology_scan:{organization_id}:{scan_id}",
                organization_id=organization_id,
                authorization_revision=organization.policy_revision,
                principal_type="user",
                principal_id=ctx.account_id,
                required_permission="technology.scan.publish",
                scope_kind="project",
                scope_id=project_id,
            )
            items.append(
                TechnologyScanLaunchItem(
                    project_id=project_id,
                    scan_id=scan_id,
                    job_id=job.id,
                    state="queued",
                )
            )
        except ApiError as error:
            items.append(
                TechnologyScanLaunchItem(
                    project_id=project_id,
                    state="rejected",
                    detail=error.message,
                )
            )
    result = TechnologyScanLaunchResult(organization_id=organization_id, items=items)
    await finish_mutation(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        target=organization_id,
        response=result,
        before=None,
        request_id=request_id,
        target_table="job",
        reason="scan_launch",
        source="detector",
    )
    return result


async def read_scan_detail(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    scan_id: str,
    request_id: str | None,
) -> TechnologyScanDetail:
    """One journal row expanded into its detector findings."""
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="landscape.read")
    scan = await db.get(TechnologyScan, (organization_id, scan_id))
    job: Job | None = None
    if scan is None:
        job = await db.scalar(
            select(Job).where(
                Job.organization_id == organization_id,
                Job.job_type.in_([str(job_type) for job_type in _SCAN_JOB_TYPES]),
                Job.payload["scan_id"].as_string() == scan_id,
            )
        )
        if job is None:
            raise ApiError(ErrorCategory.PERMISSION, "scan is unavailable")
        project_id = cast("object", job.payload.get("project_id"))
    else:
        project_id = cast("object", scan.project_id)
    if not isinstance(project_id, str):
        raise ApiError(ErrorCategory.PERMISSION, "scan is unavailable")
    for permission in ("project.read", "project_technology.read"):
        await authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission=permission,
            scope_kind="project",
            scope_id=project_id,
        )
    project = await db.scalar(
        select(CorporateProject).where(
            CorporateProject.organization_id == organization_id,
            CorporateProject.id == project_id,
        )
    )
    findings: list[TechnologyScanFinding] = []
    handoff: TechnologyScanHandoff | None = None
    pending = 0
    if scan is not None:
        handoff = TechnologyScanHandoff.model_validate(scan.handoff["handoff"])
        unmapped_rows = {
            (row.kind, row.coordinate): row
            for row in (
                await db.scalars(
                    select(TechnologyUnmappedCoordinate).where(
                        TechnologyUnmappedCoordinate.organization_id == organization_id,
                        TechnologyUnmappedCoordinate.scan_id == scan_id,
                    )
                )
            ).all()
        }
        for observation in handoff.observations:
            findings.append(
                TechnologyScanFinding(
                    kind="alias",
                    coordinate=observation.technology_id,
                    context=observation.fact.context,
                    technology_id=observation.technology_id,
                    version=observation.fact.version,
                    version_kind=observation.fact.version_kind,
                    evidence=list(observation.fact.evidence),
                    state="resolved",
                )
            )
        for coordinate in handoff.unmapped_coordinates:
            row = unmapped_rows.get((coordinate.kind, coordinate.coordinate))
            resolved = row.resolved_technology_id if row is not None else None
            candidate = row.candidate_technology_id if row is not None else None
            if resolved is not None:
                state: Literal["resolved", "candidate", "open"] = "resolved"
            elif candidate is not None:
                state = "candidate"
            else:
                state = "open"
                pending += 1
            findings.append(
                TechnologyScanFinding(
                    kind=coordinate.kind,
                    coordinate=coordinate.coordinate,
                    context=coordinate.context,
                    technology_id=resolved,
                    version=coordinate.version,
                    evidence=list(coordinate.evidence),
                    state=state,
                    candidate_technology_id=candidate,
                )
            )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="technology.scan.read",
        target_table="technology_scan",
        target_id=scan_id,
        request_id=request_id,
    )
    if scan is not None:
        repository = scan.repository
        source = cast("TechnologyScanSource", scan.source or "local")
        branch, commit, created = scan.branch, scan.commit, scan.created_at
    else:
        assert job is not None
        repository = cast("str | None", job.payload.get("provider_project_id"))
        source = cast(
            "TechnologyScanSource",
            "gitlab" if job.job_type == str(JobType.GITLAB_TECHNOLOGY_SCAN) else "github",
        )
        branch = commit = None
        created = job.created_at
    return TechnologyScanDetail(
        scan_id=scan_id,
        project_id=project_id,
        project_name=project.name if project is not None else None,
        repository=repository,
        source=source,
        branch=branch,
        commit=commit,
        created_at=format_timestamp(created),
        status=_scan_status(job, scan),
        found=len(handoff.observations) if handoff is not None else 0,
        pending=pending,
        detector_version=handoff.detector_version if handoff is not None else None,
        mapping_version=handoff.mapping_version if handoff is not None else None,
        complete=handoff.complete if handoff is not None else True,
        findings=findings,
    )
