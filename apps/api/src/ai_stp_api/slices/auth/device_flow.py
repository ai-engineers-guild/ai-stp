"""RFC 8628 device-code authorization brokered by the platform (SPEC-002)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.geoip import approximate_location
from ai_stp_api.session import issue_session
from ai_stp_api.settings import AuthSettings
from ai_stp_api.slices.devices.crypto import normalize_public_key
from ai_stp_api.slices.devices.domain import DeviceState
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Device, DeviceAuthorization

# Crockford base32 without I,L,O,U — user-typed codes.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DEFAULT_INTERVAL = 5
_DEFAULT_EXPIRES = 600
# Access sessions report their real lifetime on the wire; the contract caps
# `expires_in` at one day, so the access half of a device pair never outlives
# what the client was told. The refresh half keeps the full session TTL.
ACCESS_TTL_CAP = 86400


def _mint_device_code() -> str:
    return secrets.token_urlsafe(40)[:48]


def _mint_user_code() -> str:
    chars = [_CROCKFORD[secrets.randbelow(len(_CROCKFORD))] for _ in range(8)]
    # Store uppercase; approve path normalizes input to upper.
    return f"{''.join(chars[:4])}-{''.join(chars[4:])}".upper()


async def start_device_authorization(
    db: AsyncSession,
    *,
    provider: str,
    auth: AuthSettings,
    idempotency_key: str | None = None,
) -> DeviceAuthorization:
    """Create a pending device authorization for CLI polling.

    `idempotency_key` replays the original row so a lost answer cannot mint a
    second pending authorization for the same user intent.
    """
    if provider not in {"google", "github"}:
        raise ApiError(ErrorCategory.VALIDATION, "unsupported oauth provider")
    if not auth.provider_enabled(provider):
        raise ApiError(ErrorCategory.DEPENDENCY, "oauth provider is not configured")

    if idempotency_key is not None:
        held = (
            await db.execute(
                select(DeviceAuthorization).where(
                    DeviceAuthorization.idempotency_key == idempotency_key
                )
            )
        ).scalar_one_or_none()
        if held is not None:
            if held.provider != provider:
                raise ApiError(
                    ErrorCategory.CONFLICT,
                    "idempotency key was reused with different content",
                )
            return held

    now = datetime.now(UTC)
    # A clash can land on either unique key: `idempotency_key` means the same
    # intent committed concurrently (replay its row); `user_code` means the
    # random code collided (mint a fresh one and retry once). `DO NOTHING`
    # skips either conflict without raising, so the session stays usable —
    # a failed flush inside `begin_nested` would mark it rollback-required.
    for _attempt in range(2):
        device_code = _mint_device_code()
        user_code = _mint_user_code()
        inserted = cast(
            CursorResult[Any],
            await db.execute(
                pg_insert(DeviceAuthorization)
                .values(
                    device_code=device_code,
                    user_code=user_code,
                    provider=provider,
                    status="pending",
                    account_id=None,
                    interval_seconds=_DEFAULT_INTERVAL,
                    expires_at=now + timedelta(seconds=_DEFAULT_EXPIRES),
                    last_poll_at=None,
                    idempotency_key=idempotency_key,
                )
                .on_conflict_do_nothing()
            ),
        )
        if inserted.rowcount == 1:
            return (
                await db.execute(
                    select(DeviceAuthorization).where(
                        DeviceAuthorization.device_code == device_code
                    )
                )
            ).scalar_one()
        if idempotency_key is not None:
            held = (
                await db.execute(
                    select(DeviceAuthorization).where(
                        DeviceAuthorization.idempotency_key == idempotency_key
                    )
                )
            ).scalar_one_or_none()
            if held is not None:
                if held.provider != provider:
                    raise ApiError(
                        ErrorCategory.CONFLICT,
                        "idempotency key was reused with different content",
                    )
                return held
        # Otherwise the random `user_code` clashed: loop mints a fresh pair.
    raise ApiError(ErrorCategory.INTERNAL, "could not allocate a unique device user code")


def verification_uris(auth: AuthSettings, user_code: str) -> tuple[str, str]:
    """Build browser verification URLs on the public web origin."""
    base = auth.public_base_url.rstrip("/")
    plain = f"{base}/en/device-login"
    complete = f"{base}/en/device-login?user_code={user_code}"
    return plain, complete


async def approve_device_authorization(
    db: AsyncSession,
    *,
    user_code: str,
    account_id: str,
) -> DeviceAuthorization:
    """Human-approved binding of a pending code to the current account.

    The claim is a conditional UPDATE for the same reason the consume path is:
    the reads cannot serialize two approvers who both see `pending` — the loser
    matches zero rows and reads the winner's verdict instead of re-binding the
    grant to a different account.
    """
    normalized = user_code.strip().upper()
    now = datetime.now(UTC)
    claimed = await db.execute(
        update(DeviceAuthorization)
        .where(
            DeviceAuthorization.user_code == normalized,
            DeviceAuthorization.status == "pending",
            DeviceAuthorization.expires_at > now,
        )
        .values(status="approved", account_id=account_id)
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(
        select(DeviceAuthorization).where(DeviceAuthorization.user_code == normalized)
    )
    row = result.scalar_one_or_none()
    if getattr(claimed, "rowcount", 0) == 1 and row is not None:
        return row
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "unknown user code")
    if row.expires_at <= now or row.status in {"consumed", "declined"}:
        raise ApiError(ErrorCategory.VALIDATION, "authorization expired")
    if row.status == "approved" and row.account_id == account_id:
        return row
    raise ApiError(ErrorCategory.CONFLICT, "authorization already resolved")


async def exchange_device_code(
    db: AsyncSession,
    *,
    auth: AuthSettings,
    device_code: str,
    device_id: str,
    public_key: str,
    display_name: str,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> dict[str, object]:
    """Poll endpoint: pending/expired/declined as typed errors; success binds device."""
    row = await db.get(DeviceAuthorization, device_code)
    now = datetime.now(UTC)
    if row is None:
        raise ApiError(ErrorCategory.VALIDATION, "unknown device code")

    # Rate limit between polls. The timestamp has to survive the refusal below,
    # so it is committed before raising — a bare flush rolls back with the
    # exception and the throttle never engages.
    if row.last_poll_at is not None:
        elapsed = (now - row.last_poll_at).total_seconds()
        if elapsed < row.interval_seconds:
            raise ApiError(ErrorCategory.RATE_LIMITED, "slow down")
    row.last_poll_at = now
    await db.commit()

    # The grant dies with `expires_at` in every status: an approved code that
    # was never exchanged is not a standing credential-issuance capability.
    if row.expires_at <= now or row.status == "consumed":
        raise ApiError(ErrorCategory.AUTHORIZATION_EXPIRED, "authorization expired")
    if row.status == "pending":
        raise ApiError(ErrorCategory.AUTHORIZATION_PENDING, "authorization pending")
    if row.status == "declined":
        raise ApiError(ErrorCategory.AUTHORIZATION_DECLINED, "authorization declined")
    if row.status != "approved" or not row.account_id:
        raise ApiError(ErrorCategory.AUTHORIZATION_PENDING, "authorization pending")

    if not device_id.startswith("device_"):
        raise ApiError(ErrorCategory.VALIDATION, "invalid device id")

    # Single-use consume, claimed atomically. The reads above cannot serialize
    # two pollers that both see `approved` — only this conditional UPDATE can.
    # The loser matches zero rows, reloads, and reports the winner's verdict
    # instead of minting a second credential pair for the same grant. The claim
    # shares the request transaction, so a failure below still rolls it back.
    claimed = await db.execute(
        update(DeviceAuthorization)
        .where(
            DeviceAuthorization.device_code == row.device_code,
            DeviceAuthorization.status == "approved",
            DeviceAuthorization.expires_at > now,
        )
        .values(status="consumed")
        .execution_options(synchronize_session=False)
    )
    if getattr(claimed, "rowcount", 0) != 1:
        await db.refresh(row)
        # The refresh can move the row past `approved`; read it fresh so the
        # checks below see the winner's verdict, not the stale local value.
        current = str(row.status)
        if row.expires_at <= now or current == "consumed":
            raise ApiError(ErrorCategory.AUTHORIZATION_EXPIRED, "authorization expired")
        if current == "declined":
            raise ApiError(ErrorCategory.AUTHORIZATION_DECLINED, "authorization declined")
        raise ApiError(ErrorCategory.AUTHORIZATION_PENDING, "authorization pending")
    row.status = "consumed"

    pk = normalize_public_key(public_key)
    # `public_key` is globally unique, so the lookup itself answers the
    # foreign-account question the old two-query dance approximated.
    device = (await db.execute(select(Device).where(Device.public_key == pk))).scalar_one_or_none()
    if device is None:
        # Prefer client-supplied device_id when free; otherwise mint.
        taken = await db.get(Device, device_id)
        new_device_id = device_id if taken is None else new_id("device")
        # `ON CONFLICT DO NOTHING` keeps the request transaction alive through
        # the race: two exchanges on the same key insert once, the loser skips
        # and re-reads the committed winner. (A failed flush inside
        # `begin_nested` marks the whole session rollback-required in
        # SQLAlchemy, so savepoint-replay cannot survive here.)
        await db.execute(
            pg_insert(Device)
            .values(
                id=new_device_id,
                account_id=row.account_id,
                public_key=pk,
                device_type="cli",
                display_name=display_name or None,
                state=DeviceState.ACTIVE.value,
                last_seen_at=now,
            )
            .on_conflict_do_nothing(index_elements=[Device.public_key])
        )
        device = (await db.execute(select(Device).where(Device.public_key == pk))).scalar_one()
    if device.account_id != row.account_id:
        # `reason` survives the wire through the client's forwarded-details
        # allowlist; the recovery it names is `device reset`, which a generic
        # PERMISSION_DENIED must not suggest (#359).
        raise ApiError(
            ErrorCategory.PERMISSION,
            "device key belongs to another account",
            details={"reason": "device_key_foreign"},
        )
    if device.state == DeviceState.REVOKED.value:
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

    access_ttl = min(auth.session_ttl_seconds, ACCESS_TTL_CAP)
    issued = await issue_session(
        db,
        account_id=row.account_id,
        device_id=device.id,
        ttl_seconds=access_ttl,
    )
    refresh = await issue_session(
        db,
        account_id=row.account_id,
        device_id=device.id,
        ttl_seconds=auth.session_ttl_seconds,
        kind="refresh",
    )
    await db.flush()

    return {
        "schema_version": 1,
        "access_token": issued.raw_token,
        "refresh_token": refresh.raw_token,
        "token_type": "Bearer",
        "expires_in": access_ttl,
        "account_id": row.account_id,
        "device_id": device.id,
    }
