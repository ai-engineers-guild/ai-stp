"""Shared current interpretation of immutable local and repository scans."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.technology import (
    TechnologyDetectedCoordinate,
    TechnologyScanFinding,
    TechnologyScanHandoff,
    TechnologyScanResult,
)
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_platform.technology_models import (
    ProjectTechnologyRelation,
    TechnologyCoordinateMapping,
    TechnologyFindingReview,
    TechnologyScan,
    TechnologyUnmappedCoordinate,
    TechnologyUsageFact,
)


def finding_key(kind: str, coordinate: str, context: str | None) -> str:
    return digest_canonical("ai-stp:plan:v1", [kind, coordinate, context])


async def latest_mapping_version(db: AsyncSession, organization_id: str) -> str | None:
    return await db.scalar(
        select(TechnologyCoordinateMapping.version)
        .where(TechnologyCoordinateMapping.organization_id == organization_id)
        .group_by(TechnologyCoordinateMapping.version)
        .order_by(
            func.max(TechnologyCoordinateMapping.published_at).desc(),
            TechnologyCoordinateMapping.version.desc(),
        )
        .limit(1)
    )


async def scan_coordinates(
    db: AsyncSession, organization_id: str, handoff: TechnologyScanHandoff
) -> list[TechnologyDetectedCoordinate]:
    if handoff.coordinates:
        return list(handoff.coordinates)
    mappings = list(
        (
            await db.scalars(
                select(TechnologyCoordinateMapping).where(
                    TechnologyCoordinateMapping.organization_id == organization_id,
                    TechnologyCoordinateMapping.version == handoff.mapping_version,
                )
            )
        ).all()
    )
    result: list[TechnologyDetectedCoordinate] = []
    for observation in handoff.observations:
        aliases = sorted(
            [row for row in mappings if row.technology_id == observation.technology_id],
            key=lambda row: (row.kind != "alias", row.coordinate),
        )
        match = aliases[0] if aliases else None
        result.append(
            TechnologyDetectedCoordinate(
                kind=cast(
                    Literal["package", "image", "executable", "configuration", "alias"],
                    match.kind if match else "alias",
                ),
                coordinate=match.coordinate if match else observation.technology_id,
                technology_id=observation.technology_id,
                **observation.fact.model_dump(),
            )
        )
    result.extend(
        TechnologyDetectedCoordinate(**item.model_dump()) for item in handoff.unmapped_coordinates
    )
    return result


async def interpreted_findings(
    db: AsyncSession, organization_id: str, scan: TechnologyScan
) -> list[TechnologyScanFinding]:
    handoff = TechnologyScanHandoff.model_validate(scan.handoff["handoff"])
    version = await latest_mapping_version(db, organization_id)
    mappings = (
        list(
            (
                await db.scalars(
                    select(TechnologyCoordinateMapping).where(
                        TechnologyCoordinateMapping.organization_id == organization_id,
                        TechnologyCoordinateMapping.version == version,
                    )
                )
            ).all()
        )
        if version
        else []
    )
    mapped = {(row.kind, row.coordinate): row.technology_id for row in mappings}
    history = list(
        (
            await db.scalars(
                select(TechnologyScan).where(
                    TechnologyScan.organization_id == organization_id,
                    TechnologyScan.project_id == scan.project_id,
                )
            )
        ).all()
    )
    same_scope = {
        row.id
        for row in history
        if TechnologyScanHandoff.model_validate(row.handoff["handoff"]).scope == handoff.scope
    }
    reviews = list(
        (
            await db.scalars(
                select(TechnologyFindingReview)
                .where(
                    TechnologyFindingReview.organization_id == organization_id,
                    TechnologyFindingReview.scan_id.in_(same_scope | {scan.id}),
                )
                .order_by(TechnologyFindingReview.updated_at)
            )
        ).all()
    )
    candidates = {
        (row.kind, row.coordinate): row.candidate_technology_id
        for row in (
            await db.scalars(
                select(TechnologyUnmappedCoordinate).where(
                    TechnologyUnmappedCoordinate.organization_id == organization_id,
                    TechnologyUnmappedCoordinate.project_id == scan.project_id,
                )
            )
        ).all()
    }
    usage_reviews = {
        (technology_id, context): review
        for technology_id, context, review in (
            await db.execute(
                select(
                    ProjectTechnologyRelation.technology_id,
                    TechnologyUsageFact.context,
                    TechnologyUsageFact.review,
                )
                .join(
                    TechnologyUsageFact,
                    (
                        TechnologyUsageFact.organization_id
                        == ProjectTechnologyRelation.organization_id
                    )
                    & (TechnologyUsageFact.relation_id == ProjectTechnologyRelation.id),
                )
                .where(
                    ProjectTechnologyRelation.organization_id == organization_id,
                    ProjectTechnologyRelation.project_id == scan.project_id,
                )
            )
        ).all()
    }
    inherited = {row.finding_key: row for row in reviews}
    exact = {row.finding_key: row for row in reviews if row.scan_id == scan.id}
    result: list[TechnologyScanFinding] = []
    for item in await scan_coordinates(db, organization_id, handoff):
        key = finding_key(item.kind, item.coordinate, item.context)
        review = exact.get(key) or inherited.get(key)
        technology_id = (
            review.technology_id
            if review
            else mapped.get((item.kind, item.coordinate))
            if handoff.coordinates or item.coordinate != item.technology_id
            else item.technology_id
        )
        result.append(
            TechnologyScanFinding(
                **item.model_dump(exclude={"technology_id"}),
                technology_id=technology_id,
                candidate_technology_id=candidates.get((item.kind, item.coordinate)),
                state="rejected"
                if review and review.review == "rejected"
                else "resolved"
                if technology_id
                else "candidate"
                if candidates.get((item.kind, item.coordinate))
                else "open",
                review=cast(Literal["confirmed", "rejected"], review.review)
                if review
                else "confirmed"
                if usage_reviews.get((technology_id or "", item.context or "production"))
                in {"confirmed", "overridden"}
                else "rejected"
                if usage_reviews.get((technology_id or "", item.context or "production"))
                == "rejected"
                else "proposed",
                review_revision=exact[key].revision if key in exact else 0,
                comment=review.comment if review else "",
            )
        )
    return result


async def reproject_current_scans(
    db: AsyncSession,
    organization_id: str,
    project_id: str,
    *,
    confirmed: set[tuple[str, str]] | None = None,
    incoming: TechnologyScan | None = None,
    authorize_pair: Callable[[str], Awaitable[None]] | None = None,
    resolve_technology: Callable[[str], Awaitable[str]] | None = None,
) -> None:
    """Refresh current usage without rewriting any original scan document."""
    scans = list(
        (
            await db.scalars(
                select(TechnologyScan).where(
                    TechnologyScan.organization_id == organization_id,
                    TechnologyScan.project_id == project_id,
                )
            )
        ).all()
    )
    if incoming is not None:
        scans.append(incoming)
    latest: dict[str, TechnologyScan] = {}
    for scan in scans:
        scope = TechnologyScanHandoff.model_validate(scan.handoff["handoff"]).scope
        sequence = TechnologyScanResult.model_validate(scan.handoff["result"]).project_revision
        if (
            scope not in latest
            or sequence
            > TechnologyScanResult.model_validate(latest[scope].handoff["result"]).project_revision
        ):
            latest[scope] = scan
    current: dict[tuple[str, str], TechnologyScanFinding] = {}
    complete = all(
        TechnologyScanHandoff.model_validate(scan.handoff["handoff"]).complete
        for scan in latest.values()
    )
    for scan in latest.values():
        for item in await interpreted_findings(db, organization_id, scan):
            if item.technology_id is None:
                continue
            technology_id = (
                await resolve_technology(item.technology_id)
                if resolve_technology
                else item.technology_id
            )
            item = item.model_copy(update={"technology_id": technology_id})
            key = (technology_id, item.context or "production")
            held = current.get(key)
            if (
                held is None
                or item.review_revision
                or (held.version is None and item.version is not None)
            ):
                current[key] = item
    relations = list(
        (
            await db.scalars(
                select(ProjectTechnologyRelation).where(
                    ProjectTechnologyRelation.organization_id == organization_id,
                    ProjectTechnologyRelation.project_id == project_id,
                )
            )
        ).all()
    )
    by_technology = {row.technology_id: row for row in relations}
    for (technology_id, context), item in current.items():
        pair = by_technology.get(technology_id)
        if pair is not None and pair.state == "retired":
            continue
        if authorize_pair is not None:
            await authorize_pair("create" if pair is None else "update")
        if pair is None:
            pair = ProjectTechnologyRelation(
                organization_id=organization_id,
                id=new_id("relation"),
                project_id=project_id,
                technology_id=technology_id,
                state="current",
                revision=1,
            )
            db.add(pair)
            await db.flush()
            by_technology[technology_id] = pair
        fact = await db.get(TechnologyUsageFact, (organization_id, pair.id, context))
        explicit = bool(
            item.review_revision
            or item.comment
            or (confirmed and (item.kind, item.coordinate) in confirmed)
        )
        # A decision inherited from a previous scan is also an owner decision.
        owner_review = await db.scalar(
            select(TechnologyFindingReview)
            .join(
                TechnologyScan,
                (TechnologyScan.organization_id == TechnologyFindingReview.organization_id)
                & (TechnologyScan.id == TechnologyFindingReview.scan_id),
            )
            .where(
                TechnologyFindingReview.organization_id == organization_id,
                TechnologyScan.project_id == project_id,
                TechnologyFindingReview.finding_key
                == finding_key(item.kind, item.coordinate, item.context),
            )
            .order_by(TechnologyFindingReview.updated_at.desc())
            .limit(1)
        )
        explicit = explicit or owner_review is not None
        if fact is None:
            fact = TechnologyUsageFact(
                organization_id=organization_id,
                relation_id=pair.id,
                context=context,
                review="proposed",
            )
            db.add(fact)
        before = (fact.review, fact.version, fact.version_kind, fact.evidence, fact.freshness)
        if explicit:
            fact.review = "rejected" if item.state == "rejected" else "confirmed"
        if fact.review == "proposed" or explicit:
            fact.version = item.version
            fact.version_kind = item.version_kind if item.version else "unknown"
            if fact.version and fact.version_kind == "unknown":
                fact.version_kind = "declared_range"
            fact.evidence = [entry.model_dump(mode="json") for entry in item.evidence]
            fact.freshness = "current" if complete else "unknown"
        if before != (fact.review, fact.version, fact.version_kind, fact.evidence, fact.freshness):
            pair.revision += 1
    for pair in relations:
        for fact in (
            await db.scalars(
                select(TechnologyUsageFact).where(
                    TechnologyUsageFact.organization_id == organization_id,
                    TechnologyUsageFact.relation_id == pair.id,
                )
            )
        ).all():
            if (
                (pair.technology_id, fact.context) not in current
                and fact.evidence
                and all(entry.get("source") != "manual" for entry in fact.evidence)
            ):
                fact.freshness = "absent" if complete else "unknown"
    await db.flush()
