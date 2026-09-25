"""Fixed corporate heartbeat report over current installations and accepted signals."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from math import ceil
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_api.slices.corporate.dashboard import visible_accounts
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.heartbeat import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    HeartbeatReport,
    HeartbeatReportBucket,
    HeartbeatReportEmployee,
    HeartbeatReportRow,
    HeartbeatReportTeam,
)
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.heartbeat_models import (
    InstallationHeartbeat,
    InstallationHeartbeatEvent,
    InstallationHeartbeatPolicyEvent,
)
from ai_stp_platform.heartbeat_service import evaluate_health, organization_policy
from ai_stp_platform.models import Account, Device
from ai_stp_platform.organization_models import CorporateTeam, OrganizationMembership
from ai_stp_platform.telemetry_privacy_service import record_privileged_access

router = APIRouter(tags=["corporate"])
View = Literal["current", "history"]
Period = Literal["24h", "7d", "30d", "custom"]
Sort = Literal["employee", "team", "last_heartbeat", "status", "coverage"]
Status = Literal["active", "stale", "failing", "disabled", "unknown"]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def heartbeat_buckets(
    *,
    events: list[InstallationHeartbeatEvent],
    policies: list[InstallationHeartbeatPolicyEvent],
    start: datetime,
    end: datetime,
    default_interval: int,
    first_seen: datetime | None = None,
    initial_state: str = "active",
    end_expected_at: datetime | None = None,
) -> tuple[list[HeartbeatReportBucket], int | None]:
    """Map accepted signals to time buckets; expected cadence follows policy revisions."""
    count = 60
    span = (end - start).total_seconds() / count
    ordered_events = sorted(events, key=lambda event: _aware(event.received_at))
    event_times = [_aware(event.received_at) for event in ordered_events]
    first = (
        _aware(first_seen) if first_seen is not None else (event_times[0] if event_times else None)
    )
    changes = sorted(policies, key=lambda policy: policy.effective_from)
    change_times = [_aware(change.effective_from) for change in changes]
    buckets: list[HeartbeatReportBucket] = []
    total_expected = total_received = 0
    for index in range(count):
        left = start + timedelta(seconds=index * span)
        right = end if index == count - 1 else start + timedelta(seconds=(index + 1) * span)
        event_start = bisect_left(event_times, left)
        event_end = bisect_left(event_times, right)
        received = event_end - event_start
        expected = 0
        if first is not None and right > first:
            boundaries = [left, right]
            boundaries.extend(
                change_times[bisect_right(change_times, left) : bisect_left(change_times, right)]
            )
            boundaries.extend(event_times[bisect_right(event_times, left) : event_end])
            if end_expected_at is not None and left < _aware(end_expected_at) < right:
                boundaries.append(_aware(end_expected_at))
            ordered = sorted(boundaries)
            for segment_start, segment_end in pairwise(ordered):
                if end_expected_at is not None and segment_start >= _aware(end_expected_at):
                    continue
                prior_index = bisect_right(event_times, segment_start) - 1
                reported = (
                    ordered_events[prior_index].reported_state
                    if prior_index >= 0
                    else initial_state
                )
                if reported == "disabled":
                    continue
                policy_index = bisect_right(change_times, segment_start) - 1
                policy = changes[policy_index] if policy_index >= 0 else None
                if policy is not None and not policy.enabled:
                    continue
                interval = policy.interval_seconds if policy is not None else default_interval
                anchor = max(first, _aware(policy.effective_from)) if policy is not None else first
                if segment_end <= anchor:
                    continue
                from_slot = max(0, ceil((segment_start - anchor).total_seconds() / interval))
                to_slot = max(0, ceil((segment_end - anchor).total_seconds() / interval))
                expected += max(0, to_slot - from_slot)
        total_expected += expected
        total_received += min(received, expected)
        state: Literal["healthy", "partial", "missing", "not_expected"] = (
            "not_expected"
            if expected == 0
            else "missing"
            if received == 0
            else "healthy"
            if received >= expected
            else "partial"
        )
        buckets.append(
            HeartbeatReportBucket(
                start=format_timestamp(left),
                end=format_timestamp(right),
                expected=expected,
                received=received,
                state=state,
            )
        )
    coverage = round(100 * total_received / total_expected) if total_expected else None
    return buckets, coverage


@router.get(
    "/corporate/organizations/{organization_id}/telemetry/heartbeat-report",
    response_model=HeartbeatReport,
)
async def heartbeat_report(
    organization_id: OrganizationId,
    request: Request,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    view: View = "current",
    period: Period = "7d",
    from_date: date | None = None,
    to_date: date | None = None,
    team: Annotated[list[str] | None, Query()] = None,
    employee: Annotated[list[str] | None, Query()] = None,
    status: Annotated[list[Status] | None, Query()] = None,
    sort: Sort = "last_heartbeat",
    order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> HeartbeatReport:
    """Return only members and devices within the caller's current corporate scope."""
    _, membership = await service.organization_and_membership(
        db, ctx=ctx, organization_id=organization_id
    )
    if membership.role not in {"lead", "superadmin"}:
        raise ApiError(ErrorCategory.PERMISSION, "heartbeat report requires a lead role")
    if membership.role == "superadmin":
        await service.authorize(
            db, ctx=ctx, organization_id=organization_id, permission="telemetry.read"
        )
    allowed, teams_by_account = await visible_accounts(
        db, ctx=ctx, organization_id=organization_id, superadmin=membership.role == "superadmin"
    )
    policy = await organization_policy(db, organization_id=organization_id)
    now = datetime.now(UTC)
    teams = {
        row.id: row.name
        for row in (
            await db.scalars(
                select(CorporateTeam).where(
                    CorporateTeam.organization_id == organization_id,
                    CorporateTeam.state == "active",
                )
            )
        ).all()
    }
    visible_teams = sorted(
        {team_id for account_id in allowed for team_id in teams_by_account.get(account_id, [])}
    )
    memberships = {
        row.account_id: row
        for row in (
            await db.scalars(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.account_id.in_(allowed or {""}),
                    OrganizationMembership.state == "active",
                )
            )
        ).all()
    }
    accounts = {
        row.id: row
        for row in (await db.scalars(select(Account).where(Account.id.in_(allowed or {""})))).all()
    }

    def employee_name(account_id: str) -> str:
        member = memberships.get(account_id)
        account = accounts.get(account_id)
        return (
            (member.display_name if member else None)
            or (account.display_name if account else None)
            or "Employee"
        )

    devices = list(
        (
            await db.scalars(
                select(Device).where(
                    Device.account_id.in_(allowed or {""}), Device.device_type == "cli"
                )
            )
        ).all()
    )
    latest = {
        row.device_id: row
        for row in (
            await db.scalars(
                select(InstallationHeartbeat).where(
                    InstallationHeartbeat.organization_id == organization_id,
                    InstallationHeartbeat.account_id.in_(allowed or {""}),
                )
            )
        ).all()
    }
    rows: list[HeartbeatReportRow] = []
    for device in devices:
        team_ids = [id for id in teams_by_account.get(device.account_id, []) if id in teams]
        if team and not set(team_ids).intersection(team):
            continue
        if employee and device.account_id not in employee:
            continue
        beat = latest.get(device.id)
        state = (
            evaluate_health(
                beat.reported_state,
                beat.received_at,
                now=now,
                stale_after=timedelta(seconds=policy.stale_after_seconds),
            )
            if beat is not None
            else "unknown"
        )
        report_state: Status = (
            "disabled"
            if not policy.enabled or device.state == "revoked"
            else "failing"
            if state == "partial"
            else state
        )
        if status and report_state not in status:
            continue
        rows.append(
            HeartbeatReportRow(
                account_id=device.account_id,
                employee_name=employee_name(device.account_id),
                teams=[HeartbeatReportTeam(id=id, name=teams[id]) for id in team_ids],
                device_id=device.id,
                device_name=device.display_name or "CLI device",
                last_heartbeat_at=(format_timestamp(_aware(beat.received_at)) if beat else None),
                status=report_state,
            )
        )

    def sort_key(row: HeartbeatReportRow) -> str | datetime | int:
        if sort == "employee":
            return row.employee_name.casefold()
        if sort == "team":
            return row.teams[0].name.casefold() if row.teams else ""
        if sort == "status":
            return row.status
        if sort == "coverage":
            return row.coverage_percent if row.coverage_percent is not None else -1
        if row.last_heartbeat_at:
            return datetime.fromisoformat(row.last_heartbeat_at.replace("Z", "+00:00"))
        return datetime.min.replace(tzinfo=UTC)

    rows.sort(key=sort_key, reverse=order == "desc")
    total = len(rows)
    start = end = now
    if view == "history":
        if period == "custom":
            if from_date is None or to_date is None or to_date < from_date:
                raise ApiError(
                    ErrorCategory.VALIDATION, "valid custom heartbeat dates are required"
                )
            start = datetime.combine(from_date, time.min, tzinfo=UTC)
            end = min(now, datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC))
            if end <= start or end - start > timedelta(days=31):
                raise ApiError(ErrorCategory.VALIDATION, "heartbeat period must be within 31 days")
        else:
            start = now - timedelta(days={"24h": 1, "7d": 7, "30d": 30}[period])
            end = now
    if view == "history" and rows:
        ids = [row.device_id for row in rows]
        first_events = dict(
            cast(
                list[tuple[str, datetime]],
                (
                    await db.execute(
                        select(
                            InstallationHeartbeatEvent.device_id,
                            func.min(InstallationHeartbeatEvent.received_at),
                        )
                        .where(
                            InstallationHeartbeatEvent.organization_id == organization_id,
                            InstallationHeartbeatEvent.device_id.in_(ids),
                        )
                        .group_by(InstallationHeartbeatEvent.device_id)
                    )
                ).all(),
            )
        )
        latest_before = (
            select(
                InstallationHeartbeatEvent.device_id,
                func.max(InstallationHeartbeatEvent.checked_at).label("checked_at"),
            )
            .where(
                InstallationHeartbeatEvent.organization_id == organization_id,
                InstallationHeartbeatEvent.device_id.in_(ids),
                InstallationHeartbeatEvent.received_at < start,
            )
            .group_by(InstallationHeartbeatEvent.device_id)
            .subquery()
        )
        initial_states = {
            event.device_id: event.reported_state
            for event in (
                await db.scalars(
                    select(InstallationHeartbeatEvent).join(
                        latest_before,
                        (InstallationHeartbeatEvent.device_id == latest_before.c.device_id)
                        & (InstallationHeartbeatEvent.checked_at == latest_before.c.checked_at),
                    )
                )
            ).all()
        }
        events = list(
            (
                await db.scalars(
                    select(InstallationHeartbeatEvent)
                    .where(
                        InstallationHeartbeatEvent.organization_id == organization_id,
                        InstallationHeartbeatEvent.device_id.in_(ids),
                        InstallationHeartbeatEvent.received_at >= start,
                        InstallationHeartbeatEvent.received_at < end,
                    )
                    .order_by(InstallationHeartbeatEvent.received_at)
                    .limit(100_001)
                )
            ).all()
        )
        if len(events) > 100_000:
            raise ApiError(ErrorCategory.VALIDATION, "heartbeat report exceeds history limit")
        by_device: dict[str, list[InstallationHeartbeatEvent]] = defaultdict(list)
        for event in events:
            by_device[event.device_id].append(event)
        policies = list(
            (
                await db.scalars(
                    select(InstallationHeartbeatPolicyEvent)
                    .where(InstallationHeartbeatPolicyEvent.organization_id == organization_id)
                    .order_by(InstallationHeartbeatPolicyEvent.effective_from)
                )
            ).all()
        )
        with_history: list[HeartbeatReportRow] = []
        devices_by_id = {device.id: device for device in devices}
        for row in rows:
            device_events = by_device[row.device_id]
            buckets, coverage = heartbeat_buckets(
                events=device_events,
                policies=policies,
                start=start,
                end=end,
                default_interval=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
                first_seen=first_events.get(row.device_id),
                initial_state=initial_states.get(row.device_id, "active"),
                end_expected_at=(
                    devices_by_id[row.device_id].updated_at
                    if devices_by_id[row.device_id].state == "revoked"
                    else None
                ),
            )
            with_history.append(
                row.model_copy(
                    update={
                        "buckets": buckets,
                        "coverage_percent": coverage,
                        "last_heartbeat_at": (
                            format_timestamp(_aware(device_events[-1].received_at))
                            if device_events
                            else None
                        ),
                    }
                )
            )
        rows = with_history
        if sort == "coverage":
            rows.sort(
                key=lambda row: row.coverage_percent if row.coverage_percent is not None else -1,
                reverse=order == "desc",
            )
        elif sort == "last_heartbeat":
            rows.sort(key=sort_key, reverse=order == "desc")
    rows = rows[(page - 1) * page_size : page * page_size]
    await record_privileged_access(
        db,
        organization_id=organization_id,
        actor_account_id=ctx.account_id,
        action="telemetry.list",
        target_table=(
            "installation_heartbeat_event" if view == "history" else "installation_heartbeat"
        ),
        target_id=organization_id,
        request_id=getattr(request.state, "request_id", None),
        detail={"view": view, "returned": len(rows)},
    )
    await db.commit()
    return HeartbeatReport(
        organization_id=organization_id,
        evaluated_at=format_timestamp(now),
        interval_seconds=policy.interval_seconds,
        stale_after_seconds=policy.stale_after_seconds,
        total=total,
        page=page,
        page_size=page_size,
        teams=[HeartbeatReportTeam(id=id, name=teams[id]) for id in visible_teams],
        employees=[
            HeartbeatReportEmployee(
                id=id, name=employee_name(id), team_ids=teams_by_account.get(id, [])
            )
            for id in memberships
        ],
        items=rows,
    )
