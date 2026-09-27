"""Map bounded forge language observations to proposed technology scan input."""

from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_contracts.technology import TechnologyScanHandoff
from ai_stp_platform.technology_forge import language_handoff as _language_handoff


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
    try:
        return await _language_handoff(
            db,
            organization_id=organization_id,
            project_id=project_id,
            scan_id=scan_id,
            mapping_version=mapping_version,
            provider=provider,
            provider_project_id=provider_project_id,
            repository_id=repository_id,
            head=head,
            observed_at=observed_at,
            languages=languages,
        )
    except ValueError:
        raise ApiError(ErrorCategory.CONFLICT, "forge language mapping is ambiguous") from None
