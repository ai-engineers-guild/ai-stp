"""Map bounded forge language observations to proposed technology scan input."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_contracts.technology import (
    TechnologyEvidence,
    TechnologyObservation,
    TechnologyScanHandoff,
    TechnologyUsageFact,
)
from ai_stp_platform.technology_models import TechnologyCoordinateMapping


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
            raise ApiError(ErrorCategory.CONFLICT, "forge language mapping is ambiguous")
        alias_ids[key] = mapping.technology_id
    detector = f"{provider}-languages-v1"
    evidence_by_id: dict[str, list[TechnologyEvidence]] = {}
    for language, share in sorted(languages.items()):
        technology_id = alias_ids.get(language.casefold())
        if technology_id is None or share <= 0:
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
    )
