"""Transactional private revision sync application service (SPEC-025)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.sync.cursor import (
    SyncCursorError,
    decode_sync_cursor,
    encode_sync_cursor,
    sync_page_cursor,
)
from ai_stp_api.slices.sync.validation import (
    SyncValidationError,
    can_accept_head_transition,
    request_fingerprint,
    validate_event_document,
)
from ai_stp_contracts.http import PAGE_SIZE_MAX, PageInfo
from ai_stp_contracts.sync import (
    SyncConflictInfo,
    SyncEvent,
    SyncEventReceipt,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
    SyncStreamEvent,
)
from ai_stp_foundation.timestamps import format_timestamp, parse_timestamp
from ai_stp_platform.logging import get_logger
from ai_stp_platform.models import (
    Account,
    Device,
    SyncEntityHead,
    SyncOutbox,
    SyncRevision,
)
from ai_stp_platform.models import (
    SyncEventReceipt as SyncEventReceiptRow,
)

_log = get_logger("sync")


def _event_as_fingerprint_payload(event: SyncEvent) -> dict[str, object]:
    return event.model_dump(mode="json")


async def require_active_device(db: AsyncSession, ctx: AuthContext) -> str:
    """Return the session-bound active device id or raise typed errors."""
    if ctx.device_id is None:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "device-bound session required")
    device = await db.get(Device, ctx.device_id)
    if device is None or device.account_id != ctx.account_id:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "device-bound session required")
    if device.state != "active":
        raise ApiError(ErrorCategory.DEVICE_REVOKED, "device is revoked")
    return device.id


async def _load_receipt(
    db: AsyncSession, *, account_id: str, idempotency_key: str
) -> SyncEventReceiptRow | None:
    result = await db.execute(
        select(SyncEventReceiptRow).where(
            SyncEventReceiptRow.account_id == account_id,
            SyncEventReceiptRow.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def _lock_head(db: AsyncSession, *, account_id: str, entity_id: str) -> SyncEntityHead | None:
    result = await db.execute(
        select(SyncEntityHead)
        .where(
            SyncEntityHead.account_id == account_id,
            SyncEntityHead.entity_id == entity_id,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def _lock_account(db: AsyncSession, *, account_id: str) -> None:
    """Serialize an account's writes, including first-head and outbox allocation."""
    result = await db.execute(select(Account.id).where(Account.id == account_id).with_for_update())
    if result.scalar_one_or_none() is None:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "account is no longer available")


async def _revision_parents(db: AsyncSession, *, account_id: str, revision_id: str) -> list[str]:
    row = await db.get(SyncRevision, {"account_id": account_id, "revision_id": revision_id})
    if row is None:
        return []
    return list(row.parent_revision_ids)


async def _find_common_ancestor(
    db: AsyncSession,
    *,
    account_id: str,
    left: str,
    right: str,
) -> str | None:
    """Breadth walk of parent links; returns first shared ancestor if known."""
    if left == right:
        return left
    left_seen: set[str] = {left}
    right_seen: set[str] = {right}
    left_frontier = [left]
    right_frontier = [right]
    for _ in range(64):
        if not left_frontier and not right_frontier:
            break
        next_left: list[str] = []
        for node in left_frontier:
            for parent in await _revision_parents(db, account_id=account_id, revision_id=node):
                if parent in right_seen:
                    return parent
                if parent not in left_seen:
                    left_seen.add(parent)
                    next_left.append(parent)
        left_frontier = next_left
        next_right: list[str] = []
        for node in right_frontier:
            for parent in await _revision_parents(db, account_id=account_id, revision_id=node):
                if parent in left_seen:
                    return parent
                if parent not in right_seen:
                    right_seen.add(parent)
                    next_right.append(parent)
        right_frontier = next_right
    return None


async def _next_sequence(db: AsyncSession, *, account_id: str) -> int:
    # `_lock_account` is held by `_apply_one`, so MAX+1 is account-serial and safe.
    result = await db.execute(
        select(func.coalesce(func.max(SyncOutbox.sequence), 0)).where(
            SyncOutbox.account_id == account_id
        )
    )
    current = result.scalar_one()
    return int(current) + 1


