"""Map bounded forge language observations to proposed technology scan input."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.technology import (
    TechnologyDetectedCoordinate,
    TechnologyEvidence,
    TechnologyObservation,
    TechnologyScanHandoff,
    TechnologyUnmappedCoordinate,
    TechnologyUsageFact,
)
from ai_stp_platform.technology_models import TechnologyCoordinateMapping
from ai_stp_sources import tech_detect

#: The wire's coordinate alphabet — names outside it (F#, C#) cannot be carried.
_COORDINATE = re.compile(r"^[A-Za-z0-9._:/@+*-]+$")

#: One finding's evidence stays bounded; the detector already dedupes paths.
_MAX_EVIDENCE = 64

#: Version claims rank by how directly they were seen: an observed lockfile
#: version outranks a declared range, which outranks no claim at all.
_VERSION_RANK = {"observed_version": 0, "declared_range": 1, "unknown": 2}


@dataclass
class _Slot:
    """Per (technology, context) accumulator for one handoff."""

    version: str | None
    version_kind: Literal["unknown", "declared_range", "observed_version"]
    evidence: list[TechnologyEvidence]

    def __init__(self) -> None:
        self.version = None
        self.version_kind = "unknown"
        self.evidence = []


async def language_handoff(
    db: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    scan_id: str,
    mapping_version: str,
    provider: str,
    provider_project_id: str,
    repository_id: int,
    head: str,
    observed_at: str,
    languages: dict[str, float],
) -> TechnologyScanHandoff:
    mappings = await db.scalars(
        select(TechnologyCoordinateMapping).where(
            TechnologyCoordinateMapping.organization_id == organization_id,
            TechnologyCoordinateMapping.version == mapping_version,
            TechnologyCoordinateMapping.kind == "alias",
        )
    )
    alias_ids: dict[str, str] = {}
    for mapping in mappings:
        key = mapping.coordinate.casefold()
        if key in alias_ids and alias_ids[key] != mapping.technology_id:
            raise ValueError("forge language mapping is ambiguous")
        alias_ids[key] = mapping.technology_id
    detector = f"{provider}-languages-v1"
    evidence_by_id: dict[str, list[TechnologyEvidence]] = {}
    unmapped: list[TechnologyUnmappedCoordinate] = []
    for language, share in sorted(languages.items()):
        coordinate = language.casefold()
        technology_id = alias_ids.get(coordinate)
        if technology_id is None:
            if share > 0 and _COORDINATE.match(coordinate):
                unmapped.append(TechnologyUnmappedCoordinate(kind="alias", coordinate=coordinate))
            continue
        if share <= 0:
            continue
        evidence_by_id.setdefault(technology_id, []).append(
            TechnologyEvidence(
                source="forge_language",
                reference=f"{provider}:{repository_id}",
                observed_at=observed_at,
                source_revision=head,
                confidence=0.9,
                detector_version=detector,
                mapping_version=mapping_version,
            )
        )
    return TechnologyScanHandoff(
        organization_id=organization_id,
        project_id=project_id,
        scan_id=scan_id,
        scope=f"{provider}/{provider_project_id}",
        complete=True,
        detector_version=detector,
        mapping_version=mapping_version,
        observations=[
            TechnologyObservation(
                technology_id=technology_id,
                fact=TechnologyUsageFact(context="development", evidence=evidence),
            )
            for technology_id, evidence in sorted(evidence_by_id.items())
        ],
        unmapped_coordinates=unmapped,
    )


async def detection_handoff(
    db: AsyncSession,
    *,
    organization_id: str,
    project_id: str,
    scan_id: str,
    mapping_version: str,
    provider: str,
    provider_project_id: str,
    head: str,
    observed_at: str,
    detections: Iterable[tech_detect.Detection],
    complete: bool,
) -> TechnologyScanHandoff:
    """Fold repository-content detections into a scan handoff.

    The same mapping snapshot the language path applies resolves each
    coordinate; an ambiguous or absent mapping keeps the finding in
    ``unmapped_coordinates`` for review rather than guessing an identity.
    """
    detections = tuple(detections)
    mappings = await db.scalars(
        select(TechnologyCoordinateMapping).where(
            TechnologyCoordinateMapping.organization_id == organization_id,
            TechnologyCoordinateMapping.version == mapping_version,
        )
    )
    snapshot = tech_detect.MappingSnapshot(
        version=mapping_version,
        entries=tuple((row.kind, row.coordinate, row.technology_id) for row in mappings),
    )
    detector = f"repository-content-v{tech_detect.DETECTOR_VERSION}"
    grouped: dict[tuple[str, tech_detect.UsageContext], _Slot] = {}
    unmapped: dict[tuple[str, str], tech_detect.Detection] = {}
    for detection in detections:
        technology_id = snapshot.resolve(detection.kind, detection.coordinate)
        if technology_id is None:
            if _COORDINATE.fullmatch(detection.coordinate):
                held = unmapped.get((detection.kind, detection.coordinate))
                if held is None or _VERSION_RANK.get(detection.version_kind, 3) < _VERSION_RANK.get(
                    held.version_kind, 3
                ):
                    unmapped[(detection.kind, detection.coordinate)] = detection
            continue
        key = (technology_id, detection.context)
        slot = grouped.setdefault(key, _Slot())
        for trace in detection.traces:
            if len(slot.evidence) < _MAX_EVIDENCE:
                slot.evidence.append(
                    TechnologyEvidence(
                        source=trace.source,
                        path=trace.path,
                        reference=trace.reference,
                        observed_at=observed_at,
                        source_revision=head,
                        confidence=trace.confidence,
                        detector_version=detector,
                        mapping_version=mapping_version,
                    )
                )
        if _VERSION_RANK.get(detection.version_kind, 3) < _VERSION_RANK.get(slot.version_kind, 3):
            slot.version = detection.version
            slot.version_kind = detection.version_kind
    return TechnologyScanHandoff(
        organization_id=organization_id,
        project_id=project_id,
        scan_id=scan_id,
        scope=f"{provider}/{provider_project_id}",
        complete=complete and len(detections) <= 4096 and len(unmapped) <= 512,
        detector_version=detector,
        mapping_version=mapping_version,
        observations=[
            TechnologyObservation(
                technology_id=technology_id,
                fact=TechnologyUsageFact(
                    context=context,
                    version=slot.version if slot.version_kind != "unknown" else None,
                    version_kind=slot.version_kind,
                    evidence=slot.evidence,
                ),
            )
            for (technology_id, context), slot in sorted(grouped.items())
        ],
        coordinates=[
            TechnologyDetectedCoordinate(
                kind=item.kind,
                coordinate=item.coordinate,
                context=item.context,
                technology_id=snapshot.resolve(item.kind, item.coordinate),
                version=item.version,
                version_kind=item.version_kind,
                evidence=[
                    TechnologyEvidence(
                        source=trace.source,
                        path=trace.path,
                        reference=trace.reference,
                        observed_at=observed_at,
                        source_revision=head,
                        confidence=trace.confidence,
                        detector_version=detector,
                        mapping_version=mapping_version,
                    )
                    for trace in item.traces[:8]
                ],
            )
            for item in detections
            if _COORDINATE.fullmatch(item.coordinate)
        ][:4096],
        unmapped_coordinates=[
            TechnologyUnmappedCoordinate(
                kind=detection.kind,
                coordinate=detection.coordinate,
                context=detection.context,
                version=detection.version,
                version_kind=detection.version_kind,
                evidence=[
                    TechnologyEvidence(
                        source=trace.source,
                        path=trace.path,
                        reference=trace.reference,
                        observed_at=observed_at,
                        source_revision=head,
                        confidence=trace.confidence,
                        detector_version=detector,
                        mapping_version=mapping_version,
                    )
                    for trace in detection.traces[:8]
                ],
            )
            for detection in (unmapped[key] for key in sorted(unmapped)[:512])
        ],
    )
