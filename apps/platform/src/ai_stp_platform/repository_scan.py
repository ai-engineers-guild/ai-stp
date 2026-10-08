"""Shared repository-scan pipeline for linked provider projects.

GitHub and GitLab scans run one identical invariant sequence; only the
adapter differs. The adapter validates the stored provider identity,
fetches the repository snapshot (default branch, live head, archive bytes),
proves under lock that the identity still names the repository it fetched,
and owns the request-digest namespace. Everything else — project-link
state, mapping-snapshot membership, evidence policy, concurrency locks,
the merge itself — is provider-agnostic and lives here once.

Transient provider failures (rate limit, upstream outage) propagate from the
adapter unchanged so the queue retries on backoff; states a retry cannot
repair arrive as ``PermanentJobFailure`` and dead-letter the job.
Authorization already ran twice — at enqueue and inside the tenant envelope
check — so this module never trusts caller context.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.technology import TechnologyObservation
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.organization_models import (
    CorporateProject,
    Organization,
    ProjectIdentity,
    ProjectLink,
)
from ai_stp_platform.queue.states import PermanentJobFailure
from ai_stp_platform.technology_forge import detection_handoff
from ai_stp_platform.technology_models import (
    Technology,
    TechnologyCoordinateMapping,
    TechnologyScan,
)
from ai_stp_platform.technology_scan_merge import merge_scan_facts
from ai_stp_sources.errors import SourceError
from ai_stp_sources.tech_detect import detect_archive


@dataclass(frozen=True)
class RepositorySnapshot:
    """One immutable repository state an adapter fetched for scanning."""

    repository: str
    branch: str
    head: str
    archive: bytes
    observed_at: datetime


class RepositoryScanAdapter(Protocol):
    """The provider-specific half of a repository scan.

    Implementations raise ``PermanentJobFailure`` for states a retry cannot
    repair and let transient provider errors propagate unchanged so the
    queue schedules another attempt.
    """

    provider: str

    def validate_identity(self, identity: ProjectIdentity) -> None:
        """Permanent integrity checks on the stored provider identity."""
        ...

    async def fetch_snapshot(
        self, db: AsyncSession, identity: ProjectIdentity
    ) -> RepositorySnapshot:
        """Read the repository's live head and archive through provider APIs."""
        ...

    def still_bound(self, identity: ProjectIdentity, snapshot: RepositorySnapshot) -> bool:
        """The refreshed identity still names what ``fetch_snapshot`` read."""
        ...

    def request_digest(self, value: object) -> str:
        """Provider-namespaced scan fingerprint for replay detection."""
        ...


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


def _head_is_current(identity: ProjectIdentity, head: str) -> bool:
    """A stored observation pins the scan to the revision it recorded.

    Providers that record an observation at link time require the live head
    to match it; providers that do not record one scan whatever head the
    adapter resolved.
    """
    return identity.provider_observed_revision is None or (
        identity.provider_observed_revision == head
    )


async def scan_linked_repository(
    db: AsyncSession,
    *,
    organization_id: str,
    provider_project_id: str,
    project_id: str,
    scan_id: str,
    mapping_version: str,
    adapter: RepositoryScanAdapter,
) -> Literal["applied", "skipped"]:
    """Scan one linked repository; returns ``"applied"`` or ``"skipped"``."""
    identity = await db.scalar(
        select(ProjectIdentity).where(
            ProjectIdentity.organization_id == organization_id,
            ProjectIdentity.id == provider_project_id,
            ProjectIdentity.namespace == "provider",
            ProjectIdentity.provider_kind == adapter.provider,
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
    ):
        raise PermanentJobFailure(f"linked {adapter.provider} project is unavailable")
    adapter.validate_identity(identity)

    snapshot = await adapter.fetch_snapshot(db, identity)
    if not _head_is_current(identity, snapshot.head):
        raise PermanentJobFailure(f"{adapter.provider} observation requires refresh")
    try:
        detected = detect_archive(snapshot.archive)
    except SourceError as error:
        raise PermanentJobFailure(
            f"{adapter.provider} archive is unusable: {error.code}"
        ) from error

    handoff = await detection_handoff(
        db,
        organization_id=organization_id,
        project_id=project_id,
        scan_id=scan_id,
        mapping_version=mapping_version,
        provider=adapter.provider,
        provider_project_id=provider_project_id,
        head=snapshot.head,
        observed_at=format_timestamp(snapshot.observed_at),
        detections=detected.detections,
        complete=detected.complete,
    )

    digest = adapter.request_digest(
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
        or not adapter.still_bound(identity, snapshot)
        or not _head_is_current(identity, snapshot.head)
    ):
        raise PermanentJobFailure(f"{adapter.provider} observation or project link changed")

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
        provenance={
            "source": adapter.provider,
            "repository": snapshot.repository,
            "branch": snapshot.branch,
            "commit": snapshot.head,
        },
    )
    return "applied"


__all__ = [
    "RepositoryScanAdapter",
    "RepositorySnapshot",
    "scan_linked_repository",
]
