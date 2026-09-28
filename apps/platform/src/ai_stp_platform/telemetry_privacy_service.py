"""Corporate telemetry privacy boundary and governance service (SPEC-089).

The boundary is enumerable: every key a corporate heartbeat or invocation
event may carry is listed here, and every value is scanned for classes of
data that may never enter telemetry storage - credentials, secrets, local
paths, environment values, prompts, and message or repository content.

Governance operations are tenant-scoped through ``set_tenant_scope`` and
cover ingestion with deduplication, bounded reads, aggregates, export,
subject rights (notice, legal basis, revocation), and anonymization or
deletion. Every privileged operation leaves a ``telemetry_audit`` row that
carries counts and identifiers only - never event payloads.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Select, func, select, update
from sqlalchemy import delete as sql_delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_contracts.heartbeat import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_HEARTBEAT_RETRY_BASE_SECONDS,
    DEFAULT_HEARTBEAT_RETRY_MAX_SECONDS,
    DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS,
)
from ai_stp_platform.heartbeat_models import (
    InstallationHeartbeat,
    InstallationHeartbeatEvent,
    InstallationHeartbeatPolicyEvent,
)
from ai_stp_platform.installation_inventory_models import InstallationInventorySnapshot
from ai_stp_platform.installation_usage_models import InstallationOperationFact
from ai_stp_platform.runtime_usage_models import RuntimeUsageEvent
from ai_stp_platform.telemetry_policy_models import (
    TelemetryAudit,
    TelemetryEvent,
    TelemetryPolicy,
    TelemetryRevocation,
)
from ai_stp_platform.tenant_scope import set_tenant_scope

TelemetryEventKind = str
TelemetrySubjectKind = str

TELEMETRY_EVENT_KINDS: frozenset[str] = frozenset({"heartbeat", "invocation"})
TELEMETRY_SUBJECT_KINDS: frozenset[str] = frozenset({"account", "device"})

TELEMETRY_PERMISSIONS: frozenset[str] = frozenset(
    {
        "telemetry.write",
        "telemetry.read",
        "telemetry.list",
        "telemetry.export",
        "telemetry.manage",
        "telemetry.delete",
    }
)

HEARTBEAT_FIELDS: frozenset[str] = frozenset(
    {
        "kind",
        "event_id",
        "account_id",
        "device_id",
        "harness",
        "harness_version",
        "provider_name",
        "provider_version",
        "capabilities",
        "last_sync_at",
        "health",
        "occurred_at",
    }
)

INVOCATION_FIELDS: frozenset[str] = frozenset(
    {
        "kind",
        "event_id",
        "account_id",
        "device_id",
        "project_id",
        "harness",
        "harness_version",
        "setup_id",
        "component_kind",
        "component_stable_id",
        "component_version",
        "outcome",
        "occurred_at",
    }
)

ALLOWED_EVENT_FIELDS: dict[str, frozenset[str]] = {
    "heartbeat": HEARTBEAT_FIELDS,
    "invocation": INVOCATION_FIELDS,
}

FORBIDDEN_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "private_key",
        "client_secret",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "session",
        "email",
        "prompt",
        "payload",
        "input",
        "output",
        "stdin",
        "stdout",
        "command",
        "args",
        "content",
        "contents",
        "body",
        "message",
        "text",
        "path",
        "filepath",
        "file_path",
        "local_path",
        "env",
        "environment",
        "environ",
        "repository",
        "repo",
        "file",
        "files",
        "diagnostics",
    }
)

MAX_EXPORT_ROWS = 1000

#: Clock skew allowance for `occurred_at`: a buffered event is old, never from
#: the future — the same boundary the usage and heartbeat ingests enforce.
MAX_FUTURE_SKEW = timedelta(minutes=5)

_ABSOLUTE_PATH_RE = re.compile(r"(^[A-Za-z]:[\\/])|(^[\\/]{1,2}[^\\/])|(^~[\\/])|(^file://)")
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Z_][A-Z0-9_]{1,63}=")


class TelemetryBoundaryError(ValueError):
    """A telemetry event carried a field or value outside the closed boundary."""

    def __init__(self, fields: Sequence[str]) -> None:
        self.fields = tuple(sorted(set(fields)))
        super().__init__("telemetry event contains forbidden fields: " + ", ".join(self.fields))


class TelemetrySubjectRevokedError(ValueError):
    """The event subject revoked telemetry processing or was deleted."""


class TelemetryPolicyConflictError(ValueError):
    """The policy write did not carry the current policy revision."""


class TelemetryPolicyValidationError(ValueError):
    """A combination of policy values violates a cross-field invariant."""


class TelemetryRightStateError(ValueError):
    """The requested right transition is not legal from the current state."""


def _forbidden_in(value: Any, prefix: str, found: list[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in cast(Mapping[Any, Any], value).items():
            lowered = str(key).lower()
            location = f"{prefix}.{lowered}" if prefix else lowered
            if lowered in FORBIDDEN_FIELD_NAMES or any(
                part in lowered for part in ("password", "secret", "token", "credential", "cookie")
            ):
                found.append(location)
            _forbidden_in(item, location, found)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for index, item in enumerate(cast(Sequence[Any], value)):
            _forbidden_in(item, f"{prefix}[{index}]", found)
    elif isinstance(value, str) and (
        _ABSOLUTE_PATH_RE.search(value) or _ENV_ASSIGNMENT_RE.match(value)
    ):
        found.append(prefix or "value")


def validate_event_fields(kind: str, fields: Mapping[str, Any]) -> None:
    """Reject any event carrying keys outside the closed set or unsafe values.

    Unknown keys, known dangerous names at any nesting level, absolute local
    paths, and `NAME=value` environment-style strings are all rejected.
    """
    allowed = ALLOWED_EVENT_FIELDS.get(kind)
    if allowed is None:
        raise TelemetryBoundaryError((f"kind={kind!r}",))
    rejected: list[str] = [key for key in fields if key not in allowed]
    _forbidden_in(fields, "", rejected)
    if rejected:
        raise TelemetryBoundaryError(rejected)


def event_columns(kind: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the event and return only the allowlisted storage columns."""
    validate_event_fields(kind, fields)
    allowed = ALLOWED_EVENT_FIELDS[kind]
    return {key: fields[key] for key in allowed if key in fields}


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


