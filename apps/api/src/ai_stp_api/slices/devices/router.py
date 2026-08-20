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
from ai_stp_api.slices.devices.dto import (
    ChallengeRequest,
    RegisterDeviceRequest,
)
from ai_stp_api.slices.devices.service import (
    create_challenge,
    list_devices,
    register_device,
    revoke_device,
)
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.models import Device

router = APIRouter(tags=["devices"])


def _wire_ts(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(UTC)
    moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if moment.utcoffset() != UTC.utcoffset(None):
        moment = moment.astimezone(UTC)
    return format_timestamp(moment)


def _device_etag(device: Device) -> str:
    # Authentication refreshes ``last_seen_at`` before the route runs. That is
    # observational activity, not a concurrent edit of the revocable resource;
    # including ``updated_at`` would therefore invalidate an ETag on every
    # authenticated request, including the revoke request carrying it.
    raw = ":".join(
        (
            device.id,
            device.state,
            device.created_at.isoformat() if device.created_at else "",
            device.device_type,
            device.approximate_location or "",
            device.user_agent or "",
        )
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f'W/"{digest}"'


def _device_record(device: Device, *, display_name: str | None = None) -> dict[str, object]:
    """Map storage Device to OpenAPI DeviceRecord resource."""
    last = device.last_seen_at or device.created_at
    summary: dict[str, object] | None = None
    if display_name:
        summary = {
            "schema_version": 1,
            "display_name": display_name,
            "operating_system": "linux",
            "architecture": "x86_64",
            "detected_harnesses": [],
            "toolchain_profile_version": "unknown",
            "summary_updated_at": _wire_ts(last),
        }
    return {
        "schema_version": 1,
        "device_id": device.id,
        "state": device.state,
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
    del request
    summary, created = await register_device(
        db,
        ctx=ctx,
        auth=auth,
        public_key=body.public_key,
        nonce=body.nonce,
        signature=body.signature,
        display_name=body.display_name,
    )
    device = await db.get(Device, summary.id)
    if device is None:
        raise ApiError(ErrorCategory.INTERNAL, "device missing after register")
    record = _device_record(device, display_name=body.display_name)
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
    summaries = await list_devices(
        db,
        ctx=ctx,
        subject_account_id=account_id,
        admin_reason=x_admin_reason,
    )
    items: list[dict[str, object]] = []
    for summary in summaries:
        device = await db.get(Device, summary.id)
        if device is None:
            continue
        items.append(_device_record(device, display_name=summary.display_name))
    # Newest activity first (contract).
    items.sort(key=lambda row: str(row.get("last_active_at") or ""), reverse=True)
    return JSONResponse(
        content={
            "schema_version": 1,
            "items": items,
            "page": {
                "schema_version": 1,
                "next_cursor": None,
                "page_size": max(len(items), 1),
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
    if if_match.strip() != current:
        raise ApiError(ErrorCategory.PRECONDITION, "precondition failed")

    summary = await revoke_device(db, ctx=ctx, device_id=device_id)
    await db.refresh(device)
    now = datetime.now(UTC)
    body = {
        "schema_version": 1,
        "device": _device_record(device, display_name=summary.display_name),
        "revoked_at": _wire_ts(device.updated_at or now),
    }
    return JSONResponse(content=body, status_code=200)
