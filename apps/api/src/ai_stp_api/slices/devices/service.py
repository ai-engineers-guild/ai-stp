"""Device registration, list and revoke (SPEC-002 REQ-204/205/207/214/215)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext, revoke_sessions_for_device
from ai_stp_api.settings import AuthSettings
from ai_stp_api.slices.devices.challenge import issue_challenge, message_to_sign, verify_challenge
from ai_stp_api.slices.devices.crypto import normalize_public_key, verify_ed25519
from ai_stp_api.slices.devices.domain import DeviceState, DeviceSummary
from ai_stp_contracts.identity import DeviceSummary as SyncedDeviceSummary
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import AccountSession, Device, SyncEntityHead, SyncRevision


def _to_summary(device: Device, *, display_name: str | None = None) -> DeviceSummary:
    # Passport summary sync is out of #80 scope; lifecycle fields are always set
    # and the remaining closed-list fields are null until a later sync path fills
    # them. They are still present so the DTO never invents full-passport keys.
    return DeviceSummary(
        id=device.id,
        state=device.state,
        last_seen_at=device.last_seen_at,
        display_name=display_name,
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

    # Reject attach of this public key to another account (REQ-204 acceptance).
    foreign = await db.execute(
        select(Device).where(
            Device.public_key == pk,
            Device.account_id != ctx.account_id,
        )
    )
    if foreign.scalar_one_or_none() is not None:
        raise ApiError(ErrorCategory.PERMISSION, "device key belongs to another account")

    existing = await db.execute(
        select(Device).where(
            Device.account_id == ctx.account_id,
            Device.public_key == pk,
        )
    )
    device = existing.scalar_one_or_none()
    created = False
    now = datetime.now(UTC)
    if device is None:
        device = Device(
            id=new_id("device"),
            account_id=ctx.account_id,
            public_key=pk,
            state=DeviceState.ACTIVE.value,
            last_seen_at=now,
        )
        db.add(device)
        created = True
    else:
        if device.state == DeviceState.REVOKED.value:
            # Resuming cloud access requires a new login and a new key (REQ-207).
            raise ApiError(
                ErrorCategory.PERMISSION,
                "device is revoked; register a new device key",
            )
        device.last_seen_at = now
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
) -> list[DeviceSummary]:
    """List device summaries for the owner or an audited admin read."""
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

    result = await db.execute(
        select(Device).where(Device.account_id == target).order_by(Device.created_at.asc())
    )
    return [_to_summary(row) for row in result.scalars().all()]


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
    if device.account_id != ctx.account_id and not ctx.is_admin:
        # Do not leak existence to outsiders (same body as missing).
        raise ApiError(ErrorCategory.PERMISSION, "permission denied")
    if device.account_id != ctx.account_id and ctx.is_admin:
        # Admin revoke still requires ownership policy; MVP: owners only.
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