def _revision_from_event(
    *,
    account_id: str,
    event: SyncEvent,
    parents: list[str],
    created_at: datetime,
) -> SyncRevision:
    return SyncRevision(
        account_id=account_id,
        revision_id=event.revision_id,
        entity_id=event.entity_id,
        entity_kind=event.entity_kind,
        parent_revision_ids=parents,
        operation=event.operation,
        content_digest=event.content_digest,
        payload=dict(event.payload),
        device_id=event.device_id,
        actor_id=event.actor_id,
        event_id=event.event_id,
        schema_version=1,
        created_at=created_at,
    )


async def _store_receipt(
    db: AsyncSession,
    *,
    account_id: str,
    event: SyncEvent,
    fingerprint: str,
    receipt: SyncEventReceipt,
) -> SyncEventReceipt:
    body = receipt.model_dump(mode="json")
    row = SyncEventReceiptRow(
        account_id=account_id,
        idempotency_key=event.idempotency_key,
        request_fingerprint=fingerprint,
        event_id=event.event_id,
        device_id=event.device_id,
        state=receipt.state,
        revision_id=receipt.revision_id,
        server_head_revision_id=receipt.server_head_revision_id,
        response_body=body,
    )
    db.add(row)
    await db.flush()
    return receipt


def _receipt_from_row(row: SyncEventReceiptRow) -> SyncEventReceipt:
    return SyncEventReceipt.model_validate(row.response_body)


