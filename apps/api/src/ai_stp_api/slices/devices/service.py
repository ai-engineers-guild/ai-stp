"""Device registration, list and revoke (SPEC-002 REQ-204/205/207/214/215)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.geoip import approximate_location
from ai_stp_api.session import AuthContext, revoke_sessions_for_device
from ai_stp_api.settings import AuthSettings
from ai_stp_api.slices.devices.challenge import issue_challenge, message_to_sign, verify_challenge
from ai_stp_api.slices.devices.crypto import normalize_public_key, verify_ed25519
from ai_stp_api.slices.devices.domain import DeviceState, DeviceSummary
from ai_stp_contracts.http import PAGE_SIZE_MAX
from ai_stp_contracts.identity import DeviceSummary as SyncedDeviceSummary
from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog_cursor import (
    CursorError,
    CursorKey,
    decode_cursor,
    encode_cursor,
    filter_signature,
)
from ai_stp_platform.models import AccountSession, Device, SyncEntityHead, SyncRevision


def _to_summary(device: Device, *, display_name: str | None = None) -> DeviceSummary:
    # Passport summary sync is out of #80 scope; lifecycle fields are always set
    # and the remaining closed-list fields are null until a later sync path fills
    # them. They are still present so the DTO never invents full-passport keys.
    return DeviceSummary(
        id=device.id,
        state=device.state,
        last_seen_at=device.last_seen_at,
        display_name=display_name or device.display_name,
        os=None,
        architecture=None,
        harnesses=(),
        toolset_profile_version=None,
        summary_updated_at=None,
    )


async def create_challenge(auth: AuthSettings, public_key: str) -> tuple[str, int]:
    """Issue a stateless challenge bound to the normalized public key."""
    pk = normalize_public_key(public_key)
    return issue_challenge(
        secret_key=auth.secret_key,
        public_key=pk,
        ttl_seconds=auth.challenge_ttl_seconds,
    )


async def register_device(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    auth: AuthSettings,
    public_key: str,
    nonce: str,
    signature: str,
    display_name: str | None,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> tuple[DeviceSummary, bool]:
    """Verify challenge + Ed25519 and upsert by (account_id, public_key)."""
    pk = normalize_public_key(public_key)
    verify_challenge(
        secret_key=auth.secret_key,
        nonce=nonce,
        public_key=pk,
        max_age_seconds=auth.challenge_ttl_seconds,
    )
    verify_ed25519(public_key=pk, message=message_to_sign(nonce), signature=signature)

    # `public_key` is globally unique: one lookup answers both the
    # foreign-account rejection (REQ-204 acceptance) and the upsert question.
    device = (await db.execute(select(Device).where(Device.public_key == pk))).scalar_one_or_none()
    created = False
    now = datetime.now(UTC)
    if device is None:
        # `ON CONFLICT DO NOTHING` never raises on the race: a concurrent
        # attach of the same key commits first, this insert skips, and the
        # re-select below returns the committed winner. (A failed flush inside
        # `begin_nested` marks the whole session rollback-required in
        # SQLAlchemy, so the savepoint-replay idiom cannot survive here.)
        inserted = cast(
            CursorResult[Any],
            await db.execute(
                pg_insert(Device)
                .values(
                    id=new_id("device"),
                    account_id=ctx.account_id,
                    public_key=pk,
                    device_type="cli",
                    state=DeviceState.ACTIVE.value,
                    display_name=display_name,
                    last_seen_at=now,
                )
                .on_conflict_do_nothing(index_elements=[Device.public_key])
            ),
        )
        created = inserted.rowcount == 1
        device = (await db.execute(select(Device).where(Device.public_key == pk))).scalar_one()
    if device.account_id != ctx.account_id:
        # `reason` reaches the CLI through its forwarded-details allowlist and
        # names the rebind path; an unqualified denial must not (#359).
        raise ApiError(
            ErrorCategory.PERMISSION,
            "device key belongs to another account",
            details={"reason": "device_key_foreign"},
        )
    if device.state == DeviceState.REVOKED.value:
        # Resuming cloud access requires a new login and a new key (REQ-207).
        raise ApiError(
            ErrorCategory.PERMISSION,
            "device is revoked; register a new device key",
        )
    device.last_seen_at = now
    if display_name:
        device.display_name = display_name
    device.user_agent = user_agent
    device.approximate_location = approximate_location(client_ip, auth.geoip_city_db_path)
    await db.flush()

    # Bind the current opaque session to this device so revoke cascades.
    session_row = await db.get(AccountSession, ctx.session_id)
    if session_row is not None and session_row.device_id is None:
        session_row.device_id = device.id
        await db.flush()

    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="device.registered" if created else "device.reregistered",
        target_table="device",
        target_id=device.id,
        payload={"created": created},
    )
    return _to_summary(device, display_name=display_name), created


async def list_devices(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    subject_account_id: str | None,
    admin_reason: str | None,
    page_size: int = PAGE_SIZE_MAX,
    cursor: str | None = None,
    cursor_secret: str | None = None,
) -> tuple[list[Device], str | None]:
    """List device rows for the owner or an audited admin read.

    Keyset-paginated on the ULID primary key ascending: ids are immutable and
    lexicographically time-ordered, so the cursor position survives both a
    `last_seen_at` refresh and the millisecond precision of wire timestamps.
    `page.next_cursor` stays the only signal that more rows exist — a
    truncated page without a continuation would silently hide a
    hundred-and-first device.
    """
    target = subject_account_id or ctx.account_id
    if target != ctx.account_id:
        if not ctx.is_admin:
            raise ApiError(ErrorCategory.PERMISSION, "permission denied")
        if not admin_reason or not admin_reason.strip():
            raise ApiError(ErrorCategory.VALIDATION, "admin reason required")
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            action="device.admin_list",
            target_table="device",
            target_id=target,
            reason=admin_reason.strip(),
            payload={"subject_account_id": target},
        )

    # The signature binds the listed account: a cursor minted for account A
    # must not page account B's devices.
    filter_sig = filter_signature(
        object_kind=f"devices:{target}",
        q=None,
        tags=[],
        harness_id=None,
        component_type=None,
        include_experimental=False,
    )
    statement = select(Device).where(Device.account_id == target).order_by(Device.id.asc())
    if cursor is not None:
        if cursor_secret is None:
            raise ApiError(ErrorCategory.DEPENDENCY, "cursor signing is not configured")
        try:
            key = decode_cursor(secret=cursor_secret, token=cursor, filter_sig=filter_sig)
        except CursorError as error:
            raise ApiError(ErrorCategory.VALIDATION, "invalid cursor") from error
        statement = statement.where(Device.id > key.stable_id)
    rows = list((await db.execute(statement.limit(page_size + 1))).scalars().all())
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    next_cursor: str | None = None
    if has_more and cursor_secret is not None:
        last = rows[-1]
        created = last.created_at if last.created_at.tzinfo else last.created_at.replace(tzinfo=UTC)
        next_cursor = encode_cursor(
            secret=cursor_secret,
            filter_sig=filter_sig,
            key=CursorKey(published_at=created, stable_id=last.id),
        )
    return rows, next_cursor


async def stored_summaries(
    db: AsyncSession,
    *,
    account_id: str,
    device_ids: list[str],
) -> dict[str, dict[str, object]]:
    """The `device_summary` each device last published through sync, if it did.

    The head revision is what counts: a tombstoned summary is retracted and
    answers nothing. What is served is the validated closed document projected
    to its declared fields — the payload reached the ledger through intake
    validation, and read-side projection keeps even that vetted payload inside
    the field list the contract permits.
    """
    if not device_ids:
        return {}
    heads = await db.execute(
        select(SyncEntityHead.entity_id, SyncEntityHead.revision_id).where(
            SyncEntityHead.account_id == account_id,
            SyncEntityHead.entity_id.in_(device_ids),
        )
    )
    by_revision = {row.revision_id: row.entity_id for row in heads.all()}
    if not by_revision:
        return {}
    rows = await db.execute(
        select(SyncRevision.revision_id, SyncRevision.payload).where(
            SyncRevision.account_id == account_id,
            SyncRevision.revision_id.in_(list(by_revision)),
            SyncRevision.entity_kind == "device_summary",
            SyncRevision.operation == "upsert",
        )
    )
    declared = set(SyncedDeviceSummary.model_fields)
    summaries: dict[str, dict[str, object]] = {}
    for revision_id_value, payload in rows.all():
        try:
            summary = SyncedDeviceSummary.model_validate(payload)
        except ValueError:
            continue
        rendered = summary.model_dump(mode="json")
        summaries[by_revision[revision_id_value]] = {
            key: rendered[key] for key in declared if key in rendered
        }
    return summaries


async def revoke_device(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    device_id: str,
) -> DeviceSummary:
    """Revoke an owned device and cascade session revocation (REQ-205/207)."""
    device = await db.get(Device, device_id)
    if device is None:
        raise ApiError(ErrorCategory.PERMISSION, "permission denied")
    # Owners only — an admin cannot revoke another account's device either
    # (MVP policy). The same denial for missing and foreign leaks nothing.
    if device.account_id != ctx.account_id:
        raise ApiError(ErrorCategory.PERMISSION, "permission denied")

    if device.state != DeviceState.REVOKED.value:
        device.state = DeviceState.REVOKED.value
        await revoke_sessions_for_device(db, device.id)
        await db.flush()
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            action="device.revoked",
            target_table="device",
            target_id=device.id,
            payload={},
        )
    return _to_summary(device)