async def record_privileged_access(
    session: AsyncSession,
    *,
    organization_id: str,
    actor_account_id: str | None,
    action: str,
    target_table: str,
    target_id: str,
    request_id: str | None = None,
    detail: Mapping[str, object] | None = None,
) -> TelemetryAudit:
    """Append one governance audit row; ``detail`` carries counts, not payloads."""
    await set_tenant_scope(session, organization_id)
    row = TelemetryAudit(
        organization_id=organization_id,
        actor_account_id=actor_account_id,
        action=action,
        target_table=target_table,
        target_id=target_id,
        request_id=request_id,
        detail=dict(detail or {}),
    )
    session.add(row)
    await session.flush()
    return row


async def get_right(
    session: AsyncSession, *, organization_id: str, subject_kind: str, subject_id: str
) -> TelemetryRevocation | None:
    await set_tenant_scope(session, organization_id)
    return await session.get(TelemetryRevocation, (organization_id, subject_kind, subject_id))


async def _subject_blocked(
    session: AsyncSession, *, organization_id: str, columns: Mapping[str, Any]
) -> None:
    for kind, key in (("account", "account_id"), ("device", "device_id")):
        subject_id = columns.get(key)
        if subject_id is None:
            continue
        right = await get_right(
            session,
            organization_id=organization_id,
            subject_kind=kind,
            subject_id=str(subject_id),
        )
        if right is not None and right.state in {"revoked", "deleted"}:
            raise TelemetrySubjectRevokedError(f"{kind}:{subject_id}")


async def require_subject_active(
    session: AsyncSession, *, organization_id: str, account_id: str, device_id: str
) -> None:
    """Reject heartbeat writes for an account or device whose telemetry was revoked."""
    await set_tenant_scope(session, organization_id)
    await _subject_blocked(
        session,
        organization_id=organization_id,
        columns={"account_id": account_id, "device_id": device_id},
    )


