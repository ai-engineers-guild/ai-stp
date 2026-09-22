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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Literal, cast

from sqlalchemy import distinct, func, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from ai_stp_contracts.runtime_usage import (
    EXPORT_ROW_LIMIT,
    RuntimeUsageEvent,
    RuntimeUsageEventBatch,
    RuntimeUsageEventList,
    RuntimeUsageEventQuery,
    RuntimeUsageEventView,
    RuntimeUsageExportRequest,
    RuntimeUsageExportView,
    RuntimeUsageIngestResult,
    RuntimeUsageInstalledRow,
    RuntimeUsageReport,
    RuntimeUsageReportQuery,
    RuntimeUsageReportRow,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.models import Device
from ai_stp_platform.organization_models import (
    CorporateCatalogAssignment,
    CorporateProject,
    CorporateRoleBinding,
    CorporateTeamMember,
    OrganizationMembership,
)
from ai_stp_platform.runtime_usage_models import RuntimeUsageEvent as EventRow
from ai_stp_platform.runtime_usage_models import RuntimeUsageExport as ExportRow
from ai_stp_platform.technology_models import ProjectTechnologyRelation
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


async def _revoked_subjects(
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
) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = [EventRow.organization_id == organization_id]
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
    if query.component_stable_id is not None:
        clauses.append(EventRow.component_stable_id == query.component_stable_id)
    if query.component_kind is not None:
        clauses.append(EventRow.component_kind == query.component_kind)
    if query.outcome is not None:
        clauses.append(EventRow.outcome == query.outcome)
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
    moment = now or datetime.now(UTC)
    retention_cutoff = moment - timedelta(
        days=await raw_retention_days(session, organization_id=organization_id)
    )
    revoked = await _revoked_subjects(session, organization_id=organization_id)
    projects = await _active_projects(session, organization_id=organization_id)
    # A session bound to a device can only emit for that device; a session
    # without one (a browser context) may only name an active device the
    # caller's own account holds.
    caller_devices = (
        frozenset({caller_device_id})
        if caller_device_id is not None
        else frozenset(
            await session.scalars(
                select(Device.id).where(
                    Device.account_id == caller_account_id,
                    Device.state == "active",
                )
            )
        )
    )
    accepted = 0
    duplicates = 0
    rejected = 0
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
            continue
        existing = await session.scalar(
            select(EventRow.event_id).where(
                EventRow.organization_id == organization_id,
                EventRow.event_id == event.event_id,
            )
        )
        if existing is not None:
            duplicates += 1
            continue
        session.add(_row_for(organization_id, event))
        accepted += 1
    await session.flush()
    return RuntimeUsageIngestResult(accepted=accepted, duplicates=duplicates, rejected=rejected)


def _row_for(organization_id: str, event: RuntimeUsageEvent) -> EventRow:
    return EventRow(
        event_id=event.event_id,
        organization_id=organization_id,
        employee_account_id=event.employee_id,
        device_id=event.device_id,
        project_id=event.project_id,
        harness=event.harness,
        setup_stable_id=event.setup.stable_id,
        setup_version=event.setup.version,
        setup_passport_digest=event.setup.passport_digest,
        component_kind=event.component.kind,
        component_stable_id=event.component.stable_id,
        component_version=event.component.version,
        component_passport_digest=event.component.passport_digest,
        invoked_at=_moment(event.invoked_at) or datetime.now(UTC),
        outcome=event.outcome,
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
    """Deterministic grouped counts plus the installed-vs-invoked comparison."""
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
    clauses = _event_filters(
        organization_id, query, employees, technology_projects, retention_cutoff
    )
    total = int(
        await session.scalar(select(func.count()).select_from(EventRow).where(*clauses)) or 0
    )
    columns = _GROUP_COLUMNS[query.group_by]
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
                first_invoked_at=_stamp(record.first_invoked_at),
                last_invoked_at=_stamp(record.last_invoked_at),
            )
        )
    installed = await _installed_rows(
        session,
        organization_id=organization_id,
        clauses=clauses,
        scope=scope,
    )
    return RuntimeUsageReport(
        organization_id=organization_id,
        generated_at=_stamp(moment),
        invoked_from=query.invoked_from,
        invoked_to=query.invoked_to,
        group_by=query.group_by,
        total_events=total,
        rows=rows,
        installed=installed,
    )


