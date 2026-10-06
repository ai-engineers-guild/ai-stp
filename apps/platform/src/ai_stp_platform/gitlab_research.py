"""Asynchronous technology scan over a linked GitLab project.

The worker path shares the synchronous enrich invariants: the provider
identity, project link and observed head are rechecked live, languages map
through the immutable snapshot, and ``merge_scan_facts`` stays the only writer.
Authorization already ran twice — at enqueue (``technology.scan.publish``) and
inside the tenant envelope check — so this module never trusts caller context.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.technology import TechnologyObservation
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.gitlab_client import GitLabClient, GitLabError
from ai_stp_platform.gitlab_settings import GitLabSettings
from ai_stp_platform.gitlab_sources import request_digest
from ai_stp_platform.organization_models import (
    CorporateProject,
    Organization,
    ProjectIdentity,
    ProjectLink,
)
from ai_stp_platform.queue.states import PermanentJobFailure
from ai_stp_platform.technology_forge import language_handoff
from ai_stp_platform.technology_models import (
    Technology,
    TechnologyCoordinateMapping,
    TechnologyScan,
)
from ai_stp_platform.technology_scan_merge import merge_scan_facts

_PROVIDER = "gitlab"


async def _resolve_technology(db: AsyncSession, organization_id: str, technology_id: str) -> str:
    """Redirect traversal only; the envelope already authorized the scan."""
    seen: set[str] = set()
    current = technology_id
    while current not in seen:
        seen.add(current)
        row = await db.get(Technology, (organization_id, current))
        if row is None:
            raise PermanentJobFailure("technology endpoint is unavailable")
        if row.redirect_id is None:
            return current
        current = row.redirect_id
    raise PermanentJobFailure("technology redirect cycle")


async def scan_linked_gitlab_project(
    db: AsyncSession,
    *,
    organization_id: str,
    provider_project_id: str,
    project_id: str,
    scan_id: str,
    mapping_version: str,
    settings: GitLabSettings,
) -> str:
    """Scan one linked GitLab project; returns ``"applied"`` or ``"skipped"``."""
    connection = settings.connection_for(organization_id)
    if connection is None:
        raise PermanentJobFailure("gitlab connection is not configured")
    try:
        client = GitLabClient(
            connection.base_url,
            allowed_hosts=connection.allowed_hosts,
            verify=settings.tls_verify(),
        )
    except GitLabError:
        raise PermanentJobFailure("gitlab connection is not configured") from None
    token = connection.token.get_secret_value()

    identity = await db.scalar(
        select(ProjectIdentity).where(
            ProjectIdentity.organization_id == organization_id,
            ProjectIdentity.id == provider_project_id,
            ProjectIdentity.namespace == "provider",
            ProjectIdentity.provider_kind == _PROVIDER,
            ProjectIdentity.state == "active",
        )
    )
    link = await db.scalar(
        select(ProjectLink).where(
            ProjectLink.organization_id == organization_id,
            ProjectLink.provider_project_id == provider_project_id,
            ProjectLink.remote_project_id == project_id,
            ProjectLink.state == "linked",
        )
    )
    project = await db.scalar(
        select(CorporateProject).where(
            CorporateProject.organization_id == organization_id,
            CorporateProject.id == project_id,
            CorporateProject.lifecycle == "active",
        )
    )
    remote_identity = await db.get(ProjectIdentity, project_id)
    if (
        identity is None
        or link is None
        or project is None
        or remote_identity is None
        or remote_identity.organization_id != organization_id
        or remote_identity.state != "active"
        or identity.provider_installation_id != client.base_url
    ):
        raise PermanentJobFailure("linked GitLab project is unavailable")
    if identity.provider_default_branch is None or identity.provider_observed_revision is None:
        raise PermanentJobFailure("gitlab default branch has no observed revision")
    try:
        repository_id = int(identity.immutable_repository_id or "")
    except ValueError:
        raise PermanentJobFailure("gitlab repository identity is incomplete") from None
    try:
        head = await client.head_revision(
            repository_id, identity.provider_default_branch, token=token
        )
        languages = await client.languages(repository_id, token=token)
    except GitLabError as error:
        if error.reason == "gitlab_rate_limited":
            raise
        raise PermanentJobFailure(f"gitlab scan fetch failed: {error.reason}") from error
    if head != identity.provider_observed_revision:
        raise PermanentJobFailure("gitlab observation requires refresh")
    if identity.observed_at is None:
        raise PermanentJobFailure("gitlab observation is incomplete")

    try:
        handoff = await language_handoff(
            db,
            organization_id=organization_id,
            project_id=project_id,
            scan_id=scan_id,
            mapping_version=mapping_version,
            provider=_PROVIDER,
            provider_project_id=provider_project_id,
            repository_id=repository_id,
            head=head,
            observed_at=format_timestamp(identity.observed_at),
            languages=languages,
        )
    except ValueError:
        raise PermanentJobFailure("forge language mapping is ambiguous") from None

    digest = request_digest(
        {
            "organization_id": organization_id,
            "project_id": project_id,
            "provider_project_id": provider_project_id,
            "scan_id": scan_id,
            "mapping_version": mapping_version,
            "handoff": handoff.model_dump(mode="json"),
        }
    )
    retained = await db.get(TechnologyScan, (organization_id, scan_id))
    if retained is not None:
        if retained.project_id != project_id or retained.fingerprint != digest:
            raise PermanentJobFailure("scan ID was reused")
        return "skipped"

    mappings = list(
        await db.scalars(
            select(TechnologyCoordinateMapping).where(
                TechnologyCoordinateMapping.organization_id == organization_id,
                TechnologyCoordinateMapping.version == mapping_version,
            )
        )
    )
    if not mappings:
        raise PermanentJobFailure("scan mapping snapshot is unavailable")
    mapped_ids = {
        await _resolve_technology(db, organization_id, entry.technology_id) for entry in mappings
    }

    observations: dict[tuple[str, str], TechnologyObservation] = {}
    for observation in handoff.observations:
        current = await _resolve_technology(db, organization_id, observation.technology_id)
        if current not in mapped_ids:
            raise PermanentJobFailure("observation is outside its mapping snapshot")
        if not observation.fact.evidence or any(
            entry.source == "manual"
            or entry.detector_version != handoff.detector_version
            or entry.mapping_version != handoff.mapping_version
            for entry in observation.fact.evidence
        ):
            raise PermanentJobFailure("scan evidence must name its detector and mapping")
        key = (current, observation.fact.context)
        if key in observations:
            raise PermanentJobFailure("scan technology/context is ambiguous")
        observations[key] = observation

    organization = await db.scalar(
        select(Organization).where(Organization.id == organization_id).with_for_update()
    )
    locked_link = await db.scalar(
        select(ProjectLink)
        .where(
            ProjectLink.organization_id == organization_id,
            ProjectLink.provider_project_id == provider_project_id,
            ProjectLink.remote_project_id == project_id,
        )
        .with_for_update()
    )
    await db.refresh(identity)
    if (
        organization is None
        or organization.state != "active"
        or locked_link is None
        or locked_link.state != "linked"
        or identity.state != "active"
        or identity.provider_observed_revision != head
    ):
        raise PermanentJobFailure("gitlab observation or project link changed")

    await merge_scan_facts(
        db,
        organization_id=organization_id,
        organization=organization,
        project=project,
        handoff=handoff,
        observations=observations,
        digest=digest,
        resolve_technology=lambda technology_id: _resolve_technology(
            db, organization_id, technology_id
        ),
        authorize_pair=None,
    )
    return "applied"
