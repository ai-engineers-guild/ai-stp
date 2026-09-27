"""Corporate intake for content-free installation discovery snapshots."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.installation_inventory import (
    InstallationInventoryBatch,
    InstallationInventoryReceipt,
)
from ai_stp_platform import installation_inventory_service, runtime_usage_service

router = APIRouter(tags=["corporate"])


@router.post(
    "/corporate/organizations/{organization_id}/telemetry/installation-inventory",
    response_model=InstallationInventoryReceipt,
)
async def ingest_installation_inventory(
    organization_id: OrganizationId,
    payload: InstallationInventoryBatch,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> InstallationInventoryReceipt:
    await service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=runtime_usage_service.PERMISSION_INGEST,
        scope_kind="member",
        scope_id=ctx.account_id,
    )
    receipt = await installation_inventory_service.ingest_snapshots(
        db,
        organization_id=organization_id,
        batch=payload,
        caller_account_id=ctx.account_id,
        caller_device_id=ctx.device_id,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="telemetry_installation.inventory",
        target_table="installation_inventory_snapshot",
        target_id=organization_id,
        request_id=getattr(request.state, "request_id", None),
        payload={
            "accepted": len(receipt.accepted_ids),
            "duplicates": len(receipt.duplicate_ids),
            "rejected": len(receipt.rejected_ids),
        },
    )
    return receipt
