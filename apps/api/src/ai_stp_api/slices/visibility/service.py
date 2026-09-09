"""Apply an exact visibility decision without rewriting a published version."""

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_contracts.private_access import VisibilityPlanCreateRequest, VisibilityPlanResponse
from ai_stp_contracts.publication import PublicationConfirmRequest
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_passports.versions import ComponentVersionPassport, SetupVersionPassport
from ai_stp_platform.catalog_search import upsert_catalog_search_projection
from ai_stp_platform.github_models import DistributionVisibilityPlan
from ai_stp_platform.models import Account, CatalogMetadata, Device

PLAN_TTL = timedelta(minutes=30)


async def _device(db: AsyncSession, ctx: AuthContext, device_id: str) -> None:
    if ctx.device_id != device_id:
        raise ApiError(ErrorCategory.VALIDATION, "visibility device must match the session")
    device = await db.get(Device, device_id)
    if device is None or device.account_id != ctx.account_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "device not found")
    if device.state != "active":
        raise ApiError(ErrorCategory.DEVICE_REVOKED, "device is revoked")


async def _owned(
    db: AsyncSession,
    ctx: AuthContext,
    kind: str,
    stable_id: str,
    version: str,
) -> CatalogMetadata:
    row = await db.scalar(
        select(CatalogMetadata)
        .where(
            CatalogMetadata.object_kind == kind,
            CatalogMetadata.stable_id == stable_id,
            CatalogMetadata.version == version,
            CatalogMetadata.owner_account_id == ctx.account_id,
            CatalogMetadata.published_at.is_not(None),
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "published owner version not found")
    if row.lifecycle_state not in {"active", "deprecated"} or not row.passport_digest:
        raise ApiError(ErrorCategory.CONFLICT, "this version cannot change distribution visibility")
    return row


def _timestamp(value: datetime) -> str:
    return format_timestamp(value if value.tzinfo else value.replace(tzinfo=UTC))


async def _target(
    db: AsyncSession, *, ctx: AuthContext, metadata_id: int, lock: bool = False
) -> CatalogMetadata:
    statement = select(CatalogMetadata).where(
        CatalogMetadata.id == metadata_id,
        CatalogMetadata.owner_account_id == ctx.account_id,
    )
    if lock:
        statement = statement.with_for_update()
    target = await db.scalar(statement)
    if target is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "visibility plan not found")
    return target


def _wire(row: DistributionVisibilityPlan, target: CatalogMetadata) -> VisibilityPlanResponse:
    return VisibilityPlanResponse.model_validate(
        {
            "schema_version": 1,
            "plan_id": row.id,
            "plan_hash": row.plan_hash,
            "state": row.state,
            "object_kind": target.object_kind,
            "stable_id": target.stable_id,
            "version": target.version,
            "passport_digest": row.passport_digest,
            "previous_visibility": row.previous_visibility,
            "visibility": row.visibility,
            "actor_id": row.account_id,
            "device_id": row.device_id,
            "expires_at": _timestamp(row.expires_at),
            "effects": [f"set distribution visibility to {row.visibility}"],
        }
    )