async def ingest_event(
    session: AsyncSession,
    *,
    organization_id: str,
    kind: str,
    fields: Mapping[str, Any],
) -> tuple[TelemetryEvent, bool]:
    """Validate, deduplicate, and persist one telemetry event.

    Returns ``(row, created)``: a repeated ``event_id`` inside the tenant
    returns the originally stored row unchanged. Events whose account or
    device subject is revoked or erased are rejected before storage.
    """
    await set_tenant_scope(session, organization_id)
    columns = event_columns(kind, fields)
    await _subject_blocked(session, organization_id=organization_id, columns=columns)
    occurred = _parse_timestamp(columns.get("occurred_at"))
    if occurred is not None and occurred > datetime.now(UTC) + MAX_FUTURE_SKEW:
        # A buffered event is old, never from the future: a far-future
        # timestamp would pin ordering and outlive every retention sweep —
        # the same boundary the usage-event ingest already enforces.
        raise TelemetryBoundaryError(("occurred_at",))
    existing = await session.scalar(
        select(TelemetryEvent).where(
            TelemetryEvent.organization_id == organization_id,
            TelemetryEvent.event_id == str(columns["event_id"]),
        )
    )
    if existing is not None:
        return existing, False
    row = TelemetryEvent(
        organization_id=organization_id,
        event_id=str(columns["event_id"]),
        kind=kind,
        account_id=columns.get("account_id"),
        device_id=columns.get("device_id"),
        project_id=columns.get("project_id"),
        harness=str(columns["harness"]),
        harness_version=columns.get("harness_version"),
        provider_name=columns.get("provider_name"),
        provider_version=columns.get("provider_version"),
        capabilities=list(columns.get("capabilities") or []),
        last_sync_at=_parse_timestamp(columns.get("last_sync_at")),
        health=columns.get("health"),
        setup_id=columns.get("setup_id"),
        component_kind=columns.get("component_kind"),
        component_stable_id=columns.get("component_stable_id"),
        component_version=columns.get("component_version"),
        outcome=columns.get("outcome"),
        subject_state="active",
        occurred_at=_parse_timestamp(columns["occurred_at"]) or datetime.now(UTC),
    )
    session.add(row)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        # A concurrent ingest of the same event_id committed between the
        # existence read and this flush: the stored row wins, the verdict is
        # the same duplicate outcome the read path returns.
        existing = await session.scalar(
            select(TelemetryEvent).where(
                TelemetryEvent.organization_id == organization_id,
                TelemetryEvent.event_id == str(columns["event_id"]),
            )
        )
        if existing is None:
            raise
        return existing, False
    return row, True


async def read_policy(session: AsyncSession, *, organization_id: str) -> TelemetryPolicy | None:
    await set_tenant_scope(session, organization_id)
    return await session.get(TelemetryPolicy, organization_id)


