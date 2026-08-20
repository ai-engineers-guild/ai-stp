"""RFC 8628 device-code authorization brokered by the platform (SPEC-002)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError, ErrorCategory
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
) -> DeviceAuthorization:
    """Create a pending device authorization for CLI polling."""
    if provider not in {"google", "github"}:
        raise ApiError(ErrorCategory.VALIDATION, "unsupported oauth provider")
    if not auth.provider_enabled(provider):
        raise ApiError(ErrorCategory.DEPENDENCY, "oauth provider is not configured")

    now = datetime.now(UTC)
    row = DeviceAuthorization(
        device_code=_mint_device_code(),
        user_code=_mint_user_code(),
        provider=provider,
        status="pending",
        account_id=None,
        interval_seconds=_DEFAULT_INTERVAL,
        expires_at=now + timedelta(seconds=_DEFAULT_EXPIRES),
        last_poll_at=None,
    )
    # Rare user_code collision: retry once.
    existing = await db.get(DeviceAuthorization, row.device_code)
    del existing
    clash = await db.execute(
        select(DeviceAuthorization).where(DeviceAuthorization.user_code == row.user_code)
    )
    if clash.scalar_one_or_none() is not None:
        row.user_code = _mint_user_code()
    db.add(row)
    await db.flush()
    return row


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
    """Human-approved binding of a pending code to the current account."""
    normalized = user_code.strip().upper()
    result = await db.execute(
        select(DeviceAuthorization).where(DeviceAuthorization.user_code == normalized)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "unknown user code")
    now = datetime.now(UTC)
    if row.expires_at <= now or row.status in {"consumed", "declined"}:
        raise ApiError(ErrorCategory.VALIDATION, "authorization expired")
    if row.status == "approved" and row.account_id == account_id:
        return row
    if row.status != "pending":
        raise ApiError(ErrorCategory.CONFLICT, "authorization already resolved")
    row.status = "approved"
    row.account_id = account_id
    await db.flush()
    return row


async def exchange_device_code(
    db: AsyncSession,
    *,
    auth: AuthSettings,
    device_code: str,
    device_id: str,
    public_key: str,
    display_name: str,
) -> dict[str, object]:
    """Poll endpoint: pending/expired/declined as typed errors; success binds device."""
    row = await db.get(DeviceAuthorization, device_code)
    now = datetime.now(UTC)
    if row is None:
        raise ApiError(ErrorCategory.VALIDATION, "unknown device code")

    # Rate limit between polls.
    if row.last_poll_at is not None:
        elapsed = (now - row.last_poll_at).total_seconds()
        if elapsed < row.interval_seconds:
            raise ApiError(ErrorCategory.RATE_LIMITED, "slow down")
    row.last_poll_at = now
    await db.flush()

    if row.expires_at <= now and row.status == "pending":
        row.status = "declined"
        await db.flush()
        raise ApiError(ErrorCategory.AUTHORIZATION_EXPIRED, "authorization expired")

    if row.status == "pending":
        raise ApiError(ErrorCategory.AUTHORIZATION_PENDING, "authorization pending")
    if row.status == "declined":
        raise ApiError(ErrorCategory.AUTHORIZATION_DECLINED, "authorization declined")
    if row.status == "consumed":
        raise ApiError(ErrorCategory.AUTHORIZATION_EXPIRED, "authorization expired")
    if row.status != "approved" or not row.account_id:
        raise ApiError(ErrorCategory.AUTHORIZATION_PENDING, "authorization pending")

    if not device_id.startswith("device_"):
        raise ApiError(ErrorCategory.VALIDATION, "invalid device id")

    pk = normalize_public_key(public_key)
    foreign = await db.execute(
        select(Device).where(Device.public_key == pk, Device.account_id != row.account_id)
    )
    if foreign.scalar_one_or_none() is not None:
        raise ApiError(ErrorCategory.PERMISSION, "device key belongs to another account")

    existing = await db.execute(
        select(Device).where(Device.account_id == row.account_id, Device.public_key == pk)
    )
    device = existing.scalar_one_or_none()
    if device is None:
        # Prefer client-supplied device_id when free; otherwise mint.
        taken = await db.get(Device, device_id)
        new_device_id = device_id if taken is None else new_id("device")
        device = Device(
            id=new_device_id,
            account_id=row.account_id,
            public_key=pk,
            state=DeviceState.ACTIVE.value,
            last_seen_at=now,
        )
        db.add(device)
    else:
        if device.state == DeviceState.REVOKED.value:
            raise ApiError(
                ErrorCategory.PERMISSION,
                "device is revoked; register a new device key",
            )
        device.last_seen_at = now
    await db.flush()

    issued = await issue_session(
        db,
        account_id=row.account_id,
        device_id=device.id,
        ttl_seconds=auth.session_ttl_seconds,
    )
    # Bind session to device already done via device_id on issue.

    row.status = "consumed"
    await db.flush()

    # Refresh token: second opaque session token for offline renewal (MVP: same TTL token).
    refresh = await issue_session(
        db,
        account_id=row.account_id,
        device_id=device.id,
        ttl_seconds=auth.session_ttl_seconds,
    )
    del display_name  # stored only when a summary path exists; not required for token response

    return {
        "schema_version": 1,
        "access_token": issued.raw_token,
        "refresh_token": refresh.raw_token,
        "token_type": "Bearer",
        "expires_in": min(auth.session_ttl_seconds, 86400),
        "account_id": row.account_id,
        "device_id": device.id,
    }