async def _apply_one(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    device_id: str,
    event: SyncEvent,
    secret: str,
) -> SyncEventReceipt:
    fingerprint = request_fingerprint(_event_as_fingerprint_payload(event))
    if event.device_id != device_id:
        raise ApiError(ErrorCategory.VALIDATION, "event device_id must match session device")
    if event.actor_id != ctx.account_id:
        raise ApiError(ErrorCategory.VALIDATION, "event actor_id must match account")

    await _lock_account(db, account_id=ctx.account_id)
    existing = await _load_receipt(
        db, account_id=ctx.account_id, idempotency_key=event.idempotency_key
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise ApiError(
                ErrorCategory.CONFLICT,
                "idempotency key reused with a different event",
            )
        return _receipt_from_row(existing)

    try:
        validate_event_document(
            entity_id=event.entity_id,
            entity_kind=event.entity_kind,
            revision_id_value=event.revision_id,
            parent_revision_ids=list(event.parent_revision_ids),
            operation=event.operation,
            content_digest=event.content_digest,
            payload=dict(event.payload),
            device_id=event.device_id,
            actor_id=event.actor_id,
            created_at=event.created_at,
        )
    except SyncValidationError as exc:
        receipt = SyncEventReceipt(
            event_id=event.event_id,
            state="rejected",
            revision_id=None,
            server_head_revision_id=None,
            cursor=None,
            conflict=None,
            error_code="AI_STP_VALIDATION_ERROR",
        )
        stored = await _store_receipt(
            db,
            account_id=ctx.account_id,
            event=event,
            fingerprint=fingerprint,
            receipt=receipt,
        )
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            action="sync.event_rejected",
            target_table="sync_event_receipt",
            target_id=event.event_id,
            payload={
                "state": "rejected",
                "entity_id": event.entity_id,
                "entity_kind": event.entity_kind,
                "reason": str(exc),
            },
        )
        await db.commit()
        return stored

    # Already-accepted identical revision (same content id) is superseded if
    # head already points here, or accepted-idempotent if exact row exists.
    existing_revision = await db.get(
        SyncRevision,
        {"account_id": ctx.account_id, "revision_id": event.revision_id},
    )
    head = await _lock_head(db, account_id=ctx.account_id, entity_id=event.entity_id)

    if existing_revision is not None:
        head_id = head.revision_id if head is not None else None
        cursor = None
        if head_id is not None:
            # Point cursor at the latest outbox for this account if any.
            seq_result = await db.execute(
                select(func.max(SyncOutbox.sequence)).where(SyncOutbox.account_id == ctx.account_id)
            )
            max_seq = seq_result.scalar_one()
            if max_seq:
                cursor = encode_sync_cursor(
                    secret=secret, account_id=ctx.account_id, sequence=int(max_seq)
                )
        receipt = SyncEventReceipt(
            event_id=event.event_id,
            state="superseded",
            revision_id=event.revision_id,
            server_head_revision_id=head_id,
            cursor=cursor,
            conflict=None,
            error_code=None,
        )
        stored = await _store_receipt(
            db,
            account_id=ctx.account_id,
            event=event,
            fingerprint=fingerprint,
            receipt=receipt,
        )
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            action="sync.event_superseded",
            target_table="sync_revision",
            target_id=event.revision_id,
            payload={
                "state": "superseded",
                "entity_id": event.entity_id,
                "entity_kind": event.entity_kind,
            },
        )
        await db.commit()
        return stored

    current_head = head.revision_id if head is not None else None
    parents = list(event.parent_revision_ids)

    # A conflict candidate is retained for a later explicit client merge, so all
    # of its ancestors must already be known before it can enter the ledger.
    for parent in parents:
        parent_row = await db.get(
            SyncRevision, {"account_id": ctx.account_id, "revision_id": parent}
        )
        if parent_row is None:
            receipt = SyncEventReceipt(
                event_id=event.event_id,
                state="rejected",
                revision_id=None,
                server_head_revision_id=current_head,
                cursor=None,
                conflict=None,
                error_code="AI_STP_VALIDATION_ERROR",
            )
            stored = await _store_receipt(
                db,
                account_id=ctx.account_id,
                event=event,
                fingerprint=fingerprint,
                receipt=receipt,
            )
            await emit_audit(
                db,
                actor_account_id=ctx.account_id,
                action="sync.event_rejected",
                target_table="sync_event_receipt",
                target_id=event.event_id,
                payload={
                    "state": "rejected",
                    "entity_id": event.entity_id,
                    "reason": "unknown_parent",
                },
            )
            await db.commit()
            return stored

    if not can_accept_head_transition(
        current_head=current_head,
        expected_head=event.expected_head_revision_id,
        parent_revision_ids=parents,
    ):
        client_head = event.expected_head_revision_id or (
            parents[0] if parents else event.revision_id
        )
        ancestor = None
        if current_head is not None and event.expected_head_revision_id is not None:
            ancestor = await _find_common_ancestor(
                db,
                account_id=ctx.account_id,
                left=current_head,
                right=event.expected_head_revision_id,
            )
        if current_head is None:
            conflict = SyncConflictInfo(
                server_head_revision_id=event.expected_head_revision_id or event.revision_id,
                client_head_revision_id=client_head,
                common_ancestor_revision_id=None,
                affected_fields=sorted(event.payload.keys()) if event.payload else [],
            )
        else:
            conflict = SyncConflictInfo(
                server_head_revision_id=current_head,
                client_head_revision_id=client_head,
                common_ancestor_revision_id=ancestor,
                affected_fields=sorted(event.payload.keys()) if event.payload else [],
            )
        db.add(
            _revision_from_event(
                account_id=ctx.account_id,
                event=event,
                parents=parents,
                created_at=parse_timestamp(event.created_at),
            )
        )
        receipt = SyncEventReceipt(
            event_id=event.event_id,
            state="conflict",
            revision_id=event.revision_id,
            server_head_revision_id=current_head,
            cursor=None,
            conflict=conflict,
            error_code=None,
        )
        stored = await _store_receipt(
            db,
            account_id=ctx.account_id,
            event=event,
            fingerprint=fingerprint,
            receipt=receipt,
        )
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            action="sync.event_conflict",
            target_table="sync_revision",
            target_id=event.revision_id,
            payload={
                "state": "conflict",
                "entity_id": event.entity_id,
                "entity_kind": event.entity_kind,
                "server_head_revision_id": current_head,
            },
        )
        await db.commit()
        return stored

    created_at = parse_timestamp(event.created_at)
    sequence = await _next_sequence(db, account_id=ctx.account_id)

    revision = _revision_from_event(
        account_id=ctx.account_id,
        event=event,
        parents=parents,
        created_at=created_at,
    )
    db.add(revision)

    if head is None:
        head = SyncEntityHead(
            account_id=ctx.account_id,
            entity_id=event.entity_id,
            revision_id=event.revision_id,
        )
        db.add(head)
    else:
        head.revision_id = event.revision_id
        head.updated_at = datetime.now(UTC)

    outbox = SyncOutbox(
        account_id=ctx.account_id,
        sequence=sequence,
        event_id=event.event_id,
        entity_id=event.entity_id,
        entity_kind=event.entity_kind,
        revision_id=event.revision_id,
        parent_revision_ids=parents,
        device_id=event.device_id,
        actor_id=event.actor_id,
        operation=event.operation,
        content_digest=event.content_digest,
        payload=dict(event.payload),
        created_at=created_at,
    )
    db.add(outbox)

    cursor = encode_sync_cursor(secret=secret, account_id=ctx.account_id, sequence=sequence)
    receipt = SyncEventReceipt(
        event_id=event.event_id,
        state="accepted",
        revision_id=event.revision_id,
        server_head_revision_id=event.revision_id,
        cursor=cursor,
        conflict=None,
        error_code=None,
    )
    stored = await _store_receipt(
        db,
        account_id=ctx.account_id,
        event=event,
        fingerprint=fingerprint,
        receipt=receipt,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="sync.event_accepted",
        target_table="sync_revision",
        target_id=event.revision_id,
        payload={
            "state": "accepted",
            "entity_id": event.entity_id,
            "entity_kind": event.entity_kind,
            "operation": event.operation,
            "sequence": sequence,
        },
    )
    # Commit per event so a later failure does not undo prior accepts (ADR-0045).
    await db.commit()
    _log.info(
        "sync_event_accepted",
        **safe_log_fields(
            account_id=ctx.account_id,
            entity_id=event.entity_id,
            entity_kind=event.entity_kind,
            state="accepted",
            sequence=sequence,
        ),
    )
    return stored


