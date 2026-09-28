"""Runtime usage ingestion, scoped aggregation, drill-down, and export.

The service is deliberately free of HTTP concerns: the corporate slice resolves
the caller and the permission; this module resolves the *employee set* the
caller may see, applies the closed filters, and writes or reads the coordinate-
only tables. Retention, redaction policy, and revocation belong to the
telemetry-privacy authority (SPEC-089); this module honours the pinned seam by
reading the policy and revocation tables when they exist and falling back to
documented defaults when the governance stream is not yet integrated.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Final, Literal, cast
from zoneinfo import ZoneInfo

from sqlalchemy import distinct, func, inspect, select, text, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from ai_stp_contracts.runtime_usage import (
    EXPORT_ROW_LIMIT,
    RuntimeUsageAssignedRow,
    RuntimeUsageDayBucket,
    RuntimeUsageEmployeeRow,
    RuntimeUsageEvent,
    RuntimeUsageEventBatch,
    RuntimeUsageEventList,
    RuntimeUsageEventQuery,
    RuntimeUsageEventView,
    RuntimeUsageExportRequest,
    RuntimeUsageExportView,
    RuntimeUsageHourBucket,
    RuntimeUsageIngestResult,
    RuntimeUsageInventoryEmployeeRow,
    RuntimeUsageObjectRow,
    RuntimeUsageReport,
    RuntimeUsageReportQuery,
    RuntimeUsageReportRow,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.assignment_resolution import (
    eligible_assignment_versions,
    select_assignment_winner,
)
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.installation_inventory_models import InstallationInventorySnapshot
from ai_stp_platform.models import CatalogMetadata, Device
from ai_stp_platform.organization_models import (
    CorporateCatalogAssignment,
    CorporateProject,
    CorporateProjectMember,
    CorporateRoleBinding,
    CorporateTeamMember,
    OrganizationMembership,
)
from ai_stp_platform.runtime_usage_models import RuntimeUsageEvent as EventRow
from ai_stp_platform.runtime_usage_models import RuntimeUsageExport as ExportRow
from ai_stp_platform.technology_models import EmployeeTechnology, ProjectTechnologyRelation
from ai_stp_platform.telemetry_policy_models import TelemetryPolicy
from ai_stp_platform.tenant_scope import set_tenant_scope

#: Permission keys seeded as data into the ADR-0179 policy table by migration
#: 0088. Ingest is held by every member role; read is aggregate reporting;
#: events is the separately permissioned drill-down; export is auditable.
PERMISSION_INGEST: Final[str] = "telemetry_usage.ingest"
PERMISSION_READ: Final[str] = "telemetry_usage.read"
PERMISSION_EVENTS: Final[str] = "telemetry_usage.events"
PERMISSION_EXPORT: Final[str] = "telemetry_usage.export"

EXPORT_DIGEST_DOMAIN: Final[str] = "ai-stp:runtime-usage-export:v1"

#: Raw events older than this are invisible to every read and rejected at
#: ingest. The telemetry-privacy policy overrides it once that table exists;
#: until then the default is the boundary `SPEC-088` states.
DEFAULT_RAW_RETENTION_DAYS: Final[int] = 90

#: Clock skew allowance for `invoked_at`: a buffered event is old, never from
#: the future. Future timestamps would poison every windowed aggregate.
MAX_FUTURE_SKEW: Final[timedelta] = timedelta(minutes=5)

_GROUP_COLUMNS: Final[Mapping[str, tuple[object, ...]]] = {
    "component": (
        EventRow.component_kind,
        EventRow.component_stable_id,
        EventRow.component_version,
    ),
    "setup": (EventRow.setup_stable_id, EventRow.setup_version),
    "employee": (EventRow.employee_account_id,),
    "device": (EventRow.device_id,),
    "project": (EventRow.project_id,),
    "harness": (EventRow.harness,),
    "outcome": (EventRow.outcome,),
}

_GOVERNED_POLICY_TABLE: Final[str] = "telemetry_policy"
_GOVERNED_REVOCATION_TABLE: Final[str] = "telemetry_revocation"

_DEDUP_COMPARE_FIELDS: Final[tuple[str, ...]] = (
    "employee_account_id",
    "device_id",
    "project_id",
    "harness",
    "setup_stable_id",
    "setup_version",
    "setup_passport_digest",
    "component_kind",
    "component_stable_id",
    "component_version",
    "component_passport_digest",
    "activity_kind",
    "schema_version",
)


@dataclass(frozen=True)
class UsageScope:
    """What one principal may see. ``employees=None`` means organization-wide.

    ``denied`` is the empty answer: the principal holds the permission nowhere,
    and the slice maps it to the original 403 rather than an empty report.
    """

    employees: frozenset[str] | None
    team_ids: frozenset[str] = frozenset()

    @property
    def denied(self) -> bool:
        return self.employees == frozenset() and not self.team_ids


def _moment(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _stamp(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return format_timestamp(moment)


async def _has_table(session: AsyncSession, name: str) -> bool:
    """Whether a governance table exists, so the privacy seam is optional.

    The privacy stream owns the policy and revocation tables; this stream must
    run and be verifiable before that merge, so the seam degrades to defaults
    rather than importing a module that is not on this branch.
    """
    return await session.run_sync(
        lambda sync_session: inspect(sync_session.get_bind()).has_table(name)
    )


async def raw_retention_days(session: AsyncSession, *, organization_id: str) -> int:
    """The tenant's raw-event retention, or the documented default.

    `telemetry_policy` is the privacy stream's authority table. When it exists
    the tenant's `raw_retention_days` governs; when it does not, the default
    keeps the retention boundary testable and deterministic either way.
    """
    if not await _has_table(session, _GOVERNED_POLICY_TABLE):
        return DEFAULT_RAW_RETENTION_DAYS
    days = await session.scalar(
        text(
            "SELECT raw_retention_days FROM telemetry_policy "
            "WHERE organization_id = :organization_id"
        ),
        {"organization_id": organization_id},
    )
    return int(days) if days else DEFAULT_RAW_RETENTION_DAYS


async def revoked_subjects(
    session: AsyncSession, *, organization_id: str
) -> frozenset[tuple[str, str]]:
    """Revoked or deleted subjects, when the privacy authority table exists."""
    if not await _has_table(session, _GOVERNED_REVOCATION_TABLE):
        return frozenset()
    rows = (
        await session.execute(
            text(
                "SELECT subject_kind, subject_id FROM telemetry_revocation "
                "WHERE organization_id = :organization_id "
                "AND state IN ('revoked', 'deleted')"
            ),
            {"organization_id": organization_id},
        )
    ).all()
    return frozenset((str(kind), str(subject)) for kind, subject in rows)


async def resolve_scope(
    session: AsyncSession,
    *,
    organization_id: str,
    principal_id: str,
    permission: str,
) -> UsageScope:
    """The employee and team set the principal may see.

    Organization scope answers ``employees=None``. Otherwise the caller's own
    events plus the active members of every team where a team-scoped binding
    grants the permission. ``denied`` means "no permission anywhere"; the slice
    maps it to the original denial.
    """
    if await has_corporate_permission(
        session,
        organization_id=organization_id,
        principal_type="user",
        principal_id=principal_id,
        permission=permission,
        scope_kind="organization",
    ):
        return UsageScope(employees=None)
    bindings = list(
        (
            await session.scalars(
                select(CorporateRoleBinding).where(
                    CorporateRoleBinding.organization_id == organization_id,
                    CorporateRoleBinding.principal_type == "user",
                    CorporateRoleBinding.account_id == principal_id,
                    CorporateRoleBinding.scope_kind == "team",
                    CorporateRoleBinding.state == "active",
                    CorporateRoleBinding.scope_id != "*",
                )
            )
        ).all()
    )
    teams: list[str] = []
    for binding in bindings:
        if binding.scope_id in teams:
            continue
        if await has_corporate_permission(
            session,
            organization_id=organization_id,
            principal_type="user",
            principal_id=principal_id,
            permission=permission,
            scope_kind="team",
            scope_id=binding.scope_id,
        ):
            teams.append(binding.scope_id)
    if not teams:
        return UsageScope(employees=frozenset())
    members = await _team_members(session, organization_id=organization_id, team_ids=teams)
    return UsageScope(
        employees=frozenset(members) | {principal_id},
        team_ids=frozenset(teams),
    )


async def _team_members(
    session: AsyncSession, *, organization_id: str, team_ids: Sequence[str] | str
) -> frozenset[str]:
    """Active members of the named team or teams; membership is presence."""
    team_filter = (
        CorporateTeamMember.team_id == team_ids
        if isinstance(team_ids, str)
        else CorporateTeamMember.team_id.in_(list(team_ids))
    )
    members = await session.scalars(
        select(CorporateTeamMember.account_id)
        .join(
            OrganizationMembership,
            (OrganizationMembership.organization_id == CorporateTeamMember.organization_id)
            & (OrganizationMembership.account_id == CorporateTeamMember.account_id),
        )
        .where(
            CorporateTeamMember.organization_id == organization_id,
            team_filter,
            OrganizationMembership.state == "active",
        )
    )
    return frozenset(members)


async def _technology_projects(
    session: AsyncSession, *, organization_id: str, technology_id: str
) -> frozenset[str]:
    projects = await session.scalars(
        select(ProjectTechnologyRelation.project_id).where(
            ProjectTechnologyRelation.organization_id == organization_id,
            ProjectTechnologyRelation.technology_id == technology_id,
            ProjectTechnologyRelation.state == "current",
        )
    )
    return frozenset(projects)


async def _active_projects(session: AsyncSession, *, organization_id: str) -> frozenset[str]:
    projects = await session.scalars(
        select(CorporateProject.id).where(
            CorporateProject.organization_id == organization_id,
            CorporateProject.state == "active",
        )
    )
    return frozenset(projects)


async def _employee_filter(
    session: AsyncSession,
    *,
    organization_id: str,
    query: RuntimeUsageReportQuery | RuntimeUsageEventQuery,
    allowed_employees: frozenset[str] | None,
) -> frozenset[str] | None:
    """Combine the caller's scope with the requested employee/team filters.

    Returns the employee set the query may match, or None when unrestricted.
    A filter that names someone outside the caller's scope narrows to empty,
    never widens.
    """
    allowed = allowed_employees
    team_id = getattr(query, "team_id", None)
    if team_id is not None:
        members = await _team_members(session, organization_id=organization_id, team_ids=team_id)
        allowed = members if allowed is None else allowed & members
    employee_id = getattr(query, "employee_id", None)
    if employee_id is not None:
        wanted = frozenset({employee_id})
        allowed = wanted if allowed is None else allowed & wanted
    return allowed


def _event_filters(
    organization_id: str,
    query: RuntimeUsageReportQuery | RuntimeUsageEventQuery,
    allowed_employees: frozenset[str] | None,
    technology_projects: frozenset[str] | None,
    retention_cutoff: datetime | None,
    *,
    confirmed_only: bool = False,
) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = [EventRow.organization_id == organization_id]
    if confirmed_only:
        clauses.extend([EventRow.source == "native_hook", EventRow.activity_kind == "invocation"])
    if allowed_employees is not None:
        clauses.append(EventRow.employee_account_id.in_(sorted(allowed_employees)))
    if query.device_id is not None:
        clauses.append(EventRow.device_id == query.device_id)
    if query.project_id is not None:
        clauses.append(EventRow.project_id == query.project_id)
    if technology_projects is not None:
        clauses.append(EventRow.project_id.in_(sorted(technology_projects)))
    if query.harness is not None:
        clauses.append(EventRow.harness == query.harness)
    if query.setup_stable_id is not None:
        clauses.append(EventRow.setup_stable_id == query.setup_stable_id)
    setup_version = getattr(query, "setup_version", None)
    if setup_version is not None:
        clauses.append(EventRow.setup_version == setup_version)
    if getattr(query, "direct_only", False):
        clauses.append(EventRow.setup_stable_id.is_(None))
    if query.component_stable_id is not None:
        clauses.append(EventRow.component_stable_id == query.component_stable_id)
    component_version = getattr(query, "component_version", None)
    if component_version is not None:
        clauses.append(EventRow.component_version == component_version)
    if query.component_kind is not None:
        clauses.append(EventRow.component_kind == query.component_kind)
    if query.outcome is not None:
        clauses.append(EventRow.outcome == query.outcome)
    source = getattr(query, "source", None)
    if source is not None:
        clauses.append(EventRow.source == source)
    activity_kind = getattr(query, "activity_kind", None)
    if activity_kind is not None:
        clauses.append(EventRow.activity_kind == activity_kind)
    invoked_from = _moment(query.invoked_from)
    invoked_to = _moment(query.invoked_to)
    if invoked_from is not None:
        clauses.append(EventRow.invoked_at >= invoked_from)
    if invoked_to is not None:
        clauses.append(EventRow.invoked_at <= invoked_to)
    if retention_cutoff is not None:
        # The retention boundary is a read-time guarantee as well as a
        # deletion rule: events past retention must not surface in a report
        # that runs before the privacy executor's next sweep.
        clauses.append(EventRow.invoked_at >= retention_cutoff)
    return clauses


# Component and parent coordinates followed by the actual installation environment.
type InventoryCoordinate = tuple[str, str, str | None, str | None, str, str, str | None]


def _setup_installed(
    observations: set[InventoryCoordinate],
    setup_id: str,
    setup_version: str,
    required: set[tuple[str, str]],
) -> bool:
    """A setup must be complete in one environment, with its actual parent binding."""
    environments: dict[tuple[str, str, str | None], set[tuple[str, str]]] = {}
    for component, version, parent, parent_version, device, scope, project in observations:
        if (parent, parent_version) == (setup_id, setup_version):
            environments.setdefault((device, scope, project), set()).add((component, version))
    return bool(required) and any(required <= present for present in environments.values())


async def _inventory_employees(
    session: AsyncSession,
    *,
    organization_id: str,
    query: RuntimeUsageReportQuery,
    employees: frozenset[str] | None,
    technology_projects: frozenset[str] | None,
    policy: TelemetryPolicy | None,
    now: datetime,
    retention_cutoff: datetime,
) -> tuple[
    list[RuntimeUsageInventoryEmployeeRow],
    dict[str, set[InventoryCoordinate]],
    dict[str, set[InventoryCoordinate]],
]:
    if policy is None or not policy.inventory_scan_enabled:
        return [], {}, {}
    conditions: list[ColumnElement[bool]] = [
        InstallationInventorySnapshot.organization_id == organization_id,
        InstallationInventorySnapshot.scanned_at >= retention_cutoff,
    ]
    if employees is not None:
        conditions.append(InstallationInventorySnapshot.employee_account_id.in_(sorted(employees)))
    if query.device_id is not None:
        conditions.append(InstallationInventorySnapshot.device_id == query.device_id)
    if query.project_id is not None:
        conditions.append(InstallationInventorySnapshot.project_id == query.project_id)
    if technology_projects is not None:
        conditions.append(InstallationInventorySnapshot.project_id.in_(sorted(technology_projects)))
    snapshots = await session.scalars(
        select(InstallationInventorySnapshot)
        .where(*conditions)
        .order_by(
            InstallationInventorySnapshot.scanned_at.desc(),
            InstallationInventorySnapshot.scan_id.desc(),
        )
    )
    revoked = await revoked_subjects(session, organization_id=organization_id)
    latest: dict[tuple[str, str, str, str | None], InstallationInventorySnapshot] = {}
    last_complete: dict[str, datetime] = {}
    for snapshot in snapshots:
        if ("account", snapshot.employee_account_id) in revoked or (
            "device",
            snapshot.device_id,
        ) in revoked:
            continue
        key = (
            snapshot.employee_account_id,
            snapshot.device_id,
            snapshot.scope,
            snapshot.project_id,
        )
        latest.setdefault(key, snapshot)
        if snapshot.complete and snapshot.employee_account_id not in last_complete:
            last_complete[snapshot.employee_account_id] = snapshot.scanned_at
    by_employee: dict[str, list[InstallationInventorySnapshot]] = {}
    for snapshot in latest.values():
        by_employee.setdefault(snapshot.employee_account_id, []).append(snapshot)
    output: list[RuntimeUsageInventoryEmployeeRow] = []
    installed: dict[str, set[InventoryCoordinate]] = {}
    modified_by_employee: dict[str, set[InventoryCoordinate]] = {}
    for employee_id, current in sorted(by_employee.items()):
        present: set[tuple[str, str, str]] = set()
        modified: set[tuple[str, str, str]] = set()
        stale = False
        partial = False
        installed[employee_id] = set()
        modified_by_employee[employee_id] = set()
        for snapshot in current:
            scanned_at = (
                snapshot.scanned_at.replace(tzinfo=UTC)
                if snapshot.scanned_at.tzinfo is None
                else snapshot.scanned_at
            )
            if now - scanned_at > timedelta(seconds=policy.heartbeat_stale_after_seconds):
                stale = True
                continue
            partial |= not snapshot.complete
            for component in snapshot.components:
                if component.get("source") != "managed":
                    continue
                if query.harness is not None and component.get("harness") != query.harness:
                    continue
                if (
                    query.setup_stable_id is not None
                    and component.get("setup_stable_id") != query.setup_stable_id
                ):
                    continue
                if (
                    query.component_stable_id is not None
                    and component.get("stable_id") != query.component_stable_id
                ):
                    continue
                if (
                    query.component_kind is not None
                    and component.get("kind") != query.component_kind
                ):
                    continue
                kind, stable_id, version = (
                    component.get("kind"),
                    component.get("stable_id"),
                    component.get("version"),
                )
                if not all(isinstance(value, str) for value in (kind, stable_id, version)):
                    continue
                coordinate = (str(kind), str(stable_id), str(version))
                parent = component.get("setup_stable_id")
                parent_version = component.get("setup_version")
                observation: InventoryCoordinate = (
                    str(stable_id),
                    str(version),
                    parent if isinstance(parent, str) else None,
                    parent_version if isinstance(parent_version, str) else None,
                    snapshot.device_id,
                    snapshot.scope,
                    snapshot.project_id,
                )
                if component.get("state") == "present":
                    present.add(coordinate)
                    installed[employee_id].add(observation)
                elif component.get("state") == "modified":
                    modified.add(coordinate)
                    modified_by_employee[employee_id].add(observation)
        output.append(
            RuntimeUsageInventoryEmployeeRow(
                employee_id=employee_id,
                observed_present=len(present),
                observed_modified=len(modified - present),
                coverage="stale" if stale else "partial" if partial else "complete",
                last_scan_at=_stamp(max(snapshot.scanned_at for snapshot in current)),
                last_complete_at=(
                    _stamp(last_complete[employee_id]) if employee_id in last_complete else None
                ),
            )
        )
    return output, installed, modified_by_employee


async def _assigned_components(
    session: AsyncSession,
    *,
    organization_id: str,
    employee_ids: list[str],
    query: RuntimeUsageReportQuery,
) -> dict[str, set[tuple[str, str, str | None, str | None]]]:
    """Resolve current assignments and expand setup passports to component versions."""
    if not employee_ids:
        return {}
    assignments = list(
        await session.scalars(
            select(CorporateCatalogAssignment).where(
                CorporateCatalogAssignment.organization_id == organization_id
            )
        )
    )
    by_line: dict[tuple[str, str], list[CorporateCatalogAssignment]] = {}
    for assignment in assignments:
        by_line.setdefault((assignment.object_kind, assignment.stable_id), []).append(assignment)
    teams: dict[str, set[str]] = {employee_id: set() for employee_id in employee_ids}
    projects: dict[str, set[str]] = {employee_id: set() for employee_id in employee_ids}
    technologies: dict[str, set[str]] = {employee_id: set() for employee_id in employee_ids}
    for employee_id, team_id in await session.execute(
        select(CorporateTeamMember.account_id, CorporateTeamMember.team_id).where(
            CorporateTeamMember.organization_id == organization_id,
            CorporateTeamMember.account_id.in_(employee_ids),
        )
    ):
        teams[employee_id].add(team_id)
    active_projects = await _active_projects(session, organization_id=organization_id)
    for employee_id, project_id in await session.execute(
        select(CorporateProjectMember.account_id, CorporateProjectMember.project_id).where(
            CorporateProjectMember.organization_id == organization_id,
            CorporateProjectMember.account_id.in_(employee_ids),
        )
    ):
        if project_id in active_projects:
            projects[employee_id].add(project_id)
    for employee_id, technology_id in await session.execute(
        select(EmployeeTechnology.account_id, EmployeeTechnology.technology_id).where(
            EmployeeTechnology.organization_id == organization_id,
            EmployeeTechnology.account_id.in_(employee_ids),
            EmployeeTechnology.state == "current",
        )
    ):
        technologies[employee_id].add(technology_id)
    project_technologies: dict[str, set[str]] = {}
    for project_id, technology_id in await session.execute(
        select(ProjectTechnologyRelation.project_id, ProjectTechnologyRelation.technology_id).where(
            ProjectTechnologyRelation.organization_id == organization_id,
            ProjectTechnologyRelation.state == "current",
        )
    ):
        project_technologies.setdefault(project_id, set()).add(technology_id)
    harnesses = (
        {query.harness}
        if query.harness is not None
        else {None, *(assignment.harness for assignment in assignments if assignment.harness)}
    )
    resolved: dict[str, set[tuple[str, str, str | None, str | None]]] = {}
    version_cache: dict[tuple[str, str, str], str | None] = {}
    setup_cache: dict[tuple[str, str], list[tuple[str, str]]] = {}
    component_kind_cache: dict[tuple[str, str], str | None] = {}
    # ponytail: scan contexts in memory; batch/materialize when tenant size makes this slow.
    for employee_id in employee_ids:
        contexts: set[tuple[str | None, str | None]] = set()
        if query.project_id is None:
            if query.technology_id is None:
                contexts.add((None, None))
                contexts.update(
                    (None, technology_id) for technology_id in technologies[employee_id]
                )
            elif query.technology_id in technologies[employee_id]:
                contexts.add((None, query.technology_id))
        candidate_projects = (
            {query.project_id} if query.project_id is not None else projects[employee_id]
        )
        for project_id in candidate_projects & projects[employee_id]:
            related = project_technologies.get(project_id, set())
            if query.technology_id is None:
                contexts.add((project_id, None))
                contexts.update((project_id, technology_id) for technology_id in related)
            elif query.technology_id in related:
                contexts.add((project_id, query.technology_id))
        coordinates: set[tuple[str, str, str | None, str | None]] = set()
        for (object_kind, stable_id), rows in by_line.items():
            if object_kind not in ("setup", "component"):
                continue
            if query.setup_stable_id is not None and (
                object_kind != "setup" or stable_id != query.setup_stable_id
            ):
                continue
            if (
                object_kind == "component"
                and query.component_stable_id is not None
                and stable_id != query.component_stable_id
            ):
                continue
            for project_id, technology_id in contexts:
                for harness in harnesses:
                    winner, _, _, _ = select_assignment_winner(
                        rows,
                        account_id=employee_id,
                        team_ids=teams[employee_id],
                        project_id=project_id,
                        technology_id=technology_id,
                        harness=harness,
                    )
                    if winner is None:
                        continue
                    version = winner.version
                    if winner.selector == "latest":
                        cache_key = (employee_id, object_kind, stable_id)
                        if cache_key not in version_cache:
                            eligible = await eligible_assignment_versions(
                                session,
                                object_kind=object_kind,
                                stable_id=stable_id,
                                account_id=employee_id,
                            )
                            version_cache[cache_key] = eligible[-1][0] if eligible else None
                        version = version_cache[cache_key]
                    if version is None:
                        continue
                    if object_kind == "component":
                        candidates = [(stable_id, version)]
                    else:
                        setup_key = (stable_id, version)
                        if setup_key not in setup_cache:
                            metadata = await session.scalar(
                                select(CatalogMetadata).where(
                                    CatalogMetadata.object_kind == "setup",
                                    CatalogMetadata.stable_id == stable_id,
                                    CatalogMetadata.version == version,
                                )
                            )
                            document = metadata.passport_document if metadata else None
                            entries: object = (
                                document.get("components") if isinstance(document, dict) else None
                            )
                            if (
                                query.harness is not None
                                and isinstance(document, dict)
                                and document.get("harness_id") != query.harness
                            ):
                                entries = None
                            components: list[tuple[str, str]] = []
                            if isinstance(entries, list):
                                for item in cast(list[object], entries):
                                    if not isinstance(item, dict):
                                        continue
                                    values = cast(dict[str, object], item)
                                    component_id = values.get("stable_id")
                                    component_version = values.get("version")
                                    if isinstance(component_id, str) and isinstance(
                                        component_version, str
                                    ):
                                        components.append((component_id, component_version))
                            setup_cache[setup_key] = components
                        candidates = setup_cache[setup_key]
                    for component_id, component_version in candidates:
                        if (
                            query.component_stable_id is not None
                            and component_id != query.component_stable_id
                        ):
                            continue
                        if query.component_kind is not None:
                            component_key = (component_id, component_version)
                            if component_key not in component_kind_cache:
                                metadata = await session.scalar(
                                    select(CatalogMetadata).where(
                                        CatalogMetadata.object_kind == "component",
                                        CatalogMetadata.stable_id == component_id,
                                        CatalogMetadata.version == component_version,
                                    )
                                )
                                document = metadata.passport_document if metadata else None
                                kind = (
                                    document.get("component_type")
                                    if isinstance(document, dict)
                                    else None
                                )
                                component_kind_cache[component_key] = (
                                    kind if isinstance(kind, str) else None
                                )
                            if component_kind_cache[component_key] != query.component_kind:
                                continue
                        coordinates.add(
                            (
                                component_id,
                                component_version,
                                stable_id if object_kind == "setup" else None,
                                version if object_kind == "setup" else None,
                            )
                        )
        resolved[employee_id] = coordinates
    return resolved


async def ingest_events(
    session: AsyncSession,
    *,
    organization_id: str,
    batch: RuntimeUsageEventBatch,
    caller_account_id: str,
    caller_device_id: str | None,
    now: datetime | None = None,
) -> RuntimeUsageIngestResult:
    """Store the batch, deduplicating on the (organization, event) key.

    Identity is bound to the authenticated caller, never to the payload: an
    event naming another employee, another held device, a foreign tenant, an
    unknown project, a revoked subject, or a timestamp outside the retention
    window is rejected rather than stored.
    """
    await set_tenant_scope(session, organization_id)
    policy = await session.get(TelemetryPolicy, organization_id)
    if policy is None or not policy.usage_collection_enabled:
        return RuntimeUsageIngestResult(
            accepted=0,
            duplicates=0,
            rejected=len(batch.events),
            rejected_ids=[event.event_id for event in batch.events],
        )
    moment = now or datetime.now(UTC)
    retention_cutoff = moment - timedelta(
        days=await raw_retention_days(session, organization_id=organization_id)
    )
    revoked = await revoked_subjects(session, organization_id=organization_id)
    projects = await _active_projects(session, organization_id=organization_id)
    # A session bound to a device can only emit for that device; a session
    # without one (a browser context) may only name an active device the
    # caller's own account holds.
    device_query = select(Device.id).where(
        Device.account_id == caller_account_id,
        Device.state == "active",
    )
    if caller_device_id is not None:
        device_query = device_query.where(Device.id == caller_device_id)
    caller_devices = frozenset(await session.scalars(device_query))
    accepted = 0
    duplicates = 0
    rejected = 0
    accepted_ids: list[str] = []
    duplicate_ids: list[str] = []
    rejected_ids: list[str] = []
    seen: dict[str, EventRow] = {}
    for event in batch.events:
        invoked_at = _moment(event.invoked_at)
        if (
            event.organization_id != organization_id
            or event.employee_id != caller_account_id
            or event.device_id not in caller_devices
            or event.project_id not in projects
            or ("account", event.employee_id) in revoked
            or ("device", event.device_id) in revoked
            or invoked_at is None
            or invoked_at > moment + MAX_FUTURE_SKEW
            or invoked_at < retention_cutoff
        ):
            rejected += 1
            rejected_ids.append(event.event_id)
            continue
        candidate = _row_for(organization_id, event)
        existing = seen.get(event.event_id)
        if existing is None:
            existing = await session.scalar(
                select(EventRow).where(
                    EventRow.organization_id == organization_id,
                    EventRow.event_id == event.event_id,
                )
            )
        if existing is not None:
            if any(
                getattr(existing, field) != getattr(candidate, field)
                for field in _DEDUP_COMPARE_FIELDS
            ):
                rejected += 1
                rejected_ids.append(event.event_id)
                continue
            if existing.source == "agent_reported" and event.source == "native_hook":
                existing.source = event.source
                existing.outcome = event.outcome
                existing.invoked_at = candidate.invoked_at
            duplicates += 1
            duplicate_ids.append(event.event_id)
            continue
        session.add(candidate)
        try:
            async with session.begin_nested():
                await session.flush()
        except IntegrityError:
            # A concurrent ingest of the same event_id committed between the
            # existence read and this flush: classify it against the stored
            # row exactly as the read path does.
            stored = await session.scalar(
                select(EventRow).where(
                    EventRow.organization_id == organization_id,
                    EventRow.event_id == event.event_id,
                )
            )
            if stored is None:
                raise
            if any(
                getattr(stored, field) != getattr(candidate, field)
                for field in _DEDUP_COMPARE_FIELDS
            ):
                rejected += 1
                rejected_ids.append(event.event_id)
            else:
                if stored.source == "agent_reported" and event.source == "native_hook":
                    stored.source = event.source
                    stored.outcome = event.outcome
                    stored.invoked_at = candidate.invoked_at
                duplicates += 1
                duplicate_ids.append(event.event_id)
            continue
        seen[event.event_id] = candidate
        accepted += 1
        accepted_ids.append(event.event_id)
    await session.flush()
    return RuntimeUsageIngestResult(
        accepted=accepted,
        duplicates=duplicates,
        rejected=rejected,
        accepted_ids=accepted_ids,
        duplicate_ids=duplicate_ids,
        rejected_ids=rejected_ids,
    )


def _row_for(organization_id: str, event: RuntimeUsageEvent) -> EventRow:
    return EventRow(
        event_id=event.event_id,
        organization_id=organization_id,
        employee_account_id=event.employee_id,
        device_id=event.device_id,
        project_id=event.project_id,
        harness=event.harness,
        setup_stable_id=event.setup.stable_id if event.setup else None,
        setup_version=event.setup.version if event.setup else None,
        setup_passport_digest=event.setup.passport_digest if event.setup else None,
        component_kind=event.component.kind,
        component_stable_id=event.component.stable_id,
        component_version=event.component.version,
        component_passport_digest=event.component.passport_digest,
        invoked_at=_moment(event.invoked_at) or datetime.now(UTC),
        outcome=event.outcome,
        source=event.source,
        activity_kind=event.activity_kind,
        schema_version=event.schema_version,
    )


async def aggregate_report(
    session: AsyncSession,
    *,
    organization_id: str,
    query: RuntimeUsageReportQuery,
    scope: UsageScope,
    now: datetime | None = None,
) -> RuntimeUsageReport:
    """Deterministic grouped counts plus current assignments and observed use."""
    await set_tenant_scope(session, organization_id)
    moment = now or datetime.now(UTC)
    retention_cutoff = moment - timedelta(
        days=await raw_retention_days(session, organization_id=organization_id)
    )
    technology_projects = (
        await _technology_projects(
            session, organization_id=organization_id, technology_id=query.technology_id
        )
        if query.technology_id is not None
        else None
    )
    employees = await _employee_filter(
        session,
        organization_id=organization_id,
        query=query,
        allowed_employees=scope.employees,
    )
    member_query = select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.state == "active",
    )
    if employees is not None:
        member_query = member_query.where(OrganizationMembership.account_id.in_(sorted(employees)))
    revoked = await revoked_subjects(session, organization_id=organization_id)
    members = [
        member
        for member in await session.scalars(member_query)
        if ("account", member.account_id) not in revoked
    ]
    if query.usage_state != "all":
        activity_clauses = _event_filters(
            organization_id,
            query,
            employees,
            technology_projects,
            retention_cutoff,
            confirmed_only=True,
        )
        recorded_employees = set(
            await session.scalars(
                select(distinct(EventRow.employee_account_id)).where(*activity_clauses)
            )
        )
        members = [
            member
            for member in members
            if (member.account_id in recorded_employees) == (query.usage_state == "recorded")
        ]
        employees = frozenset(member.account_id for member in members)
    policy = await session.get(TelemetryPolicy, organization_id)
    inventory_employees, installed_by_employee, modified_by_employee = await _inventory_employees(
        session,
        organization_id=organization_id,
        query=query,
        employees=employees,
        technology_projects=technology_projects,
        policy=policy,
        now=moment,
        retention_cutoff=retention_cutoff,
    )
    if query.collection_state != "all":
        coverage = {row.employee_id: row.coverage for row in inventory_employees}
        scan_enabled = policy is not None and policy.inventory_scan_enabled
        members = [
            member
            for member in members
            if (coverage.get(member.account_id, "unknown") if scan_enabled else "disabled")
            == query.collection_state
        ]
        employees = frozenset(member.account_id for member in members)
        inventory_employees = [row for row in inventory_employees if row.employee_id in employees]
        installed_by_employee = {
            key: value for key, value in installed_by_employee.items() if key in employees
        }
        modified_by_employee = {
            key: value for key, value in modified_by_employee.items() if key in employees
        }
    member_ids = [member.account_id for member in members]
    assigned_components = await _assigned_components(
        session,
        organization_id=organization_id,
        employee_ids=member_ids,
        query=query,
    )
    clauses = _event_filters(
        organization_id,
        query,
        employees,
        technology_projects,
        retention_cutoff,
        confirmed_only=True,
    )
    if query.group_by == "setup":
        clauses.append(EventRow.setup_stable_id.is_not(None))
    total = int(
        await session.scalar(select(func.count()).select_from(EventRow).where(*clauses)) or 0
    )
    report_timezone = policy.report_timezone if policy is not None else "UTC"
    zone = ZoneInfo(report_timezone)
    object_assigned: dict[tuple[str, str, str, str | None, str | None], set[str]] = {}
    object_installed: dict[tuple[str, str, str, str | None, str | None], set[str]] = {}
    setup_required: dict[tuple[str, str, str], set[tuple[str, str]]] = {}
    object_events: dict[
        tuple[str, str, str, str | None, str | None], list[tuple[str, str, datetime]]
    ] = {}
    for employee_id, links in assigned_components.items():
        installed = installed_by_employee.get(employee_id, set())
        for component_id, component_version, setup_id, setup_version in links:
            component_key = ("component", component_id, component_version, setup_id, setup_version)
            object_assigned.setdefault(component_key, set()).add(employee_id)
            if any(
                item[:4] == (component_id, component_version, setup_id, setup_version)
                for item in installed
            ):
                object_installed.setdefault(component_key, set()).add(employee_id)
            if setup_id is not None and setup_version is not None:
                setup_key = ("setup", setup_id, setup_version, None, None)
                object_assigned.setdefault(setup_key, set()).add(employee_id)
                setup_required.setdefault((employee_id, setup_id, setup_version), set()).add(
                    (component_id, component_version)
                )
    for (employee_id, setup_id, setup_version), required in setup_required.items():
        if _setup_installed(
            installed_by_employee.get(employee_id, set()), setup_id, setup_version, required
        ):
            object_installed.setdefault(("setup", setup_id, setup_version, None, None), set()).add(
                employee_id
            )
    days: Counter[str] = Counter()
    hours: Counter[tuple[int, int]] = Counter()
    columns = _GROUP_COLUMNS[query.group_by]
    active_days: dict[tuple[object, ...], set[str]] = {}
    employee_days: dict[str, set[str]] = {}
    employee_used: dict[str, set[tuple[str, str]]] = {}
    employee_uses: Counter[str] = Counter()
    employee_last_used: dict[str, datetime] = {}
    # ponytail: stream event timestamps until report volume warrants database-specific bucketing.
    for event_record in await session.execute(
        select(
            *columns,
            EventRow.invoked_at,
            EventRow.employee_account_id,
            EventRow.component_stable_id,
            EventRow.component_version,
            EventRow.setup_stable_id,
            EventRow.setup_version,
        ).where(*clauses)
    ):
        invoked_at = event_record[-6]
        employee_id = event_record[-5]
        component_id = event_record[-4]
        component_version = event_record[-3]
        setup_id = event_record[-2]
        setup_version = event_record[-1]
        local = (
            invoked_at.replace(tzinfo=UTC).astimezone(zone)
            if invoked_at.tzinfo is None
            else invoked_at.astimezone(zone)
        )
        day = local.date().isoformat()
        days[day] += 1
        hours[(local.weekday(), local.hour)] += 1
        active_days.setdefault(tuple(event_record[: len(columns)]), set()).add(day)
        employee_days.setdefault(employee_id, set()).add(day)
        employee_used.setdefault(employee_id, set()).add((component_id, component_version))
        object_events.setdefault(
            ("component", component_id, component_version, setup_id, setup_version), []
        ).append((employee_id, day, invoked_at))
        if setup_id is not None and setup_version is not None:
            object_events.setdefault(("setup", setup_id, setup_version, None, None), []).append(
                (employee_id, day, invoked_at)
            )
        employee_uses[employee_id] += 1
        if employee_id not in employee_last_used or invoked_at > employee_last_used[employee_id]:
            employee_last_used[employee_id] = invoked_at
    statement = (
        select(
            *columns,
            func.count().label("invocations"),
            func.count().filter(EventRow.outcome == "succeeded").label("succeeded"),
            func.count().filter(EventRow.outcome == "failed").label("failed"),
            func.count().filter(EventRow.outcome == "cancelled").label("cancelled"),
            func.count(distinct(EventRow.employee_account_id)).label("employees"),
            func.count(distinct(EventRow.device_id)).label("devices"),
            func.min(EventRow.invoked_at).label("first_invoked_at"),
            func.max(EventRow.invoked_at).label("last_invoked_at"),
        )
        .where(*clauses)
        .group_by(*columns)
        .order_by(func.count().desc(), *columns)
        .offset(query.offset)
        .limit(query.limit)
    )
    rows: list[RuntimeUsageReportRow] = []
    for record in (await session.execute(statement)).all():
        values = list(record[: len(columns)])
        rows.append(
            RuntimeUsageReportRow(
                group_value=":".join(str(value) for value in values),
                component_kind=values[0] if query.group_by == "component" else None,
                component_stable_id=values[1] if query.group_by == "component" else None,
                component_version=values[2] if query.group_by == "component" else None,
                setup_stable_id=values[0] if query.group_by == "setup" else None,
                setup_version=values[1] if query.group_by == "setup" else None,
                invocations=record.invocations,
                succeeded=record.succeeded,
                failed=record.failed,
                cancelled=record.cancelled,
                employees=record.employees,
                devices=record.devices,
                active_days=len(active_days.get(tuple(values), set())),
                first_invoked_at=_stamp(record.first_invoked_at),
                last_invoked_at=_stamp(record.last_invoked_at),
            )
        )
    team_rows = await session.execute(
        select(CorporateTeamMember.account_id, CorporateTeamMember.team_id).where(
            CorporateTeamMember.organization_id == organization_id,
            CorporateTeamMember.account_id.in_(member_ids),
        )
    )
    member_teams: dict[str, list[str]] = {employee_id: [] for employee_id in member_ids}
    for employee_id, team_id in team_rows:
        member_teams[employee_id].append(team_id)
    employee_rows: list[RuntimeUsageEmployeeRow] = []
    for member in members:
        account_id = member.account_id
        assigned_set = {
            (component_id, component_version)
            for component_id, component_version, _, _ in assigned_components.get(account_id, set())
        }
        employee_rows.append(
            RuntimeUsageEmployeeRow(
                employee_id=account_id,
                name=member.display_name,
                team_ids=sorted(member_teams[account_id]),
                assigned_components=len({stable_id for stable_id, _ in assigned_set}),
                installed_components=len(
                    {
                        stable_id
                        for stable_id, version in assigned_set
                        if any(
                            item[:2] == (stable_id, version)
                            for item in installed_by_employee.get(account_id, set())
                        )
                    }
                ),
                used_components=len(
                    {
                        stable_id
                        for stable_id, version in assigned_set
                        if (stable_id, version) in employee_used.get(account_id, set())
                    }
                ),
                uses=employee_uses[account_id],
                active_days=len(employee_days.get(account_id, set())),
                last_used_at=(
                    _stamp(employee_last_used[account_id])
                    if account_id in employee_last_used
                    else None
                ),
            )
        )
    object_rows: list[RuntimeUsageObjectRow] = []
    object_keys = set(object_assigned) | set(object_events)
    catalog_names: dict[tuple[str, str, str], str] = {}
    if object_keys:
        for metadata in await session.scalars(
            select(CatalogMetadata).where(
                tuple_(
                    CatalogMetadata.object_kind, CatalogMetadata.stable_id, CatalogMetadata.version
                ).in_(sorted({key[:3] for key in object_keys}))
            )
        ):
            name = (metadata.passport_document or {}).get("name")
            if isinstance(name, str) and name.strip() and metadata.version is not None:
                catalog_names[(metadata.object_kind, metadata.stable_id, metadata.version)] = name
    selected_inventory = next(
        (row for row in inventory_employees if row.employee_id == query.employee_id), None
    )
    selected_installed = installed_by_employee.get(query.employee_id or "", set())
    selected_modified = modified_by_employee.get(query.employee_id or "", set())

    def installation_state(key: tuple[str, str, str, str | None, str | None]) -> str | None:
        if query.employee_id is None:
            return None
        if key[0] == "setup":
            coordinates = setup_required.get((query.employee_id, key[1], key[2]), set())
            if not coordinates:
                return "unknown"
            present = _setup_installed(selected_installed, key[1], key[2], coordinates)
            modified = any(
                item[2:4] == (key[1], key[2]) and item[:2] in coordinates
                for item in selected_modified
            )
        else:
            present = any(item[:4] == key[1:] for item in selected_installed)
            modified = any(item[:4] == key[1:] for item in selected_modified)
        if present:
            return "present"
        if modified:
            return "modified"
        if selected_inventory is None or selected_inventory.coverage != "complete":
            return "unknown"
        return "missing"

    for key in sorted(
        object_keys,
        key=lambda value: tuple(part or "" for part in value),
    ):
        events = object_events.get(key, [])
        object_rows.append(
            RuntimeUsageObjectRow(
                object_kind=cast("Literal['setup', 'component']", key[0]),
                stable_id=key[1],
                name=catalog_names.get(key[:3]),
                version=key[2],
                parent_setup_stable_id=key[3],
                parent_setup_version=key[4],
                assigned_to=len(object_assigned.get(key, set())),
                installed_for=len(object_installed.get(key, set())),
                installation_state=installation_state(key),  # pyright: ignore[reportArgumentType]
                last_checked_at=(selected_inventory.last_scan_at if selected_inventory else None),
                used_by=len({employee_id for employee_id, _, _ in events}),
                uses=len(events),
                active_days=len({day for _, day, _ in events}),
                last_used_at=_stamp(max(when for _, _, when in events)) if events else None,
            )
        )
    assigned_keys = {
        (row.object_kind, row.stable_id, row.version) for row in object_rows if row.assigned_to > 0
    }
    assigned_counts: dict[tuple[str, str, str], tuple[int, str | None]] = {}
    for row in object_rows:
        key = (row.object_kind, row.stable_id, row.version)
        if key not in assigned_keys:
            continue
        previous_uses, previous_last = assigned_counts.get(key, (0, None))
        assigned_counts[key] = (
            previous_uses + row.uses,
            max(filter(None, (previous_last, row.last_used_at)), default=None),
        )
    assigned = [
        RuntimeUsageAssignedRow(
            object_kind=cast("Literal['setup', 'component']", kind),
            stable_id=stable_id,
            version=version,
            state="recorded_use" if uses else "no_recorded_use",
            invocations=uses,
            last_invoked_at=last_used,
        )
        for (kind, stable_id, version), (uses, last_used) in sorted(assigned_counts.items())
    ]
    return RuntimeUsageReport(
        organization_id=organization_id,
        generated_at=_stamp(moment),
        invoked_from=query.invoked_from,
        invoked_to=query.invoked_to,
        group_by=query.group_by,
        total_events=total,
        report_timezone=report_timezone,
        inventory_scan_enabled=policy.inventory_scan_enabled if policy else False,
        usage_collection_enabled=policy.usage_collection_enabled if policy else False,
        inventory_employees=inventory_employees,
        employees=employee_rows,
        objects=object_rows,
        by_day=[RuntimeUsageDayBucket(day=day, uses=count) for day, count in sorted(days.items())],
        by_hour=[
            RuntimeUsageHourBucket(weekday=weekday, hour=hour, uses=count)
            for (weekday, hour), count in sorted(hours.items())
        ],
        rows=rows,
        assigned=assigned,
    )


async def list_events(
    session: AsyncSession,
    *,
    organization_id: str,
    query: RuntimeUsageEventQuery,
    scope: UsageScope,
    now: datetime | None = None,
) -> RuntimeUsageEventList:
    """The redacted drill-down page: identities and coordinates only.

    Revoked or deleted subjects are suppressed from event-level detail - the
    privacy authority's anonymization keeps aggregate counts while the raw row
    stays out of reach, which is what "separately permissioned and redacted"
    means against `SPEC-089`.
    """
    await set_tenant_scope(session, organization_id)
    moment = now or datetime.now(UTC)
    retention_cutoff = moment - timedelta(
        days=await raw_retention_days(session, organization_id=organization_id)
    )
    employees = await _employee_filter(
        session,
        organization_id=organization_id,
        query=query,
        allowed_employees=scope.employees,
    )
    technology_id = getattr(query, "technology_id", None)
    technology_projects = (
        await _technology_projects(
            session, organization_id=organization_id, technology_id=str(technology_id)
        )
        if technology_id is not None
        else None
    )
    clauses = _event_filters(
        organization_id, query, employees, technology_projects, retention_cutoff
    )
    zone: ZoneInfo | None = None
    if (
        query.local_day is not None
        or query.local_weekday is not None
        or query.local_hour is not None
    ):
        policy = await session.get(TelemetryPolicy, organization_id)
        zone = ZoneInfo(policy.report_timezone if policy is not None else "UTC")
    if query.local_day is not None:
        assert zone is not None
        day_start = datetime.combine(query.local_day, time.min, tzinfo=zone)
        day_end = datetime.combine(query.local_day + timedelta(days=1), time.min, tzinfo=zone)
        clauses.extend(
            [
                EventRow.invoked_at >= day_start.astimezone(UTC),
                EventRow.invoked_at < day_end.astimezone(UTC),
            ]
        )
    revoked = await revoked_subjects(session, organization_id=organization_id)
    if revoked:
        revoked_accounts = {subject for kind, subject in revoked if kind == "account"}
        revoked_devices = {subject for kind, subject in revoked if kind == "device"}
        if revoked_accounts:
            clauses.append(EventRow.employee_account_id.not_in(sorted(revoked_accounts)))
        if revoked_devices:
            clauses.append(EventRow.device_id.not_in(sorted(revoked_devices)))
    statement = (
        select(EventRow).where(*clauses).order_by(EventRow.invoked_at.desc(), EventRow.event_id)
    )
    rows: list[EventRow]
    if query.local_weekday is not None or query.local_hour is not None:
        assert zone is not None
        # ponytail: scan tenant-window rows for portable local-hour filtering; move to a
        # database-specific expression when event volume makes this report slow.
        matching: list[EventRow] = []
        for row in (await session.scalars(statement)).all():
            local = (
                row.invoked_at.replace(tzinfo=UTC)
                if row.invoked_at.tzinfo is None
                else row.invoked_at
            ).astimezone(zone)
            if query.local_weekday is not None and local.weekday() != query.local_weekday:
                continue
            if query.local_hour is not None and local.hour != query.local_hour:
                continue
            matching.append(row)
        rows = matching[query.offset : query.offset + query.limit]
    else:
        rows = list(
            (await session.scalars(statement.offset(query.offset).limit(query.limit))).all()
        )
    return RuntimeUsageEventList(
        organization_id=organization_id,
        offset=query.offset,
        limit=query.limit,
        events=[
            RuntimeUsageEventView(
                event_id=row.event_id,
                employee_id=row.employee_account_id,
                device_id=row.device_id,
                project_id=row.project_id,
                harness=row.harness,
                setup_stable_id=row.setup_stable_id,
                setup_version=row.setup_version,
                component_kind=row.component_kind,
                component_stable_id=row.component_stable_id,
                component_version=row.component_version,
                invoked_at=_stamp(row.invoked_at),
                outcome=row.outcome,  # pyright: ignore[reportArgumentType]
                source=row.source,  # pyright: ignore[reportArgumentType]
                activity_kind=row.activity_kind,  # pyright: ignore[reportArgumentType]
            )
            for row in rows
        ],
    )


async def create_export(
    session: AsyncSession,
    *,
    organization_id: str,
    request: RuntimeUsageExportRequest,
    scope: UsageScope,
    actor_account_id: str,
    now: datetime | None = None,
) -> RuntimeUsageExportView:
    """Produce a bounded export receipt; a repeated key returns the original.

    The stored artifact is the aggregate rows plus a canonical digest. Raw
    events never enter an export - drill-down stays on its own permission.
    """
    await set_tenant_scope(session, organization_id)
    existing = await session.scalar(
        select(ExportRow).where(
            ExportRow.organization_id == organization_id,
            ExportRow.idempotency_key == request.idempotency_key,
        )
    )
    if existing is not None:
        return _export_view(existing)
    bounded = request.query.model_copy(update={"offset": 0, "limit": EXPORT_ROW_LIMIT})
    report = await aggregate_report(
        session,
        organization_id=organization_id,
        query=bounded,
        scope=scope,
        now=now,
    )
    digest = _export_digest({"rows": [row.model_dump(mode="json") for row in report.rows]})
    record = ExportRow(
        id=new_id("operation"),
        organization_id=organization_id,
        requested_by=actor_account_id,
        idempotency_key=request.idempotency_key,
        filters=request.query.model_dump(mode="json", exclude_none=True),
        row_count=len(report.rows),
        content_digest=digest,
        state="completed",
        created_at=now or datetime.now(UTC),
    )
    session.add(record)
    await session.flush()
    return _export_view(record)


def _export_digest(value: JsonValue) -> str:
    """Domain-separated digest of the export's canonical row set."""
    return digest_canonical(EXPORT_DIGEST_DOMAIN, value)


def _export_view(record: ExportRow) -> RuntimeUsageExportView:
    return RuntimeUsageExportView(
        export_id=record.id,
        organization_id=record.organization_id,
        created_at=_stamp(record.created_at),
        row_count=record.row_count,
        content_digest=record.content_digest,
        state="completed",
    )


async def read_export(
    session: AsyncSession,
    *,
    organization_id: str,
    export_id: str,
) -> RuntimeUsageExportView | None:
    await set_tenant_scope(session, organization_id)
    record = await session.scalar(
        select(ExportRow).where(
            ExportRow.organization_id == organization_id,
            ExportRow.id == export_id,
        )
    )
    return None if record is None else _export_view(record)


__all__ = [
    "DEFAULT_RAW_RETENTION_DAYS",
    "EXPORT_DIGEST_DOMAIN",
    "MAX_FUTURE_SKEW",
    "PERMISSION_EVENTS",
    "PERMISSION_EXPORT",
    "PERMISSION_INGEST",
    "PERMISSION_READ",
    "UsageScope",
    "aggregate_report",
    "create_export",
    "ingest_events",
    "list_events",
    "raw_retention_days",
    "read_export",
    "resolve_scope",
    "revoked_subjects",
]