async def write_policy(
    session: AsyncSession,
    *,
    organization_id: str,
    raw_retention_days: int,
    aggregate_retention_days: int,
    legal_basis: str,
    notice_text: str | None,
    notice_revision: int,
    heartbeat_enabled: bool | None = None,
    inventory_scan_enabled: bool | None = None,
    usage_collection_enabled: bool | None = None,
    usage_registration_required: bool | None = None,
    report_timezone: str | None = None,
    heartbeat_interval_seconds: int | None = None,
    heartbeat_retry_base_seconds: int | None = None,
    heartbeat_retry_max_seconds: int | None = None,
    heartbeat_stale_after_seconds: int | None = None,
    expected_policy_revision: int,
    updated_by: str | None,
) -> TelemetryPolicy:
    await set_tenant_scope(session, organization_id)
    row = await session.get(TelemetryPolicy, organization_id)
    retry_base = (
        heartbeat_retry_base_seconds
        if heartbeat_retry_base_seconds is not None
        else (
            row.heartbeat_retry_base_seconds
            if row is not None
            else DEFAULT_HEARTBEAT_RETRY_BASE_SECONDS
        )
    )
    retry_max = (
        heartbeat_retry_max_seconds
        if heartbeat_retry_max_seconds is not None
        else (
            row.heartbeat_retry_max_seconds
            if row is not None
            else DEFAULT_HEARTBEAT_RETRY_MAX_SECONDS
        )
    )
    if retry_max < retry_base:
        raise TelemetryPolicyValidationError("heartbeat retry maximum must cover its retry base")
    effective_usage_enabled = (
        usage_collection_enabled
        if usage_collection_enabled is not None
        else (row.usage_collection_enabled if row is not None else False)
    )
    effective_usage_required = (
        usage_registration_required
        if usage_registration_required is not None
        else (row.usage_registration_required if row is not None else False)
    )
    if effective_usage_required and not effective_usage_enabled:
        raise TelemetryPolicyValidationError("required usage registration needs usage collection")
    if report_timezone is not None:
        try:
            ZoneInfo(report_timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise TelemetryPolicyValidationError(
                "report timezone must be an IANA timezone"
            ) from error
    if row is None:
        if expected_policy_revision != 0:
            raise TelemetryPolicyConflictError("telemetry policy does not exist")
        row = TelemetryPolicy(
            organization_id=organization_id,
            raw_retention_days=raw_retention_days,
            aggregate_retention_days=aggregate_retention_days,
            legal_basis=legal_basis,
            notice_text=notice_text,
            notice_revision=notice_revision,
            heartbeat_enabled=(True if heartbeat_enabled is None else heartbeat_enabled),
            inventory_scan_enabled=(
                False if inventory_scan_enabled is None else inventory_scan_enabled
            ),
            usage_collection_enabled=effective_usage_enabled,
            usage_registration_required=effective_usage_required,
            report_timezone=report_timezone or "UTC",
            heartbeat_interval_seconds=(
                DEFAULT_HEARTBEAT_INTERVAL_SECONDS
                if heartbeat_interval_seconds is None
                else heartbeat_interval_seconds
            ),
            heartbeat_retry_base_seconds=(
                DEFAULT_HEARTBEAT_RETRY_BASE_SECONDS
                if heartbeat_retry_base_seconds is None
                else heartbeat_retry_base_seconds
            ),
            heartbeat_retry_max_seconds=(
                DEFAULT_HEARTBEAT_RETRY_MAX_SECONDS
                if heartbeat_retry_max_seconds is None
                else heartbeat_retry_max_seconds
            ),
            heartbeat_stale_after_seconds=(
                DEFAULT_HEARTBEAT_STALE_AFTER_SECONDS
                if heartbeat_stale_after_seconds is None
                else heartbeat_stale_after_seconds
            ),
            policy_version=1,
            updated_by=updated_by,
        )
        session.add(row)
        session.add(
            InstallationHeartbeatPolicyEvent(
                organization_id=organization_id,
                version=1,
                effective_from=datetime.now(UTC),
                enabled=row.heartbeat_enabled,
                interval_seconds=row.heartbeat_interval_seconds,
                stale_after_seconds=row.heartbeat_stale_after_seconds,
            )
        )
        await session.flush()
        return row
    if row.policy_version != expected_policy_revision:
        raise TelemetryPolicyConflictError("telemetry policy revision is stale")
    row.raw_retention_days = raw_retention_days
    row.aggregate_retention_days = aggregate_retention_days
    row.legal_basis = legal_basis
    row.notice_text = notice_text
    row.notice_revision = notice_revision
    if heartbeat_enabled is not None:
        row.heartbeat_enabled = heartbeat_enabled
    if inventory_scan_enabled is not None:
        row.inventory_scan_enabled = inventory_scan_enabled
    if usage_collection_enabled is not None:
        row.usage_collection_enabled = usage_collection_enabled
    if usage_registration_required is not None:
        row.usage_registration_required = usage_registration_required
    if report_timezone is not None:
        row.report_timezone = report_timezone
    if heartbeat_interval_seconds is not None:
        row.heartbeat_interval_seconds = heartbeat_interval_seconds
    if heartbeat_retry_base_seconds is not None:
        row.heartbeat_retry_base_seconds = heartbeat_retry_base_seconds
    if heartbeat_retry_max_seconds is not None:
        row.heartbeat_retry_max_seconds = heartbeat_retry_max_seconds
    if heartbeat_stale_after_seconds is not None:
        row.heartbeat_stale_after_seconds = heartbeat_stale_after_seconds
    row.policy_version += 1
    session.add(
        InstallationHeartbeatPolicyEvent(
            organization_id=organization_id,
            version=row.policy_version,
            effective_from=datetime.now(UTC),
            enabled=row.heartbeat_enabled,
            interval_seconds=row.heartbeat_interval_seconds,
            stale_after_seconds=row.heartbeat_stale_after_seconds,
        )
    )
    row.updated_by = updated_by
    await session.flush()
    return row


async def record_right(
    session: AsyncSession,
    *,
    organization_id: str,
    subject_kind: str,
    subject_id: str,
    legal_basis: str,
    notice_revision: int,
    now: datetime,
) -> TelemetryRevocation:
    """Record or re-acknowledge a subject's notice and legal basis."""
    await set_tenant_scope(session, organization_id)
    row = await session.get(TelemetryRevocation, (organization_id, subject_kind, subject_id))
    if row is not None and row.state == "deleted":
        raise TelemetryRightStateError("telemetry subject was erased")
    if row is None:
        row = TelemetryRevocation(
            organization_id=organization_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
        )
        session.add(row)
    row.state = "active"
    row.legal_basis = legal_basis
    row.notice_revision = notice_revision
    row.notice_acknowledged_at = now
    row.revoked_at = None
    row.anonymized_at = None
    row.deletion_requested_at = None
    row.deleted_at = None
    await session.flush()
    return row


def _subject_predicate(subject_kind: str, subject_id: str):
    if subject_kind == "device":
        return TelemetryEvent.device_id == subject_id
    return TelemetryEvent.account_id == subject_id


async def _erase_stream_subject_rows(
    session: AsyncSession,
    *,
    organization_id: str,
    subject_kind: str,
    subject_id: str,
) -> int:
    """Delete the subject's rows from stream-owned governed tables.

    `runtime_usage_event`, `installation_operation_fact`, and
    `installation_heartbeat` carry subject
    identifiers in NOT NULL columns by design, so erasure there is physical
    deletion rather than in-place anonymization. Heartbeat rows are current
    installation state; removing them on erasure also stops the installation
    from surfacing in health reports.
    """
    if subject_kind == "device":
        usage_predicate = RuntimeUsageEvent.device_id == subject_id
        installation_predicate = InstallationOperationFact.device_id == subject_id
        inventory_predicate = InstallationInventorySnapshot.device_id == subject_id
        heartbeat_predicate = InstallationHeartbeat.device_id == subject_id
        heartbeat_event_predicate = InstallationHeartbeatEvent.device_id == subject_id
    else:
        usage_predicate = RuntimeUsageEvent.employee_account_id == subject_id
        installation_predicate = InstallationOperationFact.employee_account_id == subject_id
        inventory_predicate = InstallationInventorySnapshot.employee_account_id == subject_id
        heartbeat_predicate = InstallationHeartbeat.account_id == subject_id
        heartbeat_event_predicate = InstallationHeartbeatEvent.account_id == subject_id
    removed = 0
    for statement in (
        sql_delete(RuntimeUsageEvent).where(
            RuntimeUsageEvent.organization_id == organization_id, usage_predicate
        ),
        sql_delete(InstallationOperationFact).where(
            InstallationOperationFact.organization_id == organization_id,
            installation_predicate,
        ),
        sql_delete(InstallationInventorySnapshot).where(
            InstallationInventorySnapshot.organization_id == organization_id,
            inventory_predicate,
        ),
        sql_delete(InstallationHeartbeat).where(
            InstallationHeartbeat.organization_id == organization_id, heartbeat_predicate
        ),
        sql_delete(InstallationHeartbeatEvent).where(
            InstallationHeartbeatEvent.organization_id == organization_id, heartbeat_event_predicate
        ),
    ):
        result = await session.execute(statement)
        rowcount = getattr(result, "rowcount", 0)
        if isinstance(rowcount, int):
            removed += rowcount
    return removed


async def anonymize_subject(
    session: AsyncSession,
    *,
    organization_id: str,
    subject_kind: str,
    subject_id: str,
    now: datetime,
) -> int:
    """Strip subject identifiers from retained events; event rows remain.

    Stream-owned governed tables (`runtime_usage_event`,
    `installation_heartbeat`) cannot anonymize in place - their subject
    columns are NOT NULL by design - so the subject's rows there are
    deleted instead.
    """
    del now
    await set_tenant_scope(session, organization_id)
    result = await session.execute(
        update(TelemetryEvent)
        .where(
            TelemetryEvent.organization_id == organization_id,
            _subject_predicate(subject_kind, subject_id),
        )
        .values(account_id=None, device_id=None, subject_state="anonymized")
    )
    rowcount = getattr(result, "rowcount", 0)
    affected = rowcount if isinstance(rowcount, int) else 0
    affected += await _erase_stream_subject_rows(
        session,
        organization_id=organization_id,
        subject_kind=subject_kind,
        subject_id=subject_id,
    )
    return affected


async def revoke_subject(
    session: AsyncSession,
    *,
    organization_id: str,
    subject_kind: str,
    subject_id: str,
    anonymize: bool,
    now: datetime,
) -> tuple[TelemetryRevocation, int]:
    """Revoke telemetry processing; optionally anonymize retained events."""
    await set_tenant_scope(session, organization_id)
    row = await session.get(TelemetryRevocation, (organization_id, subject_kind, subject_id))
    if row is not None and row.state == "deleted":
        raise TelemetryRightStateError("telemetry subject was erased")
    if row is None:
        row = TelemetryRevocation(
            organization_id=organization_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
        )
        session.add(row)
    row.state = "revoked"
    row.revoked_at = now
    anonymized = 0
    if anonymize:
        anonymized = await anonymize_subject(
            session,
            organization_id=organization_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
            now=now,
        )
        row.anonymized_at = now
    await session.flush()
    return row, anonymized


async def delete_subject(
    session: AsyncSession,
    *,
    organization_id: str,
    subject_kind: str,
    subject_id: str,
    mode: str,
    now: datetime,
) -> tuple[TelemetryRevocation, int]:
    """Apply a data-rights erasure: physical delete or anonymization.

    Both modes are idempotent - a repeated request finds no remaining subject
    rows and returns the same terminal state.
    """
    await set_tenant_scope(session, organization_id)
    row = await session.get(TelemetryRevocation, (organization_id, subject_kind, subject_id))
    if row is None:
        row = TelemetryRevocation(
            organization_id=organization_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
        )
        session.add(row)
    if mode == "delete":
        result = await session.execute(
            sql_delete(TelemetryEvent).where(
                TelemetryEvent.organization_id == organization_id,
                _subject_predicate(subject_kind, subject_id),
            )
        )
        deleted = getattr(result, "rowcount", 0)
        affected = deleted if isinstance(deleted, int) else 0
        affected += await _erase_stream_subject_rows(
            session,
            organization_id=organization_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
        )
        row.state = "deleted"
        row.deleted_at = now
    else:
        affected = await anonymize_subject(
            session,
            organization_id=organization_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
            now=now,
        )
        if row.state != "deleted":
            row.state = "revoked"
        row.anonymized_at = now
    row.deletion_requested_at = row.deletion_requested_at or now
    await session.flush()
    return row, affected


def _event_cursor(
    query: Select[tuple[TelemetryEvent]],
    before_occurred_at: datetime | None,
    before_id: str | None,
) -> Select[tuple[TelemetryEvent]]:
    occurred = func.date_trunc("milliseconds", TelemetryEvent.occurred_at)
    if before_occurred_at is not None:
        if before_id is None:
            return query.where(occurred < before_occurred_at)
        return query.where(
            (occurred < before_occurred_at)
            | ((occurred == before_occurred_at) & (TelemetryEvent.event_id < before_id))
        )
    if before_id is not None:
        return query.where(TelemetryEvent.event_id < before_id)
    return query


async def list_events(
    session: AsyncSession,
    *,
    organization_id: str,
    event_kind: str | None = None,
    account_id: str | None = None,
    before_occurred_at: datetime | None = None,
    before_id: str | None = None,
    limit: int = 50,
) -> list[TelemetryEvent]:
    """Bounded tenant-scoped raw event page, newest first."""
    await set_tenant_scope(session, organization_id)
    occurred = func.date_trunc("milliseconds", TelemetryEvent.occurred_at)
    query = select(TelemetryEvent).where(TelemetryEvent.organization_id == organization_id)
    if event_kind is not None:
        query = query.where(TelemetryEvent.kind == event_kind)
    if account_id is not None:
        query = query.where(TelemetryEvent.account_id == account_id)
    query = _event_cursor(query, before_occurred_at, before_id)
    rows = await session.scalars(
        query.order_by(occurred.desc(), TelemetryEvent.event_id.desc()).limit(limit + 1)
    )
    return list(rows.all())


async def aggregate_events(
    session: AsyncSession,
    *,
    organization_id: str,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
) -> list[tuple[str, str, str | None, int]]:
    """Tenant-scoped day/kind/outcome counts; subject fields never group."""
    await set_tenant_scope(session, organization_id)
    day = func.date(TelemetryEvent.occurred_at)
    query = (
        select(
            day.label("day"),
            TelemetryEvent.kind,
            TelemetryEvent.outcome,
            func.count().label("event_count"),
        )
        .where(TelemetryEvent.organization_id == organization_id)
        .group_by(day, TelemetryEvent.kind, TelemetryEvent.outcome)
        .order_by(day, TelemetryEvent.kind, TelemetryEvent.outcome)
    )
    if occurred_from is not None:
        query = query.where(TelemetryEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        query = query.where(TelemetryEvent.occurred_at <= occurred_to)
    return [
        (str(row.day), str(row.kind), row.outcome, int(row.event_count))
        for row in (await session.execute(query)).all()
    ]


async def export_events(
    session: AsyncSession,
    *,
    organization_id: str,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = MAX_EXPORT_ROWS,
) -> list[TelemetryEvent]:
    """Bounded tenant-scoped export of raw events, oldest first."""
    await set_tenant_scope(session, organization_id)
    query = select(TelemetryEvent).where(TelemetryEvent.organization_id == organization_id)
    if occurred_from is not None:
        query = query.where(TelemetryEvent.occurred_at >= occurred_from)
    if occurred_to is not None:
        query = query.where(TelemetryEvent.occurred_at <= occurred_to)
    rows = await session.scalars(
        query.order_by(TelemetryEvent.occurred_at, TelemetryEvent.event_id).limit(
            min(limit, MAX_EXPORT_ROWS)
        )
    )
    return list(rows.all())


async def list_privileged_access(
    session: AsyncSession,
    *,
    organization_id: str,
    before_id: int | None = None,
    limit: int = 50,
) -> list[TelemetryAudit]:
    """Bounded tenant-scoped page of governance audit rows, newest first."""
    await set_tenant_scope(session, organization_id)
    query: Select[tuple[TelemetryAudit]] = select(TelemetryAudit).where(
        TelemetryAudit.organization_id == organization_id
    )
    if before_id is not None:
        query = query.where(TelemetryAudit.id < before_id)
    rows = await session.scalars(query.order_by(TelemetryAudit.id.desc()).limit(limit + 1))
    return list(rows.all())


__all__ = [
    "ALLOWED_EVENT_FIELDS",
    "FORBIDDEN_FIELD_NAMES",
    "HEARTBEAT_FIELDS",
    "INVOCATION_FIELDS",
    "MAX_EXPORT_ROWS",
    "TELEMETRY_EVENT_KINDS",
    "TELEMETRY_PERMISSIONS",
    "TELEMETRY_SUBJECT_KINDS",
    "TelemetryBoundaryError",
    "TelemetryEventKind",
    "TelemetryPolicyConflictError",
    "TelemetryPolicyValidationError",
    "TelemetryRightStateError",
    "TelemetrySubjectKind",
    "TelemetrySubjectRevokedError",
    "aggregate_events",
    "anonymize_subject",
    "delete_subject",
    "event_columns",
    "export_events",
    "get_right",
    "ingest_event",
    "list_events",
    "list_privileged_access",
    "read_policy",
    "record_privileged_access",
    "record_right",
    "require_subject_active",
    "revoke_subject",
    "validate_event_fields",
    "write_policy",
]
