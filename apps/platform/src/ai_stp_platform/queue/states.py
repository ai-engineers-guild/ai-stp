"""Job queue enumerations and transition sets (SPEC-018).

This is the queue machine and is deliberately distinct from the mutating
operation machine in docs/contracts/operation.md.
"""

from __future__ import annotations

from enum import StrEnum


class JobState(StrEnum):
    """Lifecycle states of a queued job."""

    QUEUED = "queued"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    DEAD_LETTER = "dead_letter"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    """Closed registry of job types (SPEC-018 REQ-1802, SPEC-026).

    Object signing/write is a step inside upload/update/publish, not its own type.
    """

    UPLOAD = "upload"
    UPDATE = "update"
    VALIDATE = "validate"
    PUBLISH = "publish"
    REEVALUATE_ELIGIBILITY = "reevaluate_eligibility"
    DELIVER_INVITATION = "deliver_invitation"
    REPOSITORY_METRICS = "repository_metrics"
    GITHUB_ARCHIVE = "github_archive"
    CATALOG_ENRICHMENT = "catalog_enrichment"
    SEO_BUILD = "seo_build"
    SEO_ENRICH = "seo_enrich"
    OFFICIAL_UPSTREAM_SYNC = "official_upstream_sync"


class Visibility(StrEnum):
    """Visibility parameter carried by an upload job."""

    PUBLIC = "public"
    PRIVATE = "private"


CLAIMABLE_STATES: tuple[JobState, ...] = (JobState.QUEUED, JobState.RETRY_SCHEDULED)
TERMINAL_STATES: tuple[JobState, ...] = (
    JobState.SUCCEEDED,
    JobState.DEAD_LETTER,
    JobState.CANCELLED,
)
