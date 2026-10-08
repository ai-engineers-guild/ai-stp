"""Payload parsing shared by the repository technology-scan job handlers.

Both job types carry the same fields — the provider differs only in which
adapter the handler constructs, so the validation lives once here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from ai_stp_platform.queue.engine import TENANT_ENVELOPE_KEY
from ai_stp_platform.queue.states import PermanentJobFailure


@dataclass(frozen=True)
class ScanJob:
    """Validated scan-job fields plus the tenant envelope that queued them."""

    organization_id: str
    provider_project_id: str
    project_id: str
    scan_id: str
    mapping_version: str
    envelope: Mapping[str, object]


def _field(payload: Mapping[str, object], name: str, *, job_label: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise PermanentJobFailure(f"{job_label} requires {name}")
    return value


def parse_scan_job(payload: Mapping[str, object], *, job_label: str) -> ScanJob:
    envelope = payload.get(TENANT_ENVELOPE_KEY)
    if not isinstance(envelope, Mapping):
        raise PermanentJobFailure(f"{job_label} requires a tenant envelope")
    typed = cast(Mapping[str, object], envelope)
    organization_id = typed.get("organization_id")
    if not isinstance(organization_id, str) or not organization_id:
        raise PermanentJobFailure(f"{job_label} requires organization_id")
    return ScanJob(
        organization_id=organization_id,
        provider_project_id=_field(payload, "provider_project_id", job_label=job_label),
        project_id=_field(payload, "project_id", job_label=job_label),
        scan_id=_field(payload, "scan_id", job_label=job_label),
        mapping_version=_field(payload, "mapping_version", job_label=job_label),
        envelope=typed,
    )


def user_principal(job: ScanJob, *, job_label: str) -> str:
    """The user whose connector token the scan authorizes itself with."""
    principal_id = job.envelope.get("principal_id")
    if job.envelope.get("principal_type") != "user" or not isinstance(principal_id, str):
        raise PermanentJobFailure(f"{job_label} requires a user principal")
    return principal_id


__all__ = [
    "ScanJob",
    "parse_scan_job",
    "user_principal",
]
