"""Fold a technology scan handoff into relations and facts.

The API publish path authorizes first and supplies the per-scope hooks:
redirects resolve, and every mutation check finishes before this function
writes anything.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.technology import (
    ProjectTechnologyView,
    TechnologyObservation,
    TechnologyScanHandoff,
    TechnologyScanResult,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.organization_models import CorporateProject, Organization
from ai_stp_platform.technology_models import (
    ProjectTechnologyRelation,
    TechnologyScan,
    TechnologyUnmappedCoordinate,
    TechnologyUsageFact,
)

ResolveTechnology = Callable[[str], Awaitable[str]]
AuthorizePair = Callable[[str], Awaitable[None]]


async def project_technology_view(
    db: AsyncSession,
    row: ProjectTechnologyRelation,
) -> ProjectTechnologyView:
    facts = list(
        (
            await db.scalars(
                select(TechnologyUsageFact)
                .where(
                    TechnologyUsageFact.organization_id == row.organization_id,
                    TechnologyUsageFact.relation_id == row.id,
                )
                .order_by(TechnologyUsageFact.context)
            )
        ).all()
    )
    return ProjectTechnologyView.model_validate(
        {
            "organization_id": row.organization_id,
            "relation_id": row.id,
            "project_id": row.project_id,
            "technology_id": row.technology_id,
            "state": row.state,
            "revision": row.revision,
            "facts": [
                {
                    "context": fact.context,
                    "version": fact.version,
                    "version_kind": fact.version_kind,
                    "review": fact.review,
                    "freshness": fact.freshness,
                    "evidence": fact.evidence,
                }
                for fact in facts
            ],
        }
    )


async def merge_scan_facts(
    db: AsyncSession,
    *,
    organization_id: str,
    organization: Organization,
    project: CorporateProject,
    handoff: TechnologyScanHandoff,
    observations: dict[tuple[str, str], TechnologyObservation],
    digest: str,
    resolve_technology: ResolveTechnology,
    authorize_pair: AuthorizePair | None = None,
    provenance: dict[str, str | None] | None = None,
) -> tuple[TechnologyScanResult, dict[str, Any]]:
    """Merge one handoff into the project's usage facts and store the scan.

    ``observations`` are the handoff's observations keyed by resolved
    ``(technology_id, context)``; ``resolve_technology`` maps a referenced
    identity to its current one (redirect traversal); ``authorize_pair`` runs
    the caller's project-scope authorization with ``"create"`` or ``"update"``
    before a relation row is touched. Returns the persisted result and the
    pre-mutation snapshot.
    """
    project_id = project.id
    prior_rows = list(
        (
            await db.scalars(
                select(TechnologyScan).where(
                    TechnologyScan.organization_id == organization_id,
                    TechnologyScan.project_id == project_id,
                )
            )
        ).all()
    )
    latest: dict[str, tuple[int, TechnologyScanHandoff]] = {}
    previous_keys: set[tuple[str, str]] = set()
    for row in prior_rows:
        previous = TechnologyScanHandoff.model_validate(row.handoff["handoff"])
        if previous.scope == handoff.scope:
            for observation in previous.observations:
                current = await resolve_technology(observation.technology_id)
                previous_keys.add((current, observation.fact.context))
        sequence = TechnologyScanResult.model_validate(row.handoff["result"]).project_revision
        if previous.scope not in latest or sequence > latest[previous.scope][0]:
            latest[previous.scope] = (sequence, previous)
    other_keys: set[tuple[str, str]] = set()
    for scope, (_, previous) in latest.items():
        for observation in previous.observations:
            current = await resolve_technology(observation.technology_id)
            (previous_keys if scope == handoff.scope else other_keys).add(
                (current, observation.fact.context)
            )
    keys = set(observations) | (previous_keys - other_keys)
    pairs: dict[str, ProjectTechnologyRelation | None] = {}
    facts: dict[tuple[str, str], TechnologyUsageFact | None] = {}
    for technology_id, context in sorted(keys):
        if technology_id not in pairs:
            pairs[technology_id] = await db.scalar(
                select(ProjectTechnologyRelation).where(
                    ProjectTechnologyRelation.organization_id == organization_id,
                    ProjectTechnologyRelation.project_id == project_id,
                    ProjectTechnologyRelation.technology_id == technology_id,
                )
            )
            if authorize_pair is not None:
                await authorize_pair("update" if pairs[technology_id] else "create")
        pair = pairs[technology_id]
        facts[(technology_id, context)] = (
            await db.get(TechnologyUsageFact, (organization_id, pair.id, context)) if pair else None
        )
    disagreements: list[TechnologyObservation] = []
    touched: dict[str, ProjectTechnologyRelation] = {}
    created_relation_ids: list[str] = []
    before = {
        "project_revision": project.revision,
        "usages": [
            (await project_technology_view(db, pair)).model_dump(mode="json")
            for pair in pairs.values()
            if pair is not None
        ],
    }
    for key in sorted(keys):
        technology_id, context = key
        observation, fact, pair = observations.get(key), facts[key], pairs[technology_id]
        if pair is not None and pair.state == "retired":
            if observation:
                disagreements.append(observation)
            continue
        if pair is None:
            if observation is None:
                continue
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
            pairs[technology_id] = pair
            created_relation_ids.append(pair.id)
        elif technology_id not in touched:
            pair.revision += 1
        touched[technology_id] = pair
        if observation is None:
            # Manual evidence is independent of detector source availability.
            if (
                fact is not None
                and fact.review != "retired"
                and fact.evidence
                and all(entry.get("source") != "manual" for entry in fact.evidence)
            ):
                fact.freshness = "absent" if handoff.complete else "unknown"
            continue
        if fact is not None and fact.review != "proposed":
            if (fact.version, fact.version_kind) != (
                observation.fact.version,
                observation.fact.version_kind,
            ) or fact.review in {"rejected", "retired"}:
                disagreements.append(observation)
                if (
                    fact.evidence
                    and fact.review != "retired"
                    and all(entry.get("source") != "manual" for entry in fact.evidence)
                ):
                    fact.freshness = "stale" if handoff.complete else "unknown"
            elif fact.evidence and all(entry.get("source") != "manual" for entry in fact.evidence):
                fact.freshness = "current" if handoff.complete else "unknown"
            continue
        if fact is None:
            fact = TechnologyUsageFact(
                organization_id=organization_id,
                relation_id=pair.id,
                context=context,
                review="proposed",
            )
            db.add(fact)
        fact.version = observation.fact.version
        fact.version_kind = observation.fact.version_kind
        fact.evidence = [entry.model_dump(mode="json") for entry in observation.fact.evidence]
        fact.freshness = "current" if handoff.complete else "unknown"
    project.revision += 1
    organization.policy_revision += 1
    await db.flush()
    response = TechnologyScanResult(
        organization_id=organization_id,
        project_id=project_id,
        scan_id=handoff.scan_id,
        project_revision=project.revision,
        digest=digest,
        disagreements=disagreements,
        usages=[
            await project_technology_view(db, pair) for pair in pairs.values() if pair is not None
        ],
        created_relation_ids=created_relation_ids,
    )
    provenance = provenance or {}
    db.add(
        TechnologyScan(
            organization_id=organization_id,
            id=handoff.scan_id,
            project_id=project_id,
            fingerprint=digest,
            source=provenance.get("source"),
            repository=provenance.get("repository"),
            branch=provenance.get("branch"),
            commit=provenance.get("commit"),
            handoff={
                "handoff": handoff.model_dump(mode="json"),
                "result": response.model_dump(mode="json"),
            },
        )
    )
    # Unmapped coordinates are the registry's review queue: a scope's rescan
    # replaces its rows wholesale so the queue says what the latest scan said.
    # Review candidates are proposals attached to the coordinate org-wide, not
    # scan output — a rewrite carries them over rather than dropping work.
    prior_candidates = {
        (row.kind, row.coordinate): row.candidate_technology_id
        for row in (
            await db.scalars(
                select(TechnologyUnmappedCoordinate).where(
                    TechnologyUnmappedCoordinate.organization_id == organization_id,
                    TechnologyUnmappedCoordinate.candidate_technology_id.is_not(None),
                )
            )
        ).all()
    }
    await db.execute(
        delete(TechnologyUnmappedCoordinate).where(
            TechnologyUnmappedCoordinate.organization_id == organization_id,
            TechnologyUnmappedCoordinate.project_id == project_id,
            TechnologyUnmappedCoordinate.scope == handoff.scope,
        )
    )
    db.add_all(
        TechnologyUnmappedCoordinate(
            organization_id=organization_id,
            project_id=project_id,
            kind=coordinate.kind,
            coordinate=coordinate.coordinate,
            scope=handoff.scope,
            scan_id=handoff.scan_id,
            candidate_technology_id=prior_candidates.get((coordinate.kind, coordinate.coordinate)),
        )
        for coordinate in handoff.unmapped_coordinates
    )
    return response, before
