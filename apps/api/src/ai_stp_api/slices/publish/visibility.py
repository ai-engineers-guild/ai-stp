"""One-way component exposure over immutable passports and existing object locations."""

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.profile.service import get_public_publisher
from ai_stp_api.slices.publish.service import (
    _require_active_device,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_contracts.private_access import (
    VisibilityConfirmRequest,
    VisibilityPlanCreateRequest,
    VisibilityPlanResponse,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_passports.versions import ComponentVersionPassport
from ai_stp_platform.catalog_projection import verify_passport_integrity
from ai_stp_platform.catalog_read import public_version_row
from ai_stp_platform.catalog_search import upsert_catalog_search_projection
from ai_stp_platform.github_authority import utc
from ai_stp_platform.github_client import GitHubClient, GitHubError
from ai_stp_platform.github_models import DistributionVisibilityPlan
from ai_stp_platform.github_sources import bound_source, public_bound_source_bytes, request_digest
from ai_stp_platform.models import (
    Account,
    CatalogIdentity,
    CatalogMetadata,
    ObjectLocation,
    PublicationPlan,
)
from ai_stp_platform.publication_logic import run_platform_checks, validate_publication_passport
from ai_stp_platform.safety.orchestrator import run_safety_suite
from ai_stp_platform.safety.policy import POLICY_VERSION
from ai_stp_platform.storage.object_store import ImmutableObjectStore, ObjectIntegrityError
from ai_stp_sources.definition import pack_component_tree
from ai_stp_sources.errors import SourceError
from ai_stp_sources.git import resolve_git
from ai_stp_sources.models import GitIntent


async def _owned_version(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    stable_id: str,
    version: str,
) -> CatalogMetadata:
    row = await db.scalar(
        select(CatalogMetadata)
        .where(
            CatalogMetadata.object_kind == "component",
            CatalogMetadata.stable_id == stable_id,
            CatalogMetadata.version == version,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "component version not found")
    identity = await db.scalar(
        select(CatalogIdentity)
        .where(
            CatalogIdentity.stable_id == stable_id,
        )
        .with_for_update()
    )
    if (
        row.owner_account_id != ctx.account_id
        or identity is None
        or identity.owner_account_id != ctx.account_id
    ):
        raise ApiError(ErrorCategory.PERMISSION, "only the current component owner can promote it")
    if row.published_at is None or row.lifecycle_state not in {"active", "deprecated"}:
        raise ApiError(
            ErrorCategory.PRECONDITION, "component is not eligible for public distribution"
        )
    return row


def _response(plan: DistributionVisibilityPlan, row: CatalogMetadata) -> VisibilityPlanResponse:
    return VisibilityPlanResponse.model_validate(
        {
            "plan_id": plan.id,
            "plan_hash": plan.plan_hash,
            "state": plan.state,
            "object_kind": "component",
            "stable_id": row.stable_id,
            "version": row.version,
            "passport_digest": plan.passport_digest,
            "previous_visibility": plan.previous_visibility,
            "visibility": "public",
            "actor_id": plan.account_id,
            "device_id": plan.device_id,
            "expires_at": format_timestamp(utc(plan.expires_at)),
            "effects": ["expose_component_version"],
        }
    )


async def create_plan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    body: VisibilityPlanCreateRequest,
) -> VisibilityPlanResponse:
    await _require_active_device(db, ctx=ctx, device_id=body.device_id)
    if body.object_kind != "component" or body.visibility != "public":
        raise ApiError(
            ErrorCategory.VALIDATION, "only component private-to-public promotion is supported"
        )
    row = await _owned_version(db, ctx=ctx, stable_id=body.stable_id, version=body.version)
    digest = request_digest(body.model_dump(mode="json", exclude={"idempotency_key"}))
    existing = await db.scalar(
        select(DistributionVisibilityPlan).where(
            DistributionVisibilityPlan.account_id == ctx.account_id,
            DistributionVisibilityPlan.idempotency_key == body.idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != digest:
            raise ApiError(ErrorCategory.CONFLICT, "idempotency key belongs to another request")
        return _response(existing, row)
    if not row.passport_digest:
        raise ApiError(ErrorCategory.CATALOG_INTEGRITY, "published passport digest is unavailable")
    identity = await db.get(CatalogIdentity, row.stable_id)
    expiry = datetime.now(UTC) + timedelta(minutes=10)
    plan = DistributionVisibilityPlan(
        id=str(uuid4()),
        account_id=ctx.account_id,
        device_id=body.device_id,
        metadata_id=row.id,
        passport_digest=row.passport_digest,
        ownership_revision_id=identity.ownership_revision_id if identity else None,
        previous_visibility=row.visibility,
        visibility="public",
        request_hash=digest,
        idempotency_key=body.idempotency_key,
        expires_at=expiry,
        state="planned",
        plan_hash=request_digest(
            {
                "request": digest,
                "actor": ctx.account_id,
                "passport": row.passport_digest,
                "visibility": row.visibility,
                "expires_at": format_timestamp(expiry),
                "ownership": identity.ownership_revision_id if identity else None,
            }
        ),
    )
    db.add(plan)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="publication.visibility_planned",
        target_table="distribution_visibility_plan",
        target_id=plan.id,
    )
    return _response(plan, row)


async def read_plan(db: AsyncSession, *, ctx: AuthContext, plan_id: str) -> VisibilityPlanResponse:
    plan = await db.get(DistributionVisibilityPlan, plan_id)
    if plan is None or plan.account_id != ctx.account_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "visibility plan not found")
    row = await db.get(CatalogMetadata, plan.metadata_id)
    if row is None or row.owner_account_id != ctx.account_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "component version not found")
    return _response(plan, row)


async def _validate_public(
    db: AsyncSession,
    *,
    row: CatalogMetadata,
    store: ImmutableObjectStore,
    client: GitHubClient,
) -> None:
    account = await db.get(Account, row.owner_account_id)
    profile = await get_public_publisher(db, account_id=row.owner_account_id)
    if (
        account is None
        or not account.show_profile_publicly
        or not account.allow_publisher_listing
        or profile is None
        or not str(profile.get("display_name") or "").strip()
    ):
        raise ApiError(
            ErrorCategory.VALIDATION, "publish a non-empty public publisher profile first"
        )
    document = dict(row.passport_document or {})
    artifact = document.get("artifact")
    if not isinstance(artifact, dict):
        raise ApiError(ErrorCategory.CATALOG_INTEGRITY, "artifact identity is unavailable")
    content_digest = str(cast(dict[str, object], artifact).get("digest") or "")
    original = await db.scalar(
        select(PublicationPlan)
        .where(
            PublicationPlan.object_kind == "component",
            PublicationPlan.stable_id == row.stable_id,
            PublicationPlan.version == row.version,
            PublicationPlan.state == "published",
        )
        .order_by(PublicationPlan.created_at)
    )
    binding = await bound_source(db, original) if original is not None else None
    passport, invalid = validate_publication_passport(
        document,
        object_kind="component",
        stable_id=row.stable_id,
        version=str(row.version),
        content_digest=content_digest,
        expected_visibility=str(document.get("visibility")),
        source_bound=binding is not None,
    )
    if not isinstance(passport, ComponentVersionPassport) or any(
        item["result"] != "passed"
        for item in run_platform_checks(
            passport=document,
            content_digest=content_digest,
            source_bound=binding is not None,
        )
    ):
        raise ApiError(
            ErrorCategory.VALIDATION,
            "public passport requirements are not met",
            details={"fields": ",".join(invalid)},
        )
    if (
        digest_bytes("ai-stp:passport:v1", canonize(cast(JsonValue, document)))
        != row.passport_digest
    ):
        raise ApiError(ErrorCategory.CATALOG_INTEGRITY, "passport digest mismatch")
    locations = list(
        (
            await db.scalars(
                select(ObjectLocation).where(
                    ObjectLocation.catalog_metadata_id == row.id,
                )
            )
        ).all()
    )
    primary = next((item for item in locations if item.purpose == "artifact"), None)
    if (
        primary is None
        or primary.digest != content_digest
        or primary.size_bytes != passport.artifact.size_bytes
    ):
        raise ApiError(ErrorCategory.CATALOG_INTEGRITY, "artifact location is unavailable")
    payloads: dict[str, bytes] = {}
    try:
        for location in locations:
            payload = await store.read_verified(
                object_key=location.object_key,
                expected_digest=location.digest,
                expected_size=location.size_bytes,
                bucket=location.bucket,
            )
            if payload is None:
                raise ObjectIntegrityError("artifact unavailable")
            payloads[location.digest] = payload
    except ObjectIntegrityError:
        raise ApiError(
            ErrorCategory.CATALOG_INTEGRITY, "published artifact failed integrity validation"
        ) from None
    try:
        if binding is not None:
            source_bytes = await public_bound_source_bytes(binding, client=client)
        else:
            source = passport.source
            if source is None:
                raise GitHubError("public_source_required", status=400)
            snapshot = await resolve_git(
                GitIntent(
                    repository_url=str(source.repository),
                    tracked_ref=str(source.commit),
                    subpath=str(source.path),
                ),
                fetch=client.fetch,
            )
            source_bytes = pack_component_tree(snapshot.files)
        if source_bytes != payloads[content_digest]:
            raise GitHubError("source_binding_mismatch", status=412)
    except (GitHubError, SourceError):
        raise ApiError(
            ErrorCategory.VALIDATION,
            "the exact source must be public and match the artifact",
            details={"reason": "public_source_required"},
        ) from None
    # Re-run the same mandatory safety barrier over the common and native projection bytes.
    required = {content_digest: passport.artifact.size_bytes}
    for adaptation in passport.adaptations:
        for scope in adaptation.scope_adaptations:
            required[str(scope.projection_artifact.digest)] = scope.projection_artifact.size_bytes
    for digest, size in required.items():
        if digest not in payloads or len(payloads[digest]) != size:
            raise ApiError(ErrorCategory.CATALOG_INTEGRITY, "projection artifact unavailable")
        safety = await run_safety_suite(
            passport=document,
            content_digest=digest,
            policy_version=POLICY_VERSION,
            object_kind="component",
            artifact_bytes=payloads[digest],
            use_cache=False,
        )
        if any(item["mandatory"] and item["result"] != "passed" for item in safety.bindings()):
            raise ApiError(ErrorCategory.VALIDATION, "mandatory public safety checks did not pass")


async def confirm(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    plan_id: str,
    body: VisibilityConfirmRequest,
    store: ImmutableObjectStore,
    client: GitHubClient,
) -> VisibilityPlanResponse:
    plan = await db.scalar(
        select(DistributionVisibilityPlan)
        .where(
            DistributionVisibilityPlan.id == plan_id,
            DistributionVisibilityPlan.account_id == ctx.account_id,
        )
        .with_for_update()
    )
    if plan is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "visibility plan not found")
    await _require_active_device(db, ctx=ctx, device_id=plan.device_id)
    target = await db.get(CatalogMetadata, plan.metadata_id)
    if target is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "component version not found")
    row = await _owned_version(db, ctx=ctx, stable_id=target.stable_id, version=str(target.version))
    identity = await db.get(CatalogIdentity, row.stable_id)
    if (
        body.plan_hash != plan.plan_hash
        or row.passport_digest != plan.passport_digest
        or identity is None
        or identity.ownership_revision_id != plan.ownership_revision_id
    ):
        raise ApiError(ErrorCategory.PRECONDITION, "visibility plan is stale")
    if plan.state == "applied":
        return _response(plan, row)
    if utc(plan.expires_at) <= datetime.now(UTC):
        raise ApiError(ErrorCategory.PRECONDITION, "visibility plan expired")
    if row.visibility != "public":
        await _validate_public(db, row=row, store=store, client=client)
        row.visibility = "public"
        # Projection integrity accepts the separate distribution policy, not a rewritten passport.
        verify_passport_integrity(public_version_row(row))
        await upsert_catalog_search_projection(db, object_kind="component", stable_id=row.stable_id)
    plan.state = "applied"
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="publication.visibility_changed",
        target_table="distribution_visibility_plan",
        target_id=plan.id,
        payload={"visibility": "public", "passport_digest": row.passport_digest},
    )
    return _response(plan, row)
