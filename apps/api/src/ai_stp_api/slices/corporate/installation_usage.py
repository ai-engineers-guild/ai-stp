"""Corporate intake for settled, coordinate-only installation operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.deps import get_db, require_auth
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service
from ai_stp_contracts.corporate import OrganizationId
from ai_stp_contracts.installation_usage import (
    InstallationOperationBatch,
    InstallationOperationReceipt,
)
from ai_stp_platform import installation_usage_service, runtime_usage_service

router = APIRouter(tags=["corporate"])


@router.post(
    "/corporate/organizations/{organization_id}/telemetry/installation-operations",
    response_model=InstallationOperationReceipt,
)
async def ingest_installation_operations(
    organization_id: OrganizationId,
    payload: InstallationOperationBatch,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_auth)],
) -> InstallationOperationReceipt:
    await service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=runtime_usage_service.PERMISSION_INGEST,
        scope_kind="member",
        scope_id=ctx.account_id,
    )
    receipt = await installation_usage_service.ingest_operations(
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
        action="telemetry_installation.ingest",
        target_table="installation_operation_fact",
        target_id=organization_id,
        request_id=getattr(request.state, "request_id", None),
        payload={
            "accepted": len(receipt.accepted_ids),
            "duplicates": len(receipt.duplicate_ids),
            "rejected": len(receipt.rejected_ids),
        },
    )
    return receipt