async def push_events(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    body: SyncPushRequest,
    secret: str,
) -> SyncPushResponse:
    """Apply push events in order with durable per-event receipts."""
    device_id = await require_active_device(db, ctx)
    receipts: list[SyncEventReceipt] = []
    for event in body.events:
        receipts.append(
            await _apply_one(
                db,
                ctx=ctx,
                device_id=device_id,
                event=event,
                secret=secret,
            )
        )
    return SyncPushResponse(receipts=receipts)


async def pull_events(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    secret: str,
    cursor: str | None,
    page_size: int,
) -> SyncPullResponse:
    """Read the caller's accepted outbox from a signed account-bound cursor."""
    await require_active_device(db, ctx)
    size = min(max(page_size, 1), PAGE_SIZE_MAX)
    after = 0
    if cursor is not None:
        try:
            position = decode_sync_cursor(secret=secret, token=cursor, account_id=ctx.account_id)
        except SyncCursorError as exc:
            raise ApiError(ErrorCategory.VALIDATION, "invalid sync cursor") from exc
        after = position.sequence

    result = await db.execute(
        select(SyncOutbox)
        .where(
            SyncOutbox.account_id == ctx.account_id,
            SyncOutbox.sequence > after,
        )
        .order_by(SyncOutbox.sequence.asc())
        .limit(size)
    )
    page_rows = list(result.scalars().all())
    items = [
        SyncStreamEvent(
            event_id=row.event_id,
            entity_id=row.entity_id,
            entity_kind=row.entity_kind,  # type: ignore[arg-type]
            revision_id=row.revision_id,
            parent_revision_ids=list(row.parent_revision_ids),
            device_id=row.device_id,
            actor_id=row.actor_id,
            operation=row.operation,  # type: ignore[arg-type]
            content_digest=row.content_digest,
            created_at=format_timestamp(
                row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
            ),
            payload=dict(row.payload),
            sequence=int(row.sequence),
        )
        for row in page_rows
    ]
    last_delivered = int(page_rows[-1].sequence) if page_rows else None
    next_cursor = sync_page_cursor(
        last_delivered_sequence=last_delivered,
        incoming_cursor=cursor,
        secret=secret,
        account_id=ctx.account_id,
    )

    return SyncPullResponse(
        items=items,
        page=PageInfo(next_cursor=next_cursor, page_size=size),
    )


def safe_log_fields(**fields: Any) -> dict[str, Any]:
    """Return only safe observability fields (no payload/cursor/token)."""
    allowed = {
        "account_id",
        "entity_id",
        "entity_kind",
        "state",
        "sequence",
        "event_id",
        "device_id",
        "operation",
    }
    return {key: value for key, value in fields.items() if key in allowed}
