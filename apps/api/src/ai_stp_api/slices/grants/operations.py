"""Transaction-owned receipts for direct grant mutations."""

import hashlib
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_platform.grant_identity_models import GrantOperationReceipt


async def lookup(
    db: AsyncSession, actor: str, key: str, action: Literal["direct", "revoke"], request: JsonValue
) -> tuple[str, GrantOperationReceipt | None]:
    # One lock order for both operations: request key, then grant row. Hash
    # collisions only serialize unrelated work; the primary key owns identity.
    lock = hashlib.sha256(f"ai-stp:grant-operation:{actor}:{key}".encode()).digest()[:8]
    await db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(lock, signed=True))))
    digest = hashlib.sha256(canonize(request)).hexdigest()
    receipt = await db.get(GrantOperationReceipt, (actor, key))
    if receipt is not None and (receipt.action != action or receipt.request_digest != digest):
        raise ApiError(ErrorCategory.CONFLICT, "idempotency key belongs to another grant request")
    return digest, receipt


async def complete(
    db: AsyncSession,
    actor: str,
    key: str,
    action: Literal["direct", "revoke"],
    digest: str,
    grant_id: str,
) -> None:
    db.add(
        GrantOperationReceipt(
            actor_account_id=actor,
            idempotency_key=key,
            action=action,
            request_digest=digest,
            grant_id=grant_id,
        )
    )
    await db.flush()