async def _installed_rows(
    session: AsyncSession,
    *,
    organization_id: str,
    clauses: list[ColumnElement[bool]],
    scope: UsageScope,
) -> list[RuntimeUsageInstalledRow]:
    """Current assignments beside their invocation counts in the same window.

    An assigned object with no matching event is `not_invoked` - the
    installed-vs-invoked distinction the report exists to answer. A scoped
    caller sees only assignments addressed to their employees or their teams,
    plus organization-wide ones: naming an assignment outside the caller's
    scope would disclose which objects other teams were handed.
    """
    invoked = await session.execute(
        select(
            EventRow.component_stable_id,
            EventRow.component_version,
            func.count().label("invocations"),
            func.max(EventRow.invoked_at).label("last_invoked_at"),
        )
        .where(*clauses)
        .group_by(EventRow.component_stable_id, EventRow.component_version)
    )
    invoked_components = {
        (row.component_stable_id, row.component_version): (
            int(row.invocations),
            row.last_invoked_at,
        )
        for row in invoked.all()
    }
    invoked_setup = await session.execute(
        select(
            EventRow.setup_stable_id,
            EventRow.setup_version,
            func.count().label("invocations"),
            func.max(EventRow.invoked_at).label("last_invoked_at"),
        )
        .where(*clauses)
        .group_by(EventRow.setup_stable_id, EventRow.setup_version)
    )
    invoked_setups = {
        (row.setup_stable_id, row.setup_version): (int(row.invocations), row.last_invoked_at)
        for row in invoked_setup.all()
    }
    assignments = list(
        (
            await session.scalars(
                select(CorporateCatalogAssignment)
                .where(
                    CorporateCatalogAssignment.organization_id == organization_id,
                    CorporateCatalogAssignment.state == "current",
                )
                .order_by(
                    CorporateCatalogAssignment.object_kind,
                    CorporateCatalogAssignment.stable_id,
                    CorporateCatalogAssignment.version,
                )
            )
        ).all()
    )
    rows: list[RuntimeUsageInstalledRow] = []
    seen: set[tuple[str, str, str | None]] = set()
    for assignment in assignments:
        if not _assignment_visible(assignment, scope):
            continue
        key = (assignment.object_kind, assignment.stable_id, assignment.version)
        if key in seen:
            continue
        seen.add(key)
        counts = (
            invoked_components.get((assignment.stable_id, assignment.version))
            if assignment.object_kind == "component"
            else invoked_setups.get((assignment.stable_id, assignment.version))
        )
        invocations, last_invoked_at = counts if counts is not None else (0, None)
        rows.append(
            RuntimeUsageInstalledRow(
                object_kind=cast("Literal['setup', 'component']", assignment.object_kind),
                stable_id=assignment.stable_id,
                version=assignment.version,
                state="invoked" if invocations else "not_invoked",
                invocations=invocations,
                last_invoked_at=(None if last_invoked_at is None else _stamp(last_invoked_at)),
            )
        )
    return rows


def _assignment_visible(assignment: CorporateCatalogAssignment, scope: UsageScope) -> bool:
    """Whether a scoped caller may see this assignment line in the report."""
    if scope.employees is None:
        return True
    if assignment.account_id is not None:
        return assignment.account_id in scope.employees
    if assignment.team_id is not None:
        return assignment.team_id in scope.team_ids
    # Organization-wide assignment: addressed to everyone.
    return assignment.project_id is None and assignment.technology_id is None


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
    revoked = await _revoked_subjects(session, organization_id=organization_id)
    if revoked:
        revoked_accounts = {subject for kind, subject in revoked if kind == "account"}
        revoked_devices = {subject for kind, subject in revoked if kind == "device"}
        if revoked_accounts:
            clauses.append(EventRow.employee_account_id.not_in(sorted(revoked_accounts)))
        if revoked_devices:
            clauses.append(EventRow.device_id.not_in(sorted(revoked_devices)))
    rows = list(
        (
            await session.scalars(
                select(EventRow)
                .where(*clauses)
                .order_by(EventRow.invoked_at.desc(), EventRow.event_id)
                .offset(query.offset)
                .limit(query.limit)
            )
        ).all()
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
]
