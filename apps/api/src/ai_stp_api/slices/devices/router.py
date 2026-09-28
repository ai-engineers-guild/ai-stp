"""Device lifecycle routes aligned to identity-device OpenAPI contracts."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.deps import get_auth_settings, get_db, require_auth
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import AuthSettings
from ai_stp_api.slices.devices.domain import DeviceState
from ai_stp_api.slices.devices.dto import (
    ChallengeRequest,
    RegisterDeviceRequest,
)
from ai_stp_api.slices.devices.service import (
    create_challenge,
    list_devices,
    register_device,
    revoke_device,
    stored_summaries,
)
from ai_stp_contracts.http import PAGE_SIZE_MAX
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.models import Device

router = APIRouter(tags=["devices"])

# The applied bound the endpoint reports in `page.page_size`; the wire type
# (`DeviceListResponse.items`) forbids returning more than PAGE_SIZE_MAX.
_DEVICE_PAGE_SIZE = PAGE_SIZE_MAX


def _wire_ts(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(UTC)
    moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if moment.utcoffset() != UTC.utcoffset(None):
        moment = moment.astimezone(UTC)
    return format_timestamp(moment)


def _device_etag(device: Device) -> str:
    # Authentication refreshes ``last_seen_at``, ``user_agent`` and
    # ``approximate_location`` on every request. That is observational
    # activity, not a concurrent edit of the revocable resource; any of them
    # in the hash would invalidate an ETag between the read that minted it and
    # the revoke carrying it — ``updated_at`` stays out for the same reason.
    raw = ":".join(
        (
            device.id,
            device.state,
            device.created_at.isoformat() if device.created_at else "",
            device.device_type,
        )
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f'W/"{digest}"'


def _device_record(
    device: Device, *, summary: dict[str, object] | None = None
) -> dict[str, object]:
    """Map storage Device to OpenAPI DeviceRecord resource.

    `summary` is the closed document the device published through sync, or
    nothing — the contract shows it only "when the device has published one",
    and a fabricated operating system is worse than an absent one.
    """
    last = device.last_seen_at or device.created_at
    return {
        "schema_version": 1,
        "device_id": device.id,
        "state": device.state,
        "display_name": device.display_name,
        "registered_at": _wire_ts(device.created_at),
        "last_active_at": _wire_ts(last),
        "device_type": device.device_type,
        "approximate_location": device.approximate_location,
        "user_agent": device.user_agent,
        "summary": summary,
        "etag": _device_etag(device),
    }


@router.post("/devices/challenge", response_model=None)
async def device_challenge(
    request: Request,
    body: ChallengeRequest,
    ctx: Annotated[AuthContext, Depends(require_auth)],
    auth: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> JSONResponse:
    """Issue a one-time signed nonce for device registration (resource body)."""
    del request, ctx
    nonce, expires_in = await create_challenge(auth, body.public_key)
    return JSONResponse(
        content={"schema_version": 1, "nonce": nonce, "expires_in": expires_in},
        status_code=200,
    )


@router.post("/devices", response_model=None)
async def device_register(
    request: Request,
    body: RegisterDeviceRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    auth: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> JSONResponse:
    """Register a device after challenge + Ed25519 verification."""
    summary, created = await register_device(
        db,
        ctx=ctx,
        auth=auth,
        public_key=body.public_key,
        nonce=body.nonce,
        signature=body.signature,
        display_name=body.display_name,
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
        client_ip=request.headers.get("x-ai-stp-client-ip")
        or (request.client.host if request.client is not None else None),
    )
    device = await db.get(Device, summary.id)
    if device is None:
        raise ApiError(ErrorCategory.INTERNAL, "device missing after register")
    synced = await stored_summaries(db, account_id=ctx.account_id, device_ids=[device.id])
    record = _device_record(device, summary=synced.get(device.id))
    return JSONResponse(
        content={"schema_version": 1, "device": record, "created": created},
        status_code=201 if created else 200,
    )


@router.get("/devices", response_model=None)
async def device_list(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    account_id: str | None = Query(default=None),
    x_admin_reason: Annotated[str | None, Header(alias="X-Admin-Reason")] = None,
) -> JSONResponse:
    """List devices as OpenAPI DeviceListResponse (items + page)."""
    del request
    devices = await list_devices(
        db,
        ctx=ctx,
        subject_account_id=account_id,
        admin_reason=x_admin_reason,
    )
    target = account_id or ctx.account_id
    synced = await stored_summaries(
        db, account_id=target, device_ids=[device.id for device in devices]
    )
    items = [_device_record(device, summary=synced.get(device.id)) for device in devices]
    # Newest activity first (contract).
    items.sort(key=lambda row: str(row.get("last_active_at") or ""), reverse=True)
    return JSONResponse(
        content={
            "schema_version": 1,
            "items": items,
            "page": {
                "schema_version": 1,
                "next_cursor": None,
                # The contract's `page_size` is the maximum the endpoint will
                # return per page, not however many rows happened to exist.
                "page_size": _DEVICE_PAGE_SIZE,
            },
        },
        status_code=200,
    )


@router.post("/devices/{device_id}/revoke", response_model=None)
async def device_revoke(
    device_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JSONResponse:
    """Revoke a device; If-Match etag is required (412 when stale)."""
    del request, idempotency_key
    if not device_id.startswith("device_"):
        raise ApiError(ErrorCategory.VALIDATION, "invalid device id")
    if not if_match or not if_match.strip():
        raise ApiError(ErrorCategory.VALIDATION, "If-Match required")

    device = await db.get(Device, device_id)
    # Same code for missing and foreign: do not leak ownership (REQ-206).
    if device is None or device.account_id != ctx.account_id:
        raise ApiError(ErrorCategory.PERMISSION, "permission denied")

    current = _device_etag(device)
    # A retry of a completed revoke carries the pre-revoke ETag and would
    # collide with `state` inside the hash. An already-revoked device is the
    # idempotent replay: answer 200 rather than a false precondition race.
    if device.state != DeviceState.REVOKED.value and if_match.strip() != current:
        raise ApiError(ErrorCategory.PRECONDITION, "precondition failed")

    await revoke_device(db, ctx=ctx, device_id=device_id)
    await db.refresh(device)
    synced = await stored_summaries(db, account_id=device.account_id, device_ids=[device.id])
    now = datetime.now(UTC)
    body = {
        "schema_version": 1,
        "device": _device_record(device, summary=synced.get(device.id)),
        "revoked_at": _wire_ts(device.updated_at or now),
    }
    return JSONResponse(content=body, status_code=200)
