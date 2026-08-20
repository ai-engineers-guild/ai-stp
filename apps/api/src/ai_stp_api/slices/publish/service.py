"""Publication plan application service (SPEC-026)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_contracts.publication import (
    PublicationConfirmRequest,
    PublicationPlanCreateRequest,
    PublicationPlanResponse,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.artifact_bind import (
    ArtifactBindError,
    bind_plan_artifact,
    plan_artifact_is_durable,
)
from ai_stp_platform.models import Device, EvidenceBinding, PublicationPlan, ValidationSnapshot
from ai_stp_platform.publication_logic import (
    PLAN_TTL,
    compute_plan_hash,
    plan_to_wire,
    validate_publication_passport,
)
from ai_stp_platform.queue.engine import enqueue
from ai_stp_platform.queue.states import JobType
from ai_stp_platform.safety.artifact_fetch import passport_artifact_size
from ai_stp_platform.storage.object_store import (
    ImmutableObjectStore,
    ObjectConflict,
    ObjectIntegrityError,
)


async def _require_active_device(db: AsyncSession, *, ctx: AuthContext, device_id: str) -> Device:
    if ctx.device_id is None or ctx.device_id != device_id:
        raise ApiError(ErrorCategory.VALIDATION, "device_id must match session device")
    device = await db.get(Device, device_id)
    if device is None or device.account_id != ctx.account_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "device not found")
    if device.state != "active":
        raise ApiError(ErrorCategory.DEVICE_REVOKED, "device is revoked")
    return device


def _to_response(
    plan: PublicationPlan, evidence: list[dict[str, object]] | None = None
) -> PublicationPlanResponse:
    return PublicationPlanResponse.model_validate(plan_to_wire(plan, evidence=evidence))


async def create_plan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    body: PublicationPlanCreateRequest,
) -> PublicationPlanResponse:
    await _require_active_device(db, ctx=ctx, device_id=body.device_id)
    existing = await db.scalar(
        select(PublicationPlan).where(
            PublicationPlan.actor_account_id == ctx.account_id,
            PublicationPlan.idempotency_key == body.idempotency_key,
        )
    )
    if existing is not None:
        return _to_response(existing)

    passport_model, invalid = validate_publication_passport(
        dict(body.passport),
        object_kind=body.object_kind,
        stable_id=body.stable_id,
        version=body.version,
        content_digest=body.content_digest,
        owner_account_id=ctx.account_id,
    )
    if passport_model is None:
        raise ApiError(
            ErrorCategory.VALIDATION,
            "passport invalid for publication",
            details={"fields": ",".join(invalid)},
        )
    attestations = [a.model_dump(mode="json") for a in body.attestations]
    passport = passport_model.model_dump(mode="json")
    plan_hash = compute_plan_hash(
        actor_account_id=ctx.account_id,
        device_id=body.device_id,
        object_kind=body.object_kind,
        stable_id=body.stable_id,
        version=body.version,
        content_digest=body.content_digest,
        policy_version=body.policy_version,
        passport=passport,
        attestations=attestations,
    )
    plan = PublicationPlan(
        id=new_id("plan"),
        actor_account_id=ctx.account_id,
        device_id=body.device_id,
        object_kind=body.object_kind,
        stable_id=body.stable_id,
        version=body.version,
        content_digest=body.content_digest,
        policy_version=body.policy_version,
        plan_hash=plan_hash,
        state="ready",
        passport=passport,
        attestations=attestations,
        effects=["validate", "publish_catalog_version"],
        idempotency_key=body.idempotency_key,
        expires_at=datetime.now(UTC) + PLAN_TTL,
    )
    db.add(plan)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="publication.plan_created",
        target_table="publication_plan",
        target_id=plan.id,
        payload={"stable_id": plan.stable_id, "version": plan.version},
    )
    await db.flush()
    return _to_response(plan)


async def read_plan(db: AsyncSession, *, ctx: AuthContext, plan_id: str) -> PublicationPlanResponse:
    plan = await db.get(PublicationPlan, plan_id)
    if plan is None or plan.actor_account_id != ctx.account_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "plan not found")
    evidence = await _evidence_for_plan(db, plan_id=plan.id)
    return _to_response(plan, evidence=evidence)


async def _evidence_for_plan(db: AsyncSession, *, plan_id: str) -> list[dict[str, object]]:
    snapshot = await db.scalar(
        select(ValidationSnapshot).where(ValidationSnapshot.plan_id == plan_id)
    )
    if snapshot is None:
        return []
    rows = list(
        (
            await db.execute(
                select(EvidenceBinding).where(EvidenceBinding.snapshot_id == snapshot.id)
            )
        )
        .scalars()
        .all()
    )
    out: list[dict[str, object]] = []
    for row in rows:
        expires = None
        if row.expires_at is not None:
            exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
            expires = exp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        out.append(
            {
                "schema_version": 1,
                "check_id": row.check_id,
                "result": row.result,
                "source": row.source,
                "expires_at": expires,
            }
        )
    return out


async def bind_artifact(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    plan_id: str,
    payload: bytes,
    store: ImmutableObjectStore,
) -> PublicationPlanResponse:
    plan = await db.get(PublicationPlan, plan_id)
    if plan is None or plan.actor_account_id != ctx.account_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "plan not found")
    await _require_active_device(db, ctx=ctx, device_id=plan.device_id)
    if plan.state in {"failed", "cancelled", "stale"}:
        raise ApiError(ErrorCategory.CONFLICT, f"plan is {plan.state}")
    expected_size = passport_artifact_size(dict(plan.passport))
    if expected_size is None:
        raise ApiError(ErrorCategory.VALIDATION, "passport does not declare artifact size")
    try:
        await bind_plan_artifact(
            store=store,
            payload=payload,
            expected_digest=plan.content_digest,
            expected_size=expected_size,
        )
    except ArtifactBindError as exc:
        raise ApiError(ErrorCategory.VALIDATION, str(exc)) from exc
    except ObjectIntegrityError as exc:
        raise ApiError(
            ErrorCategory.VALIDATION, "artifact digest or size does not match the plan"
        ) from exc
    except ObjectConflict as exc:
        raise ApiError(
            ErrorCategory.CONFLICT, "different bytes already occupy this digest"
        ) from exc
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="publication.artifact_bound",
        target_table="publication_plan",
        target_id=plan.id,
        payload={"digest": plan.content_digest, "size_bytes": expected_size},
    )
    return _to_response(plan)


async def confirm_plan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    plan_id: str,
    body: PublicationConfirmRequest,
    store: ImmutableObjectStore,
) -> PublicationPlanResponse:
    plan = await db.get(PublicationPlan, plan_id)
    if plan is None or plan.actor_account_id != ctx.account_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "plan not found")
    await _require_active_device(db, ctx=ctx, device_id=plan.device_id)

    if plan.confirm_idempotency_key == body.idempotency_key:
        evidence = await _evidence_for_plan(db, plan_id=plan.id)
        return _to_response(plan, evidence=evidence)

    if plan.state in {"validating", "publish_planned", "published"}:
        if plan.plan_hash != body.plan_hash:
            raise ApiError(ErrorCategory.CONFLICT, "plan already confirmed with different hash")
        plan.confirm_idempotency_key = body.idempotency_key
        await db.flush()
        evidence = await _evidence_for_plan(db, plan_id=plan.id)
        return _to_response(plan, evidence=evidence)

    if plan.state in {"failed", "cancelled", "stale"}:
        raise ApiError(ErrorCategory.CONFLICT, f"plan is {plan.state}")

    now = datetime.now(UTC)
    expires = plan.expires_at if plan.expires_at.tzinfo else plan.expires_at.replace(tzinfo=UTC)
    if expires <= now:
        plan.state = "stale"
        await db.flush()
        raise ApiError(ErrorCategory.VALIDATION, "plan expired")

    if body.plan_hash != plan.plan_hash:
        raise ApiError(ErrorCategory.VALIDATION, "plan_hash mismatch")

    expected_size = passport_artifact_size(dict(plan.passport))
    if not await plan_artifact_is_durable(
        store=store,
        content_digest=plan.content_digest,
        expected_size=expected_size,
    ):
        raise ApiError(ErrorCategory.VALIDATION, "publication artifact bytes are not bound")

    plan.state = "validating"
    plan.confirm_idempotency_key = body.idempotency_key
    await enqueue(
        db,
        job_type=JobType.VALIDATE,
        payload={"plan_id": plan.id},
        idempotency_key=f"validate:{plan.id}",
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="publication.plan_confirmed",
        target_table="publication_plan",
        target_id=plan.id,
        payload={"state": plan.state},
    )
    await db.flush()
    return _to_response(plan)