async def _plan(db: AsyncSession, ctx: AuthContext, plan_id: str) -> DistributionVisibilityPlan:
    row = await db.scalar(
        select(DistributionVisibilityPlan)
        .where(
            DistributionVisibilityPlan.id == plan_id,
            DistributionVisibilityPlan.account_id == ctx.account_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "visibility plan not found")
    return row


def _expire(row: DistributionVisibilityPlan) -> None:
    expiry = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if row.state == "planned" and expiry <= datetime.now(UTC):
        row.state = "expired"


async def create(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    body: VisibilityPlanCreateRequest,
) -> VisibilityPlanResponse:
    await _device(db, ctx, body.device_id)
    # Serializes identical idempotency keys before insertion, with no second effect.
    await db.scalar(select(Account).where(Account.id == ctx.account_id).with_for_update())
    existing = await db.scalar(
        select(DistributionVisibilityPlan).where(
            DistributionVisibilityPlan.account_id == ctx.account_id,
            DistributionVisibilityPlan.idempotency_key == body.idempotency_key,
        )
    )
    if existing is not None:
        target = await _target(db, ctx=ctx, metadata_id=existing.metadata_id)
        answer = _wire(existing, target)
        if any(
            getattr(answer, field) != getattr(body, field)
            for field in (
                "object_kind",
                "stable_id",
                "version",
                "visibility",
                "device_id",
            )
        ):
            raise ApiError(
                ErrorCategory.CONFLICT, "idempotency key describes another visibility effect"
            )
        _expire(existing)
        return _wire(existing, target)
    target = await _owned(db, ctx, body.object_kind, body.stable_id, body.version)
    expiry = datetime.now(UTC) + PLAN_TTL
    request_hash = digest_canonical(
        "ai-stp:github-request:v1",
        cast(
            JsonValue,
            body.model_dump(mode="json", exclude={"idempotency_key"}),
        ),
    )
    document = {
        "schema_version": 1,
        "plan_id": new_id("plan"),
        "state": "planned",
        "object_kind": body.object_kind,
        "stable_id": body.stable_id,
        "version": body.version,
        "passport_digest": target.passport_digest,
        "previous_visibility": target.visibility,
        "visibility": body.visibility,
        "actor_id": ctx.account_id,
        "device_id": body.device_id,
        "expires_at": format_timestamp(expiry),
        "effects": [f"set distribution visibility to {body.visibility}"],
    }
    document["plan_hash"] = digest_canonical("ai-stp:plan:v1", cast(JsonValue, document))
    response = VisibilityPlanResponse.model_validate(document)
    db.add(
        DistributionVisibilityPlan(
            id=response.plan_id,
            account_id=ctx.account_id,
            device_id=body.device_id,
            metadata_id=target.id,
            passport_digest=target.passport_digest,
            ownership_revision_id=target.current_revision_id,
            previous_visibility=target.visibility,
            visibility=body.visibility,
            plan_hash=response.plan_hash,
            request_hash=request_hash,
            idempotency_key=body.idempotency_key,
            state="planned",
            expires_at=expiry,
        )
    )
    await db.flush()
    return response


async def status(db: AsyncSession, *, ctx: AuthContext, plan_id: str) -> VisibilityPlanResponse:
    row = await _plan(db, ctx, plan_id)
    target = await _target(db, ctx=ctx, metadata_id=row.metadata_id)
    _expire(row)
    return _wire(row, target)


async def _public_dependencies(db: AsyncSession, target: CatalogMetadata) -> None:
    if target.object_kind != "setup":
        return
    passport = SetupVersionPassport.model_validate(target.passport_document)
    pending = list(passport.components)
    seen: set[tuple[str, str, str]] = set()
    while pending:
        ref = pending.pop(0)
        coordinate = (ref.stable_id, ref.version, ref.passport_digest)
        if coordinate in seen:
            continue
        seen.add(coordinate)
        dependency = await db.scalar(
            select(CatalogMetadata)
            .where(
                CatalogMetadata.object_kind == "component",
                CatalogMetadata.stable_id == ref.stable_id,
                CatalogMetadata.version == ref.version,
            )
            .with_for_update(read=True)
        )
        if (
            dependency is None
            or dependency.visibility != "public"
            or dependency.lifecycle_state not in {"active", "deprecated"}
            or dependency.published_at is None
            or dependency.passport_digest != ref.passport_digest
        ):
            raise ApiError(
                ErrorCategory.CONFLICT, "public setup requires every exact pin to be public"
            )
        component = ComponentVersionPassport.model_validate(dependency.passport_document)
        pending.extend(component.requires_components)


async def confirm(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    plan_id: str,
    body: PublicationConfirmRequest,
) -> VisibilityPlanResponse:
    row = await _plan(db, ctx, plan_id)
    target = await _target(db, ctx=ctx, metadata_id=row.metadata_id, lock=True)
    planned = _wire(row, target)
    await _device(db, ctx, planned.device_id)
    if not body.confirmed or body.plan_hash != planned.plan_hash:
        raise ApiError(ErrorCategory.CONFLICT, "visibility confirmation does not match the plan")
    target = await _owned(db, ctx, planned.object_kind, planned.stable_id, planned.version)
    if row.state == "applied":
        return _wire(row, target)
    _expire(row)
    if row.state != "planned":
        return _wire(row, target)
    if (
        target.passport_digest != planned.passport_digest
        or target.visibility != planned.previous_visibility
    ):
        row.state = "refused"
        return _wire(row, target)
    if planned.visibility == "public":
        await _public_dependencies(db, target)
    target.visibility = planned.visibility
    row.state = "applied"
    await db.flush()
    await upsert_catalog_search_projection(
        db, object_kind=target.object_kind, stable_id=target.stable_id
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="distribution_visibility_changed",
        target_table=CatalogMetadata.__tablename__,
        target_id=str(target.id),
        payload={
            "plan_id": plan_id,
            "previous_visibility": planned.previous_visibility,
            "visibility": planned.visibility,
            "passport_digest": planned.passport_digest,
        },
    )
    return _wire(row, target)
