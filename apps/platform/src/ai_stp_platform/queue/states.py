"""Job queue enumerations and transition sets (SPEC-018).

This is the queue machine and is deliberately distinct from the mutating
operation machine in docs/contracts/operation.md.
"""

from __future__ import annotations

from datetime import datetime
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
    DELIVER_CORPORATE_INVITATION = "deliver_corporate_invitation"
    REPOSITORY_METRICS = "repository_metrics"
    GITHUB_ARCHIVE = "github_archive"
    GITLAB_TECHNOLOGY_SCAN = "gitlab_technology_scan"
    CATALOG_ENRICHMENT = "catalog_enrichment"
    SEO_BUILD = "seo_build"
    SEO_ENRICH = "seo_enrich"
    OFFICIAL_UPSTREAM_SYNC = "official_upstream_sync"
    TELEMETRY_RETENTION = "telemetry_retention"


class Visibility(StrEnum):
    """Visibility parameter carried by an upload job."""

    PUBLIC = "public"
    PRIVATE = "private"


class PermanentJobFailure(ValueError):
    """The job can never succeed — dead-letter immediately, skip retries.

    Raised for structurally invalid payloads and permanent preconditions.
    A retry cannot repair these, so burning attempts only delays the
    durable verdict.
    """


class RetryAfterJobFailure(Exception):
    """A transient failure that cannot clear before a known moment.

    The upstream named when to retry, such as a rate-limit reset: the retry is
    scheduled then instead of on the shorter backoff, and still consumes an
    attempt, so a limit that never lifts still ends in dead-letter.
    """

    def __init__(self, message: str, *, not_before: datetime) -> None:
        super().__init__(message)
        self.not_before = not_before


CLAIMABLE_STATES: tuple[JobState, ...] = (JobState.QUEUED, JobState.RETRY_SCHEDULED)
TERMINAL_STATES: tuple[JobState, ...] = (
    JobState.SUCCEEDED,
    JobState.DEAD_LETTER,
    JobState.CANCELLED,
)
