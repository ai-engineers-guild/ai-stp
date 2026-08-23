"""Persist public complaints and enforce configured intake limits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import blake2b

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import ComplaintSettings
from ai_stp_contracts.complaints import ComplaintCreateRequest, ComplaintCreateResponse
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.models import ComplaintIntake

_FORBIDDEN_PAYLOAD_MARKERS = (
    "password",
    "secret",
    "token",
    "private_key",
    ".env",
    "home/",
    "c:\\users\\",
)


def _scan_forbidden(text: str) -> None:
    lowered = text.lower()
    for marker in _FORBIDDEN_PAYLOAD_MARKERS:
        if marker in lowered:
            raise ApiError(ErrorCategory.VALIDATION, "complaint payload contains forbidden content")


def submitter_key(*, account_id: str | None, reply_email: str) -> str:
    if account_id:
        return account_id
    return f"email:{reply_email.casefold()}"


async def create_complaint(
    db: AsyncSession,
    *,
    ctx: AuthContext | None,
    body: ComplaintCreateRequest,
    limits: ComplaintSettings,
) -> ComplaintCreateResponse:
    _scan_forbidden(body.sender_name)
    _scan_forbidden(body.subject)
    _scan_forbidden(body.message)
    _scan_forbidden(body.target)
    account_id = ctx.account_id if ctx is not None else None
    key = submitter_key(account_id=account_id, reply_email=body.reply_email)
    await _lock_rate_limit(db, f"submitter:{key}")
    await _lock_rate_limit(db, f"target:{body.target_kind}:{body.target}")
    now = datetime.now(UTC)
    await _enforce_limit(
        db,
        ComplaintIntake.submitter_key == key,
        since=now - timedelta(seconds=limits.submitter_window_seconds),
        maximum=limits.submitter_limit,
    )
    await _enforce_limit(
        db,
        ComplaintIntake.target_kind == body.target_kind,
        ComplaintIntake.target == body.target,
        since=now - timedelta(seconds=limits.target_window_seconds),
        maximum=limits.target_limit,
    )
    row = ComplaintIntake(
        id=new_id("complaint"),
        submitter_account_id=account_id,
        submitter_key=key,
        target_kind=body.target_kind,
        target=body.target,
        sender_name=body.sender_name,
        reply_email=body.reply_email,
        subject=body.subject,
        message=body.message,
        created_at=now,
    )
    db.add(row)
    await db.flush()
    return ComplaintCreateResponse(
        schema_version=1,
        complaint_id=row.id,  # type: ignore[arg-type]
        accepted=True,
        created_at=format_timestamp(now),
    )


async def _lock_rate_limit(db: AsyncSession, scope: str) -> None:
    lock_id = int.from_bytes(blake2b(scope.encode(), digest_size=8).digest(), signed=True)
    await db.execute(select(func.pg_advisory_xact_lock(lock_id)))


async def _enforce_limit(
    db: AsyncSession,
    *clauses: ColumnElement[bool],
    since: datetime,
    maximum: int,
) -> None:
    count = await db.scalar(
        select(func.count())
        .select_from(ComplaintIntake)
        .where(*clauses, ComplaintIntake.created_at >= since)
    )
    if count is not None and int(count) >= maximum:
        raise ApiError(ErrorCategory.RATE_LIMITED, "complaint rate limit exceeded")
