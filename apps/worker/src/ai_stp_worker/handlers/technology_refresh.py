"""Daily technology refresh for linked GitLab projects (SPEC-081).

The job runs as the system actor: it re-observes the bounded forge language
signal for each linked project whose recorded head is current, builds the
same handoff the enrich endpoint would, and folds it into usage facts through
the shared scan merge. It never resolves identities itself: a project whose
provider head moved past the recorded observation is skipped until discovery
re-pins it.

Payload: ``{"organization_id": "org_..."}``; optional ``mapping_version``
pins the snapshot, ``provider_project_id`` limits the sweep to one link.

GitLab connections come from ``AI_STP_GITLAB_CONNECTIONS`` (the same JSON
mapping the API parses): ``{organization_id: {base_url, token,
allowed_hosts}}``. GitHub enrichment is bound to a user's connector session
and stays request-driven.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.technology import (
    TechnologyObservation,
    TechnologyScanHandoff,
    TechnologyScanResult,
)
from ai_stp_contracts.technology_seed import SEED_COORDINATES_VERSION
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.gitlab_client import GitLabClient, GitLabError
from ai_stp_platform.models import AuditEvent
from ai_stp_platform.organization_models import (
    CorporateProject,
    Organization,
    ProjectIdentity,
    ProjectLink,
)
from ai_stp_platform.queue.engine import enqueue
from ai_stp_platform.queue.states import JobType
from ai_stp_platform.technology_forge import language_handoff
from ai_stp_platform.technology_models import (
    TechnologyCoordinateMapping,
    TechnologyScan,
)
from ai_stp_platform.technology_scan_merge import (
    merge_scan_facts,
    resolve_technology_redirect,
)
from ai_stp_platform.tenant_scope import set_tenant_scope

_MAX_PROJECTS = 128


async def enqueue_daily_refresh(session: AsyncSession) -> None:
    """Enqueue one refresh job per configured tenant per UTC day.

    Idempotency keys make a worker restart inside the same day a no-op; a
    tenant whose connection was removed produces a job that exits clean.
    """
    today = datetime.now(UTC).date().isoformat()
    for organization_id in sorted(_connections()):
        await enqueue(
            session,
            job_type=JobType.TECHNOLOGY_REFRESH,
            payload={"organization_id": organization_id, "utc_day": today},
            idempotency_key=f"technology-refresh:{organization_id}:{today}",
        )


def _connections() -> dict[str, dict[str, Any]]:
    raw = os.environ.get("AI_STP_GITLAB_CONNECTIONS")
    if not raw:
        return {}
    try:
        parsed: object = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    entries = cast(dict[object, object], parsed)
    return {
        str(key): cast(dict[str, Any], value)
        for key, value in entries.items()
        if isinstance(value, dict)
    }


async def _mapping_version(
    session: AsyncSession, organization_id: str, override: str | None
) -> str | None:
    """The snapshot a refresh resolves against: explicit, last used, or seed."""
    if override:
        return override
    latest_revision = -1
    latest_version: str | None = None
    scans = await session.scalars(
        select(TechnologyScan).where(TechnologyScan.organization_id == organization_id)
    )
    for row in scans:
        try:
            result = TechnologyScanResult.model_validate(row.handoff["result"])
            handoff = TechnologyScanHandoff.model_validate(row.handoff["handoff"])
        except ValueError:
            continue
        if result.project_revision > latest_revision:
            latest_revision = result.project_revision
            latest_version = handoff.mapping_version
    if latest_version is not None:
        return latest_version
    seeded = await session.scalar(
        select(func.count())
        .select_from(TechnologyCoordinateMapping)
        .where(TechnologyCoordinateMapping.organization_id == organization_id)
    )
    return SEED_COORDINATES_VERSION if seeded else None


async def handle_technology_refresh(session: AsyncSession, payload: Mapping[str, object]) -> None:
    """Re-observe forge languages for linked GitLab projects of one tenant."""
    organization_id = payload.get("organization_id")
    if not isinstance(organization_id, str) or not organization_id:
        raise ValueError("technology_refresh requires organization_id")
    config = _connections().get(organization_id)
    if not isinstance(config, dict):
        return
    try:
        client = GitLabClient(
            str(config.get("base_url", "")),
            allowed_hosts=config.get("allowed_hosts") or (),
        )
    except GitLabError:
        return
    token = config.get("token")
    if not isinstance(token, str) or not token:
        return
    await set_tenant_scope(session, organization_id)
    organization = await session.scalar(
        select(Organization).where(Organization.id == organization_id).with_for_update()
    )
    if organization is None or organization.state != "active":
        return
    override = payload.get("mapping_version")
    mapping_version = await _mapping_version(
        session, organization_id, override if isinstance(override, str) else None
    )
    if mapping_version is None:
        return
    rows = (
        await session.execute(
            select(ProjectLink, ProjectIdentity, CorporateProject)
            .join(
                ProjectIdentity,
                ProjectIdentity.id == ProjectLink.provider_project_id,
            )
            .join(
                CorporateProject,
                CorporateProject.id == ProjectLink.remote_project_id,
            )
            .where(
                ProjectLink.organization_id == organization_id,
                ProjectLink.state == "linked",
                ProjectIdentity.organization_id == organization_id,
                ProjectIdentity.namespace == "provider",
                ProjectIdentity.provider_kind == "gitlab",
                ProjectIdentity.provider_installation_id == client.base_url,
                ProjectIdentity.state == "active",
                CorporateProject.organization_id == organization_id,
                CorporateProject.lifecycle == "active",
            )
            .order_by(ProjectLink.id)
            .limit(_MAX_PROJECTS)
        )
    ).all()
    refreshed = 0
    skipped = 0
    failed = 0
    for link, identity, project in rows:
        if (
            identity.immutable_repository_id is None
            or identity.provider_default_branch is None
            or identity.provider_observed_revision is None
            or identity.observed_at is None
        ):
            skipped += 1
            continue
        try:
            repository_id = int(identity.immutable_repository_id)
        except ValueError:
            skipped += 1
            continue
        scope = f"gitlab/{link.provider_project_id}"
        try:
            head = await client.head_revision(
                repository_id, identity.provider_default_branch, token=token
            )
            if head != identity.provider_observed_revision:
                skipped += 1  # discovery must re-pin the observation first
                continue
            prior = await session.scalars(
                select(TechnologyScan).where(
                    TechnologyScan.organization_id == organization_id,
                    TechnologyScan.project_id == project.id,
                )
            )
            current = False
            for row in prior:
                try:
                    previous = TechnologyScanHandoff.model_validate(row.handoff["handoff"])
                except ValueError:
                    continue
                if previous.scope != scope:
                    continue
                if any(
                    entry.source_revision == head
                    for observation in previous.observations
                    for entry in observation.fact.evidence
                ):
                    current = True
                    break
            if current:
                continue  # the forge signal for this head is already merged
            languages = await client.languages(repository_id, token=token)
        except GitLabError:
            failed += 1
            continue
        handoff = await language_handoff(
            session,
            organization_id=organization_id,
            project_id=project.id,
            scan_id=new_id("scan"),
            mapping_version=mapping_version,
            provider="gitlab",
            provider_project_id=str(link.provider_project_id),
            repository_id=repository_id,
            head=head,
            observed_at=format_timestamp(identity.observed_at),
            languages=languages,
        )
        observations: dict[tuple[str, str], TechnologyObservation] = {}
        try:
            for observation in handoff.observations:
                resolved = await resolve_technology_redirect(
                    session, organization_id, observation.technology_id
                )
                key = (resolved, observation.fact.context)
                if key in observations:
                    raise ValueError("scan technology/context is ambiguous")
                observations[key] = TechnologyObservation(
                    technology_id=resolved, fact=observation.fact
                )
        except (LookupError, ValueError):
            failed += 1
            continue
        await merge_scan_facts(
            session,
            organization_id=organization_id,
            organization=organization,
            project=project,
            handoff=handoff,
            observations=observations,
            digest=digest_canonical(
                "ai-stp:technology_scan:v1",
                {
                    "organization_id": organization_id,
                    "project_id": project.id,
                    "handoff": handoff.model_dump(mode="json"),
                },
            ),
            resolve_technology=lambda technology_id: resolve_technology_redirect(
                session, organization_id, technology_id
            ),
        )
        refreshed += 1
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_type="system",
            actor_id="worker:technology_refresh",
            action="technology.refresh",
            target_table="technology_scan",
            target_id=organization_id,
            payload={
                "refreshed": refreshed,
                "skipped": skipped,
                "failed": failed,
                "mapping_version": mapping_version,
                "at": format_timestamp(datetime.now(UTC)),
            },
        )
    )
