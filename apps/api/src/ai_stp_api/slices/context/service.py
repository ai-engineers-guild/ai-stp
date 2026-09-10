"""Server-owned context resolution and capability projection."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_contracts.context import (
    CapabilityProjection,
    ProjectConflictResolutionRequest,
    ProjectLinkPlanRequest,
    ProjectLinkPlanResponse,
    ProjectLinkProposalRequest,
    ProjectLinkRequest,
    ProjectLinkResponse,
    ProjectRevisionPullResponse,
    ProjectRevisionPushRequest,
    ProjectRevisionPushResponse,
    ProjectRevisionView,
    ProjectSyncApplyRequest,
    ProjectSyncPlanRequest,
    ProjectSyncPlanResponse,
    ProjectUnlinkPlanRequest,
    ProjectUnlinkPlanResponse,
    ProjectUnlinkRequest,
    ProviderProjectObservationRequest,
    validate_public_project_data,
)
from ai_stp_contracts.context import (
    ProjectRevisionReceipt as ProjectRevisionReceiptContract,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.models import Account, Device
from ai_stp_platform.organization_models import (
    Organization,
    OrganizationMembership,
    ProjectIdentity,
    ProjectLink,
    ProjectLinkPlan,
    ProjectLinkProposal,
    ProjectRevision,
    ProjectRevisionHead,
    ProjectSyncPlan,
    ProjectUnlinkPlan,
)
from ai_stp_platform.organization_models import (
    ProjectRevisionReceipt as ProjectRevisionReceiptRow,
)

CAPABILITY_TTL_SECONDS = 60

LOCAL_CAPABILITIES: tuple[str, ...] = (
    "catalog_object.list",
    "catalog_object.read",
    "landscape.list",
    "landscape.read",
    "project.list",
    "project.read",
    "technology.list",
    "technology.read",
)
PERSONAL_CAPABILITIES: tuple[str, ...] = (
    *LOCAL_CAPABILITIES,
    "catalog_object.publish",
    "organization.read",
    "project.create",
    "project.link",
    "project.unlink",
    "project.update",
)
CORPORATE_CAPABILITIES: tuple[str, ...] = (
    *PERSONAL_CAPABILITIES,
    "assignment.assign",
    "audit.read",
    "deployment.operate",
    "invitation.manage",
    "member.manage",
    "organization.manage",
    "saml.manage",
    "team.manage",
    "telemetry.read",
)

_MODE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "local": LOCAL_CAPABILITIES,
    "personal": PERSONAL_CAPABILITIES,
    "corporate": CORPORATE_CAPABILITIES,
}
_IMPLEMENTED_CAPABILITIES = frozenset(PERSONAL_CAPABILITIES)
_CORPORATE_ONLY = frozenset(set(CORPORATE_CAPABILITIES) - set(PERSONAL_CAPABILITIES))
_CORPORATE_ADMIN_ONLY = frozenset(
    {
        "assignment.assign",
        "invitation.manage",
        "member.manage",
        "organization.manage",
        "saml.manage",
        "team.manage",
    }
)


def _timestamp(value: datetime) -> str:
    moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return format_timestamp(moment.astimezone(UTC))


def _plan_digest(values: dict[str, object]) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    )


async def personal_organization(
    db: AsyncSession, *, account_id: str, create: bool = False
) -> Organization | None:
    """Find the account's personal organization, optionally creating it."""
    if create:
        # Serialize first-use creation per account. The partial unique index is
        # the final guard; the row lock keeps concurrent requests from turning
        # the first personal-context read into a transient 500.
        await db.get(Account, account_id, with_for_update=True)
    result = await db.execute(
        select(Organization).where(
            Organization.kind == "personal",
            Organization.owner_account_id == account_id,
        )
    )
    organizations = list(result.scalars().all())
    if len(organizations) > 1:
        raise ApiError(ErrorCategory.INTERNAL, "personal organization state is invalid")
    organization = organizations[0] if organizations else None
    if organization is not None or not create:
        if organization is None:
            return None
        memberships = list(
            (
                await db.scalars(
                    select(OrganizationMembership).where(
                        OrganizationMembership.organization_id == organization.id,
                    )
                )
            ).all()
        )
        if (
            len(memberships) != 1
            or memberships[0].account_id != account_id
            or memberships[0].role != "owner"
            or memberships[0].state != "active"
        ):
            raise ApiError(ErrorCategory.INTERNAL, "personal organization state is invalid")
        return organization
    organization = Organization(
        id=new_id("organization"),
        kind="personal",
        owner_account_id=account_id,
        display_name="Personal",
    )
    db.add(organization)
    await db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            account_id=account_id,
            role="owner",
            state="active",
        )
    )
    await db.flush()
    return organization


async def organizations_for_account(db: AsyncSession, *, account_id: str) -> list[Organization]:
    """Return only active memberships, in stable display order."""
    result = await db.execute(
        select(Organization)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(
            OrganizationMembership.account_id == account_id,
            OrganizationMembership.state == "active",
        )
        .order_by(Organization.kind.asc(), Organization.display_name.asc(), Organization.id.asc())
    )
    return list(result.scalars().all())


async def require_membership(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str
) -> Organization:
    """Resolve an explicit organization and enforce active membership."""
    result = await db.execute(
        select(Organization)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(
            Organization.id == organization_id,
            OrganizationMembership.account_id == ctx.account_id,
            OrganizationMembership.state == "active",
        )
    )
    organization = result.scalar_one_or_none()
    if organization is None:
        raise ApiError(ErrorCategory.PERMISSION, "organization access denied")
    return organization


async def _membership(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str
) -> tuple[Organization, OrganizationMembership]:
    result = await db.execute(
        select(Organization, OrganizationMembership)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(
            Organization.id == organization_id,
            OrganizationMembership.account_id == ctx.account_id,
            OrganizationMembership.state == "active",
        )
    )
    pair = result.one_or_none()
    if pair is None:
        raise ApiError(ErrorCategory.PERMISSION, "organization access denied")
    organization, membership = pair
    return organization, membership


def projection_for(
    *,
    mode: str,
    organization_id: str | None,
    policy_revision: int = 1,
    membership_revision: int | None = None,
    role: str = "owner",
) -> CapabilityProjection:
    """Build the single bounded capability answer for a resolved context."""
    if mode not in _MODE_CAPABILITIES:
        raise ApiError(ErrorCategory.VALIDATION, "unknown product mode")
    now = datetime.now(UTC)
    available = [
        capability
        for capability in _MODE_CAPABILITIES[mode]
        if capability in _IMPLEMENTED_CAPABILITIES
    ]
    if mode == "corporate" and role not in {"owner", "admin"}:
        available = [item for item in available if item not in _CORPORATE_ADMIN_ONLY]
    available.sort()
    unavailable = {
        capability: (
            "forbidden"
            if mode == "corporate"
            and (capability in _IMPLEMENTED_CAPABILITIES or role not in {"owner", "admin"})
            else "unsupported"
        )
        for capability in _CORPORATE_ONLY
        if capability not in available
    }
    revision = (
        f"{policy_revision}:{membership_revision}"
        if membership_revision is not None
        else str(policy_revision)
    )
    authorization_revision = f"{mode}:{organization_id or 'local'}:{revision}"
    return CapabilityProjection(
        mode=mode,  # type: ignore[arg-type]
        context_kind=mode,  # type: ignore[arg-type]
        organization_id=organization_id,
        authorization_revision=authorization_revision,
        issued_at=_timestamp(now),
        generated_at=_timestamp(now),
        expires_at=_timestamp(now + timedelta(seconds=CAPABILITY_TTL_SECONDS)),
        capabilities=available,
        unavailable=unavailable,  # type: ignore[arg-type]
    )


async def remote_projection(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str
) -> CapabilityProjection:
    """Authorize and project one remote organization."""
    organization, membership = await _membership(db, ctx=ctx, organization_id=organization_id)
    return projection_for(
        mode=organization.kind,
        organization_id=organization.id,
        policy_revision=organization.revision,
        membership_revision=membership.revision,
        role=membership.role,
    )


async def require_capability(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    capability: str,
    authorization_revision: str,
) -> Organization:
    """Re-evaluate the projection and reject forged or stale client hints."""
    organization, membership = await _membership(db, ctx=ctx, organization_id=organization_id)
    projection = projection_for(
        mode=organization.kind,
        organization_id=organization.id,
        policy_revision=organization.revision,
        membership_revision=membership.revision,
        role=membership.role,
    )
    if authorization_revision != projection.authorization_revision:
        raise ApiError(
            ErrorCategory.PRECONDITION,
            "capability projection is stale",
            details={"reason": "capability_stale"},
        )
    if capability not in projection.capabilities:
        raise ApiError(
            ErrorCategory.PERMISSION,
            "capability is not available in this context",
            details={"capability": capability},
        )
    return organization


async def require_active_device(db: AsyncSession, *, ctx: AuthContext) -> Device:
    """Project links and syncs are device-bound, like the existing sync ledger."""
    if ctx.device_id is None:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "device-bound session required")
    device = await db.get(Device, ctx.device_id)
    if device is None or device.account_id != ctx.account_id:
        raise ApiError(ErrorCategory.AUTH_REQUIRED, "device-bound session required")
    if device.state != "active":
        raise ApiError(ErrorCategory.DEVICE_REVOKED, "device is revoked")
    return device


async def _link_for_member(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    link_id: str,
    for_update: bool = False,
) -> ProjectLink:
    """Load a link only through an active membership in its organization."""
    statement = (
        select(ProjectLink)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == ProjectLink.organization_id,
        )
        .join(
            ProjectIdentity,
            (ProjectIdentity.id == ProjectLink.remote_project_id)
            & (ProjectIdentity.organization_id == ProjectLink.organization_id)
            & (ProjectIdentity.namespace == "remote"),
        )
        .where(
            ProjectLink.id == link_id,
            ProjectLink.organization_id == organization_id,
            OrganizationMembership.account_id == ctx.account_id,
            OrganizationMembership.state == "active",
        )
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    link = result.scalar_one_or_none()
    if link is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "project link not found")
    return link


def _require_linked(link: ProjectLink, *, allow_conflict: bool = False) -> ProjectLink:
    """Reject operations on an unlinked link; conflict resolution is explicit."""
    if link.state != "linked" and not (allow_conflict and link.state == "conflict"):
        raise ApiError(ErrorCategory.PRECONDITION, "project link is not active")
    return link


def link_body(link: ProjectLink) -> ProjectLinkResponse:
    """Project the ORM link without exposing organization internals."""
    updated = link.updated_at or datetime.now(UTC)
    return ProjectLinkResponse(
        link_id=link.id,
        plan_id=link.plan_id,
        plan_digest=link.plan_digest,
        organization_id=link.organization_id,
        local_project_id=link.local_project_id,
        remote_project_id=link.remote_project_id,
        provider_project_id=link.provider_project_id,
        state=link.state,  # type: ignore[arg-type]
        local_revision=link.local_revision,
        remote_revision=link.remote_revision,
        provider_revision=link.provider_revision,
        conflict_server_revision=link.conflict_server_revision,
        conflict_client_revision=link.conflict_client_revision,
        conflict_common_ancestor=link.conflict_common_ancestor,
        revision=link.revision,
        updated_at=_timestamp(updated),
    )


def link_plan_body(plan: ProjectLinkPlan) -> ProjectLinkPlanResponse:
    """Project only the exact fields a client must confirm."""
    return ProjectLinkPlanResponse(
        plan_id=plan.id,
        organization_id=plan.organization_id,
        local_project_id=plan.local_project_id,
        remote_project_id=plan.remote_project_id,
        provider_project_id=plan.provider_project_id,
        local_revision=plan.local_revision,
        remote_revision=plan.remote_revision,
        provider_revision=plan.provider_revision,
        authorization_revision=plan.authorization_revision,
        plan_digest=plan.plan_digest,
        expires_at=_timestamp(plan.expires_at),
    )


def unlink_plan_body(plan: ProjectUnlinkPlan) -> ProjectUnlinkPlanResponse:
    """Project only the exact fields a client must confirm."""
    return ProjectUnlinkPlanResponse(
        plan_id=plan.id,
        link_id=plan.link_id,
        organization_id=plan.organization_id,
        local_project_id=plan.local_project_id,
        remote_project_id=plan.remote_project_id,
        provider_project_id=plan.provider_project_id,
        expected_link_revision=plan.expected_link_revision,
        local_revision=plan.local_revision,
        remote_revision=plan.remote_revision,
        provider_revision=plan.provider_revision,
        authorization_revision=plan.authorization_revision,
        plan_digest=plan.plan_digest,
        expires_at=_timestamp(plan.expires_at),
    )


async def create_project_link_plan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: ProjectLinkPlanRequest,
) -> ProjectLinkPlanResponse:
    """Create or replay the server-authored link decision."""
    device = await require_active_device(db, ctx=ctx)
    await require_capability(
        db,
        ctx=ctx,
        organization_id=organization_id,
        capability="project.link",
        authorization_revision=payload.authorization_revision,
    )
    replay = await db.scalar(
        select(ProjectLinkPlan).where(
            ProjectLinkPlan.organization_id == organization_id,
            ProjectLinkPlan.idempotency_key == payload.idempotency_key,
        )
    )
    if replay is not None:
        expected = (
            replay.local_project_id,
            replay.remote_project_id,
            replay.provider_project_id,
            replay.local_revision,
            replay.remote_revision,
            replay.provider_revision,
        )
        actual = (
            payload.local_project_id,
            payload.remote_project_id,
            payload.provider_project_id,
            payload.local_revision,
            payload.remote_revision,
            payload.provider_revision,
        )
        if expected != actual or replay.actor_account_id != ctx.account_id:
            raise ApiError(ErrorCategory.CONFLICT, "idempotency key belongs to another link plan")
        return link_plan_body(replay)

    await _validate_link_targets(db, organization_id=organization_id, payload=payload)
    active_link = await db.scalar(
        select(ProjectLink).where(
            ProjectLink.organization_id == organization_id,
            ProjectLink.local_project_id == payload.local_project_id,
            ProjectLink.state.in_(("linked", "conflict")),
        )
    )
    if active_link is not None:
        raise ApiError(ErrorCategory.CONFLICT, "local project is already linked")

    values = {
        "organization_id": organization_id,
        "actor_account_id": ctx.account_id,
        "device_id": device.id,
        "local_project_id": payload.local_project_id,
        "remote_project_id": payload.remote_project_id,
        "provider_project_id": payload.provider_project_id,
        "local_revision": payload.local_revision,
        "remote_revision": payload.remote_revision,
        "provider_revision": payload.provider_revision,
        "authorization_revision": payload.authorization_revision,
    }
    expires_at = datetime.now(UTC) + timedelta(minutes=15)
    digest = _plan_digest({**values, "expires_at": _timestamp(expires_at)})
    plan = ProjectLinkPlan(
        id=new_id("link_plan"),
        **values,
        idempotency_key=payload.idempotency_key,
        plan_digest=digest,
        expires_at=expires_at,
    )
    db.add(plan)
    await db.flush()
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.link_planned",
        target_table="project_link_plan",
        target_id=plan.id,
        payload={"organization_id": organization_id},
    )
    return link_plan_body(plan)


async def observe_provider_project(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: ProviderProjectObservationRequest,
) -> ProjectIdentity:
    """Record provider evidence without matching or mutating a project link."""
    await require_active_device(db, ctx=ctx)
    await require_capability(
        db,
        ctx=ctx,
        organization_id=organization_id,
        capability="project.update",
        authorization_revision=payload.authorization_revision,
    )
    identity = await db.scalar(
        select(ProjectIdentity).where(
            ProjectIdentity.id == payload.provider_project_id,
            ProjectIdentity.organization_id == organization_id,
            ProjectIdentity.namespace == "provider",
        )
    )
    duplicate = await db.scalar(
        select(ProjectIdentity).where(
            ProjectIdentity.organization_id == organization_id,
            ProjectIdentity.namespace == "provider",
            ProjectIdentity.immutable_repository_id == payload.immutable_repository_id,
            ProjectIdentity.state == "active",
        )
    )
    if duplicate is not None and (identity is None or duplicate.id != identity.id):
        raise ApiError(ErrorCategory.CONFLICT, "provider repository is already bound")
    is_new_identity = identity is None
    if is_new_identity:
        identity = ProjectIdentity(
            id=payload.provider_project_id,
            organization_id=organization_id,
            namespace="provider",
            external_key=payload.immutable_repository_id,
            display_name=payload.observed_name,
        )
        db.add(identity)
    elif identity.external_key != payload.immutable_repository_id:
        raise ApiError(ErrorCategory.CONFLICT, "provider repository identity is immutable")
    identity.provider_kind = payload.provider_kind
    identity.provider_installation_id = payload.installation_id
    identity.provider_namespace_id = payload.namespace_id
    identity.immutable_repository_id = payload.immutable_repository_id
    identity.current_url = payload.current_url
    identity.observed_name = payload.observed_name
    identity.observed_at = datetime.now(UTC)
    identity.revision = 1 if is_new_identity else identity.revision + 1
    await db.flush()
    return identity


async def create_project_link_proposal(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: ProjectLinkProposalRequest,
) -> ProjectLinkProposal:
    """Persist an observation as a proposal; link creation remains explicit."""
    await require_active_device(db, ctx=ctx)
    await require_capability(
        db,
        ctx=ctx,
        organization_id=organization_id,
        capability="project.read",
        authorization_revision=payload.authorization_revision,
    )
    try:
        validate_public_project_data(payload.evidence, reject_identifiers=True)
    except ValueError as exc:
        raise ApiError(ErrorCategory.VALIDATION, "link proposal evidence is not public") from exc
    await _validate_link_targets(
        db,
        organization_id=organization_id,
        payload=ProjectLinkPlanRequest(
            local_project_id=payload.local_project_id,
            remote_project_id=payload.remote_project_id,
            provider_project_id=payload.provider_project_id,
            local_revision="proposal",
            remote_revision="proposal",
            authorization_revision="proposal",
            idempotency_key="proposal-evidence",
        ),
    )
    proposal = ProjectLinkProposal(
        id=new_id("proposal"),
        organization_id=organization_id,
        local_project_id=payload.local_project_id,
        remote_project_id=payload.remote_project_id,
        provider_project_id=payload.provider_project_id,
        evidence=dict(payload.evidence),
    )
    db.add(proposal)
    await db.flush()
    return proposal


async def _validate_link_targets(
    db: AsyncSession, *, organization_id: str, payload: ProjectLinkPlanRequest
) -> None:
    remote = await db.scalar(
        select(ProjectIdentity).where(
            ProjectIdentity.id == payload.remote_project_id,
            ProjectIdentity.organization_id == organization_id,
            ProjectIdentity.namespace == "remote",
            ProjectIdentity.state == "active",
        )
    )
    if remote is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "remote project not found")
    if payload.provider_project_id is not None:
        provider = await db.scalar(
            select(ProjectIdentity).where(
                ProjectIdentity.id == payload.provider_project_id,
                ProjectIdentity.organization_id == organization_id,
                ProjectIdentity.namespace == "provider",
                ProjectIdentity.state == "active",
            )
        )
        if provider is None:
            raise ApiError(ErrorCategory.NOT_FOUND, "provider project not found")


async def read_project_link_plan(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, plan_id: str
) -> ProjectLinkPlanResponse:
    """Read a plan only through the selected organization's membership."""
    await require_membership(db, ctx=ctx, organization_id=organization_id)
    result = await db.execute(
        select(ProjectLinkPlan).where(
            ProjectLinkPlan.id == plan_id,
            ProjectLinkPlan.organization_id == organization_id,
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "project link plan not found")
    return link_plan_body(plan)


async def create_project_unlink_plan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: ProjectUnlinkPlanRequest,
) -> ProjectUnlinkPlanResponse:
    """Create or replay the server-authored unlink decision."""
    device = await require_active_device(db, ctx=ctx)
    link = await _link_for_member(
        db, ctx=ctx, organization_id=organization_id, link_id=payload.link_id
    )
    await require_capability(
        db,
        ctx=ctx,
        organization_id=organization_id,
        capability="project.unlink",
        authorization_revision=payload.authorization_revision,
    )
    replay = await db.scalar(
        select(ProjectUnlinkPlan).where(
            ProjectUnlinkPlan.organization_id == organization_id,
            ProjectUnlinkPlan.idempotency_key == payload.idempotency_key,
        )
    )
    if replay is not None:
        if (
            replay.link_id != payload.link_id
            or replay.expected_link_revision != payload.expected_link_revision
            or replay.actor_account_id != ctx.account_id
        ):
            raise ApiError(ErrorCategory.CONFLICT, "idempotency key belongs to another unlink plan")
        return unlink_plan_body(replay)
    if link.state not in {"linked", "conflict"}:
        raise ApiError(ErrorCategory.PRECONDITION, "project link is already unlinked")
    if link.revision != payload.expected_link_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "project link revision is stale")

    values = {
        "organization_id": organization_id,
        "link_id": link.id,
        "actor_account_id": ctx.account_id,
        "device_id": device.id,
        "local_project_id": link.local_project_id,
        "remote_project_id": link.remote_project_id,
        "provider_project_id": link.provider_project_id,
        "expected_link_revision": link.revision,
        "local_revision": link.local_revision,
        "remote_revision": link.remote_revision,
        "provider_revision": link.provider_revision,
        "authorization_revision": payload.authorization_revision,
    }
    expires_at = datetime.now(UTC) + timedelta(minutes=15)
    digest = _plan_digest({**values, "expires_at": _timestamp(expires_at)})
    plan = ProjectUnlinkPlan(
        id=new_id("unlink_plan"),
        **values,
        idempotency_key=payload.idempotency_key,
        plan_digest=digest,
        expires_at=expires_at,
    )
    db.add(plan)
    await db.flush()
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.unlink_planned",
        target_table="project_unlink_plan",
        target_id=plan.id,
        payload={"organization_id": organization_id, "link_id": link.id},
    )
    return unlink_plan_body(plan)


async def read_project_unlink_plan(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, plan_id: str
) -> ProjectUnlinkPlanResponse:
    """Read a plan only through the selected organization's membership."""
    await require_membership(db, ctx=ctx, organization_id=organization_id)
    plan = await db.scalar(
        select(ProjectUnlinkPlan).where(
            ProjectUnlinkPlan.id == plan_id,
            ProjectUnlinkPlan.organization_id == organization_id,
        )
    )
    if plan is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "project unlink plan not found")
    return unlink_plan_body(plan)


async def create_project_link(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: ProjectLinkRequest,
) -> ProjectLinkResponse:
    """Confirm one exact server-authored link plan."""
    device = await require_active_device(db, ctx=ctx)
    await require_capability(
        db,
        ctx=ctx,
        organization_id=organization_id,
        capability="project.link",
        authorization_revision=payload.authorization_revision,
    )
    replay = await db.scalar(
        select(ProjectLink).where(ProjectLink.create_idempotency_key == payload.idempotency_key)
    )
    if replay is not None:
        if (
            replay.organization_id != organization_id
            or replay.plan_id != payload.plan_id
            or replay.plan_digest != payload.plan_digest
        ):
            raise ApiError(
                ErrorCategory.CONFLICT, "idempotency key belongs to another project link"
            )
        return link_body(replay)

    plan = await db.scalar(
        select(ProjectLinkPlan).where(ProjectLinkPlan.id == payload.plan_id).with_for_update()
    )
    if plan is None or plan.organization_id != organization_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "project link plan not found")
    if plan.actor_account_id != ctx.account_id or plan.device_id != device.id:
        raise ApiError(ErrorCategory.PERMISSION, "project link plan belongs to another device")
    if plan.plan_digest != payload.plan_digest:
        raise ApiError(ErrorCategory.PRECONDITION, "project link plan digest is stale")
    if plan.plan_digest != _plan_digest(
        {
            "organization_id": plan.organization_id,
            "actor_account_id": plan.actor_account_id,
            "device_id": plan.device_id,
            "local_project_id": plan.local_project_id,
            "remote_project_id": plan.remote_project_id,
            "provider_project_id": plan.provider_project_id,
            "local_revision": plan.local_revision,
            "remote_revision": plan.remote_revision,
            "provider_revision": plan.provider_revision,
            "authorization_revision": plan.authorization_revision,
            "expires_at": _timestamp(plan.expires_at),
        }
    ):
        raise ApiError(ErrorCategory.PRECONDITION, "project link plan digest is stale")
    if plan.authorization_revision != payload.authorization_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "project link plan authorization is stale")
    expires_at = plan.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if plan.state != "ready" or expires_at <= datetime.now(UTC):
        raise ApiError(ErrorCategory.PRECONDITION, "project link plan is no longer active")

    existing = await db.scalar(
        select(ProjectLink).where(
            ProjectLink.organization_id == organization_id,
            ProjectLink.local_project_id == plan.local_project_id,
            ProjectLink.state.in_(("linked", "conflict")),
        )
    )
    if existing is not None:
        raise ApiError(ErrorCategory.CONFLICT, "local project is already linked")

    link = ProjectLink(
        id=new_id("project_link"),
        plan_id=plan.id,
        plan_digest=plan.plan_digest,
        organization_id=organization_id,
        actor_account_id=ctx.account_id,
        device_id=device.id,
        local_project_id=plan.local_project_id,
        remote_project_id=plan.remote_project_id,
        provider_project_id=plan.provider_project_id,
        state="linked",
        local_revision=plan.local_revision,
        remote_revision=plan.remote_revision,
        provider_revision=plan.provider_revision,
        create_idempotency_key=payload.idempotency_key,
    )
    db.add(link)
    await db.flush()
    plan.state = "applied"
    plan.link_id = link.id
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=link.organization_id,
        action="project.link_created",
        target_table="project_link",
        target_id=link.id,
        payload={
            "organization_id": organization_id,
            "local_project_id": link.local_project_id,
            "remote_project_id": link.remote_project_id,
        },
    )
    return link_body(link)


async def read_project_link(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, link_id: str
) -> ProjectLinkResponse:
    """Read one link after the same tenant check used for mutations."""
    return link_body(
        await _link_for_member(db, ctx=ctx, organization_id=organization_id, link_id=link_id)
    )


async def unlink_project_link(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    link_id: str,
    payload: ProjectUnlinkRequest,
) -> ProjectLinkResponse:
    """Confirm one exact unlink plan, retaining identities and history."""
    device = await require_active_device(db, ctx=ctx)
    plan = await db.scalar(
        select(ProjectUnlinkPlan).where(ProjectUnlinkPlan.id == payload.plan_id).with_for_update()
    )
    if plan is None or plan.link_id != link_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "project unlink plan not found")
    link = await _link_for_member(
        db,
        ctx=ctx,
        organization_id=organization_id,
        link_id=link_id,
        for_update=True,
    )
    if link.organization_id != plan.organization_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "project unlink plan not found")
    await require_capability(
        db,
        ctx=ctx,
        organization_id=link.organization_id,
        capability="project.unlink",
        authorization_revision=payload.authorization_revision,
    )
    if plan.actor_account_id != ctx.account_id or plan.device_id != device.id:
        raise ApiError(ErrorCategory.PERMISSION, "project unlink plan belongs to another device")
    if plan.plan_digest != payload.plan_digest:
        raise ApiError(ErrorCategory.PRECONDITION, "project unlink plan digest is stale")
    if plan.plan_digest != _plan_digest(
        {
            "organization_id": plan.organization_id,
            "link_id": plan.link_id,
            "actor_account_id": plan.actor_account_id,
            "device_id": plan.device_id,
            "local_project_id": plan.local_project_id,
            "remote_project_id": plan.remote_project_id,
            "provider_project_id": plan.provider_project_id,
            "expected_link_revision": plan.expected_link_revision,
            "local_revision": plan.local_revision,
            "remote_revision": plan.remote_revision,
            "provider_revision": plan.provider_revision,
            "authorization_revision": plan.authorization_revision,
            "expires_at": _timestamp(plan.expires_at),
        }
    ):
        raise ApiError(ErrorCategory.PRECONDITION, "project unlink plan digest is stale")
    if plan.authorization_revision != payload.authorization_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "project unlink plan authorization is stale")
    if plan.state == "applied" and plan.confirmation_idempotency_key == payload.idempotency_key:
        return link_body(link)
    expires_at = plan.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if plan.state != "ready" or expires_at <= datetime.now(UTC):
        raise ApiError(ErrorCategory.PRECONDITION, "project unlink plan is no longer active")
    if link.state not in {"linked", "conflict"}:
        raise ApiError(ErrorCategory.PRECONDITION, "project link is already unlinked")
    if (
        link.revision != plan.expected_link_revision
        or link.local_revision != plan.local_revision
        or link.remote_revision != plan.remote_revision
        or link.provider_revision != plan.provider_revision
    ):
        raise ApiError(ErrorCategory.PRECONDITION, "project link revision is stale")
    link.state = "unlinked"
    link.revision += 1
    link.unlink_idempotency_key = payload.idempotency_key
    plan.state = "applied"
    plan.confirmation_idempotency_key = payload.idempotency_key
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=link.organization_id,
        action="project.link_unlinked",
        target_table="project_link",
        target_id=link.id,
        payload={
            "organization_id": link.organization_id,
            "link_revision": link.revision,
            "unlink_plan_id": plan.id,
        },
    )
    return link_body(link)


def _project_revision_document(
    payload: ProjectRevisionPushRequest, *, remote_project_id: str
) -> dict[str, object]:
    """Return the signed, path-free project revision body."""
    return {
        "schema_version": 1,
        "remote_project_id": remote_project_id,
        "parent_revision_ids": list(payload.parent_revision_ids),
        "operation": payload.operation,
        "projection": dict(payload.projection),
    }


async def _project_revision(
    db: AsyncSession, *, organization_id: str, remote_project_id: str, revision_id: str
) -> ProjectRevision | None:
    return await db.get(ProjectRevision, (organization_id, remote_project_id, revision_id))


async def _project_parents(
    db: AsyncSession, *, organization_id: str, remote_project_id: str, revision_id: str
) -> list[str]:
    row = await _project_revision(
        db,
        organization_id=organization_id,
        remote_project_id=remote_project_id,
        revision_id=revision_id,
    )
    return list(row.parent_revision_ids) if row is not None else []


async def _project_is_ancestor(
    db: AsyncSession,
    *,
    organization_id: str,
    remote_project_id: str,
    ancestor: str,
    descendant: str,
) -> bool:
    if ancestor == descendant:
        return True
    seen: set[str] = set()
    frontier = [descendant]
    for _ in range(256):
        if not frontier:
            return False
        next_frontier: list[str] = []
        for revision_id in frontier:
            if revision_id in seen:
                continue
            seen.add(revision_id)
            parents = await _project_parents(
                db,
                organization_id=organization_id,
                remote_project_id=remote_project_id,
                revision_id=revision_id,
            )
            if ancestor in parents:
                return True
            next_frontier.extend(parent for parent in parents if parent not in seen)
        frontier = next_frontier
    return False


async def _project_common_ancestor(
    db: AsyncSession,
    *,
    organization_id: str,
    remote_project_id: str,
    left: str,
    right: str,
) -> str | None:
    """Walk persisted parent links; never synthesize an ancestor identifier."""
    if left == right:
        return left
    left_seen: set[str] = {left}
    right_seen: set[str] = {right}
    left_frontier = [left]
    right_frontier = [right]
    for _ in range(256):
        if not left_frontier and not right_frontier:
            return None
        next_left: list[str] = []
        for revision_id in left_frontier:
            for parent in await _project_parents(
                db,
                organization_id=organization_id,
                remote_project_id=remote_project_id,
                revision_id=revision_id,
            ):
                if parent in right_seen:
                    return parent
                if parent not in left_seen:
                    left_seen.add(parent)
                    next_left.append(parent)
        left_frontier = next_left
        next_right: list[str] = []
        for revision_id in right_frontier:
            for parent in await _project_parents(
                db,
                organization_id=organization_id,
                remote_project_id=remote_project_id,
                revision_id=revision_id,
            ):
                if parent in left_seen:
                    return parent
                if parent not in right_seen:
                    right_seen.add(parent)
                    next_right.append(parent)
        right_frontier = next_right
    return None


def _project_revision_receipt_body(
    *,
    event_id: str,
    state: str,
    revision_id: str | None,
    server_head_revision_id: str | None,
    client_head_revision_id: str | None,
    common_ancestor_revision_id: str | None,
    error_code: str | None,
) -> ProjectRevisionPushResponse:
    return ProjectRevisionPushResponse(
        receipt=ProjectRevisionReceiptContract(
            event_id=event_id,
            state=state,  # type: ignore[arg-type]
            revision_id=revision_id,
            server_head_revision_id=server_head_revision_id,
            client_head_revision_id=client_head_revision_id,
            common_ancestor_revision_id=common_ancestor_revision_id,
            error_code=error_code,
        )
    )


async def push_project_revision(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    link_id: str,
    payload: ProjectRevisionPushRequest,
    resolution: bool = False,
) -> ProjectRevisionPushResponse:
    """Store one project revision, accepting only initial/fast-forward pushes."""
    device = await require_active_device(db, ctx=ctx)
    link = _require_linked(
        await _link_for_member(
            db,
            ctx=ctx,
            organization_id=organization_id,
            link_id=link_id,
            for_update=True,
        ),
        allow_conflict=resolution,
    )
    await require_capability(
        db,
        ctx=ctx,
        organization_id=link.organization_id,
        capability="project.update",
        authorization_revision=payload.authorization_revision,
    )
    remote_project_id = link.remote_project_id
    fingerprint = digest_canonical(
        "ai-stp:revision:v1", cast(JsonValue, payload.model_dump(mode="json"))
    )
    existing_receipt = await db.scalar(
        select(ProjectRevisionReceiptRow).where(
            ProjectRevisionReceiptRow.organization_id == link.organization_id,
            ProjectRevisionReceiptRow.remote_project_id == remote_project_id,
            ProjectRevisionReceiptRow.idempotency_key == payload.idempotency_key,
        )
    )
    if existing_receipt is not None:
        if existing_receipt.request_fingerprint != fingerprint:
            raise ApiError(ErrorCategory.CONFLICT, "idempotency key belongs to another revision")
        return ProjectRevisionPushResponse.model_validate(existing_receipt.response_body)

    expected_content = digest_canonical("ai-stp:revision:v1", cast(JsonValue, payload.projection))
    expected_revision = digest_canonical(
        "ai-stp:revision:v1",
        cast(JsonValue, _project_revision_document(payload, remote_project_id=remote_project_id)),
    )
    declared_project = payload.projection.get("remote_project_id")
    if declared_project is not None and declared_project != remote_project_id:
        raise ApiError(ErrorCategory.PERMISSION, "project projection names another remote project")
    if payload.content_digest != expected_content or payload.revision_id != expected_revision:
        raise ApiError(ErrorCategory.VALIDATION, "project revision digest does not match content")

    head = await db.scalar(
        select(ProjectRevisionHead)
        .where(
            ProjectRevisionHead.organization_id == link.organization_id,
            ProjectRevisionHead.remote_project_id == remote_project_id,
        )
        .with_for_update()
    )
    server_head = head.revision_id if head is not None else None
    for parent in payload.parent_revision_ids:
        if (
            await _project_revision(
                db,
                organization_id=link.organization_id,
                remote_project_id=remote_project_id,
                revision_id=parent,
            )
            is None
        ):
            raise ApiError(ErrorCategory.VALIDATION, "project revision parent is unknown")
    if payload.expected_head_revision_id is not None and (
        await _project_revision(
            db,
            organization_id=link.organization_id,
            remote_project_id=remote_project_id,
            revision_id=payload.expected_head_revision_id,
        )
        is None
    ):
        raise ApiError(ErrorCategory.PRECONDITION, "client project head is unknown")

    if resolution:
        conflict_pair = {
            link.conflict_server_revision,
            link.conflict_client_revision,
        }
        if link.state != "conflict" or None in conflict_pair:
            raise ApiError(
                ErrorCategory.PRECONDITION, "project link is not in a resolvable conflict"
            )
        if server_head != link.conflict_server_revision:
            raise ApiError(ErrorCategory.PRECONDITION, "project conflict is stale")
        if payload.expected_head_revision_id != link.conflict_server_revision:
            raise ApiError(ErrorCategory.PRECONDITION, "project conflict server head is stale")
        if set(payload.parent_revision_ids) != conflict_pair:
            raise ApiError(ErrorCategory.PRECONDITION, "project conflict parents are stale")

    if resolution and len(payload.parent_revision_ids) != 2:
        raise ApiError(ErrorCategory.VALIDATION, "resolution requires exactly two parents")

    revision = ProjectRevision(
        organization_id=link.organization_id,
        remote_project_id=remote_project_id,
        revision_id=payload.revision_id,
        parent_revision_ids=list(payload.parent_revision_ids),
        operation=payload.operation,
        content_digest=payload.content_digest,
        projection=dict(payload.projection),
        actor_account_id=ctx.account_id,
        device_id=device.id,
        event_id=payload.event_id,
    )
    db.add(revision)
    fast_forward = (
        server_head is None
        and not payload.parent_revision_ids
        and payload.expected_head_revision_id is None
    ) or (
        server_head is not None
        and payload.expected_head_revision_id == server_head
        and server_head in payload.parent_revision_ids
    )
    if resolution and (server_head is None or payload.expected_head_revision_id != server_head):
        raise ApiError(ErrorCategory.PRECONDITION, "project head is stale")
    if not fast_forward:
        common = await _project_common_ancestor(
            db,
            organization_id=link.organization_id,
            remote_project_id=remote_project_id,
            left=server_head or payload.revision_id,
            right=payload.expected_head_revision_id or payload.revision_id,
        )
        body = _project_revision_receipt_body(
            event_id=payload.event_id,
            state="conflict",
            revision_id=payload.revision_id,
            server_head_revision_id=server_head,
            client_head_revision_id=payload.expected_head_revision_id,
            common_ancestor_revision_id=common,
            error_code="divergent_heads",
        )
        link.state = "conflict"
        link.conflict_server_revision = server_head
        link.conflict_client_revision = payload.revision_id
        link.conflict_common_ancestor = common
    else:
        if head is None:
            head = ProjectRevisionHead(
                organization_id=link.organization_id,
                remote_project_id=remote_project_id,
                revision_id=payload.revision_id,
            )
            db.add(head)
        else:
            head.revision_id = payload.revision_id
        link.state = "linked"
        link.remote_revision = payload.revision_id
        link.conflict_server_revision = None
        link.conflict_client_revision = None
        link.conflict_common_ancestor = None
        link.revision += 1
        body = _project_revision_receipt_body(
            event_id=payload.event_id,
            state="accepted",
            revision_id=payload.revision_id,
            server_head_revision_id=payload.revision_id,
            client_head_revision_id=payload.expected_head_revision_id,
            common_ancestor_revision_id=None,
            error_code=None,
        )
    db.add(
        ProjectRevisionReceiptRow(
            organization_id=link.organization_id,
            remote_project_id=remote_project_id,
            idempotency_key=payload.idempotency_key,
            request_fingerprint=fingerprint,
            response_body=body.model_dump(mode="json"),
        )
    )
    await db.flush()
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=link.organization_id,
        action="project.revision_pushed",
        target_table="project_revision",
        target_id=payload.revision_id,
        payload={
            "organization_id": link.organization_id,
            "remote_project_id": remote_project_id,
            "state": body.receipt.state,
        },
    )
    return body


async def resolve_project_conflict(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    link_id: str,
    payload: ProjectConflictResolutionRequest,
) -> ProjectRevisionPushResponse:
    """Create a two-parent revision through the same idempotent ledger path."""
    return await push_project_revision(
        db,
        ctx=ctx,
        organization_id=organization_id,
        link_id=link_id,
        payload=payload,
        resolution=True,
    )


async def pull_project_revisions(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    link_id: str,
    authorization_revision: str,
) -> ProjectRevisionPullResponse:
    """Return only the selected tenant's redacted project history."""
    link = _require_linked(
        await _link_for_member(db, ctx=ctx, organization_id=organization_id, link_id=link_id)
    )
    await require_capability(
        db,
        ctx=ctx,
        organization_id=link.organization_id,
        capability="project.read",
        authorization_revision=authorization_revision,
    )
    head = await db.scalar(
        select(ProjectRevisionHead).where(
            ProjectRevisionHead.organization_id == link.organization_id,
            ProjectRevisionHead.remote_project_id == link.remote_project_id,
        )
    )
    rows = (
        (
            await db.execute(
                select(ProjectRevision)
                .where(
                    ProjectRevision.organization_id == link.organization_id,
                    ProjectRevision.remote_project_id == link.remote_project_id,
                )
                .order_by(ProjectRevision.created_at.asc(), ProjectRevision.revision_id.asc())
                .limit(256)
            )
        )
        .scalars()
        .all()
    )
    return ProjectRevisionPullResponse(
        head_revision_id=head.revision_id if head is not None else None,
        items=[
            ProjectRevisionView(
                revision_id=row.revision_id,
                parent_revision_ids=row.parent_revision_ids,
                operation=row.operation,  # type: ignore[arg-type]
                content_digest=row.content_digest,
                projection=row.projection,
                actor_account_id=row.actor_account_id,
                device_id=row.device_id,
                created_at=_timestamp(row.created_at),
            )
            for row in rows
        ],
    )


async def create_sync_plan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: ProjectSyncPlanRequest,
) -> ProjectSyncPlanResponse:
    """Persist a deterministic sync decision without changing either endpoint."""
    device = await require_active_device(db, ctx=ctx)
    link = _require_linked(
        await _link_for_member(
            db,
            ctx=ctx,
            organization_id=organization_id,
            link_id=payload.link_id,
        )
    )
    await require_capability(
        db,
        ctx=ctx,
        organization_id=link.organization_id,
        capability="project.read",
        authorization_revision=payload.authorization_revision,
    )
    replay = await db.scalar(
        select(ProjectSyncPlan).where(
            ProjectSyncPlan.link_id == link.id,
            ProjectSyncPlan.idempotency_key == payload.idempotency_key,
        )
    )
    if replay is not None:
        return sync_plan_body(replay)
    if link.revision != payload.expected_link_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "project link revision is stale")

    local_changed = payload.local_revision != link.local_revision
    remote_changed = payload.remote_revision != link.remote_revision
    provider_changed = payload.provider_revision != link.provider_revision
    remote = await db.scalar(
        select(ProjectIdentity).where(
            ProjectIdentity.id == link.remote_project_id,
            ProjectIdentity.organization_id == organization_id,
            ProjectIdentity.namespace == "remote",
        )
    )
    provider = (
        await db.scalar(
            select(ProjectIdentity).where(
                ProjectIdentity.id == link.provider_project_id,
                ProjectIdentity.organization_id == organization_id,
                ProjectIdentity.namespace == "provider",
            )
        )
        if link.provider_project_id is not None
        else None
    )
    if remote is None or remote.state != "active":
        state, action, conflict = "conflict", "merge_required", "remote_missing"
    elif (
        (provider is None and link.provider_project_id is not None)
        or (provider is not None and provider.state != "active")
        or (provider_changed and not local_changed and not remote_changed)
    ):
        state, action, conflict = "conflict", "merge_required", "provider_mismatch"
    elif local_changed and remote_changed:
        local_known = await _project_revision(
            db,
            organization_id=link.organization_id,
            remote_project_id=link.remote_project_id,
            revision_id=payload.local_revision,
        )
        remote_known = await _project_revision(
            db,
            organization_id=link.organization_id,
            remote_project_id=link.remote_project_id,
            revision_id=payload.remote_revision,
        )
        if local_known is None or remote_known is None:
            raise ApiError(
                ErrorCategory.PRECONDITION, "project revision is not in the organization ledger"
            )
        if await _project_is_ancestor(
            db,
            organization_id=link.organization_id,
            remote_project_id=link.remote_project_id,
            ancestor=payload.local_revision,
            descendant=payload.remote_revision,
        ):
            state, action, conflict = "ready", "remote_to_local", None
        elif await _project_is_ancestor(
            db,
            organization_id=link.organization_id,
            remote_project_id=link.remote_project_id,
            ancestor=payload.remote_revision,
            descendant=payload.local_revision,
        ):
            state, action, conflict = "ready", "local_to_remote", None
        else:
            state, action, conflict = "conflict", "merge_required", "both_changed"
    elif local_changed:
        state, action, conflict = "ready", "local_to_remote", None
    elif remote_changed:
        state, action, conflict = "ready", "remote_to_local", None
    else:
        state, action, conflict = "ready", "noop", None

    values = {
        "link_id": link.id,
        "expected_link_revision": payload.expected_link_revision,
        "local_revision": payload.local_revision,
        "remote_revision": payload.remote_revision,
        "provider_revision": payload.provider_revision,
        "remote_identity_revision": remote.revision if remote is not None else None,
        "provider_identity_revision": provider.revision if provider is not None else None,
        "action": action,
    }
    common_ancestor = None
    if state == "conflict" and conflict == "both_changed":
        common_ancestor = await _project_common_ancestor(
            db,
            organization_id=link.organization_id,
            remote_project_id=link.remote_project_id,
            left=payload.local_revision,
            right=payload.remote_revision,
        )
    values["common_ancestor_revision"] = common_ancestor
    expires_at = datetime.now(UTC) + timedelta(minutes=15)
    digest = _plan_digest(
        {
            **values,
            "organization_id": organization_id,
            "actor_account_id": ctx.account_id,
            "device_id": device.id,
            "expires_at": _timestamp(expires_at),
        }
    )
    plan = ProjectSyncPlan(
        id=new_id("sync_plan"),
        link_id=link.id,
        actor_account_id=ctx.account_id,
        device_id=device.id,
        state=state,
        action=action,
        expected_link_revision=payload.expected_link_revision,
        local_revision=payload.local_revision,
        remote_revision=payload.remote_revision,
        provider_revision=payload.provider_revision,
        remote_identity_revision=remote.revision if remote is not None else 0,
        provider_identity_revision=provider.revision if provider is not None else None,
        conflict_code=conflict,
        common_ancestor_revision=common_ancestor if state == "conflict" else None,
        idempotency_key=payload.idempotency_key,
        plan_digest=digest,
        expires_at=expires_at,
    )
    db.add(plan)
    await db.flush()
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.sync_planned",
        target_table="project_sync_plan",
        target_id=plan.id,
        payload={
            "organization_id": link.organization_id,
            "link_id": link.id,
            "state": plan.state,
            "action": plan.action,
            "conflict_code": plan.conflict_code,
        },
    )
    return sync_plan_body(plan)


def sync_plan_body(plan: ProjectSyncPlan) -> ProjectSyncPlanResponse:
    """Project a durable sync plan to the shared response contract."""
    return ProjectSyncPlanResponse(
        plan_id=plan.id,
        link_id=plan.link_id,
        state=plan.state,  # type: ignore[arg-type]
        action=plan.action,  # type: ignore[arg-type]
        expected_link_revision=plan.expected_link_revision,
        local_revision=plan.local_revision,
        remote_revision=plan.remote_revision,
        provider_revision=plan.provider_revision,
        remote_identity_revision=plan.remote_identity_revision,
        provider_identity_revision=plan.provider_identity_revision,
        conflict_code=plan.conflict_code,  # type: ignore[arg-type]
        common_ancestor_revision=plan.common_ancestor_revision,
        plan_digest=plan.plan_digest,
        expires_at=_timestamp(plan.expires_at),
    )


async def apply_sync_plan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    plan_id: str,
    link_id: str,
    payload: ProjectSyncApplyRequest,
) -> ProjectSyncPlanResponse:
    """Apply one exact ready plan and record an idempotent receipt."""
    await require_active_device(db, ctx=ctx)
    plan = await db.scalar(
        select(ProjectSyncPlan).where(ProjectSyncPlan.id == plan_id).with_for_update()
    )
    if plan is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "sync plan not found")
    if plan.link_id != link_id:
        raise ApiError(ErrorCategory.NOT_FOUND, "sync plan not found")
    link = _require_linked(
        await _link_for_member(
            db,
            ctx=ctx,
            organization_id=organization_id,
            link_id=plan.link_id,
            for_update=True,
        )
    )
    await require_capability(
        db,
        ctx=ctx,
        organization_id=link.organization_id,
        capability="project.update",
        authorization_revision=payload.authorization_revision,
    )
    if plan.apply_idempotency_key == payload.idempotency_key:
        return sync_plan_body(plan)
    if plan.apply_idempotency_key is not None:
        raise ApiError(ErrorCategory.CONFLICT, "sync plan was already applied")
    if plan.plan_digest != payload.plan_digest:
        raise ApiError(ErrorCategory.PRECONDITION, "sync plan digest is stale")
    expected_digest = _plan_digest(
        {
            "link_id": plan.link_id,
            "expected_link_revision": plan.expected_link_revision,
            "local_revision": plan.local_revision,
            "remote_revision": plan.remote_revision,
            "provider_revision": plan.provider_revision,
            "remote_identity_revision": plan.remote_identity_revision,
            "provider_identity_revision": plan.provider_identity_revision,
            "conflict_code": plan.conflict_code,
            "common_ancestor_revision": plan.common_ancestor_revision,
            "action": plan.action,
            "organization_id": organization_id,
            "actor_account_id": plan.actor_account_id,
            "device_id": plan.device_id,
            "expires_at": _timestamp(plan.expires_at),
        }
    )
    if plan.plan_digest != expected_digest:
        raise ApiError(ErrorCategory.PRECONDITION, "sync plan digest is stale")
    expires_at = plan.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise ApiError(ErrorCategory.PRECONDITION, "sync plan has expired")
    if plan.state != "ready" or plan.action == "merge_required":
        raise ApiError(ErrorCategory.CONFLICT, "sync plan requires explicit conflict resolution")
    if (
        link.revision != payload.expected_link_revision
        or link.revision != plan.expected_link_revision
    ):
        raise ApiError(ErrorCategory.PRECONDITION, "project link revision is stale")
    remote = await db.scalar(
        select(ProjectIdentity)
        .where(ProjectIdentity.id == link.remote_project_id)
        .where(ProjectIdentity.organization_id == organization_id)
        .where(ProjectIdentity.namespace == "remote")
        .with_for_update()
    )
    provider = (
        await db.scalar(
            select(ProjectIdentity)
            .where(ProjectIdentity.id == link.provider_project_id)
            .where(ProjectIdentity.organization_id == organization_id)
            .where(ProjectIdentity.namespace == "provider")
            .with_for_update()
        )
        if link.provider_project_id is not None
        else None
    )
    if (
        remote is None
        or remote.state != "active"
        or remote.revision != plan.remote_identity_revision
        or (link.provider_project_id is not None and provider is None)
        or (provider is not None and provider.state != "active")
        or (provider is not None and provider.revision != plan.provider_identity_revision)
    ):
        raise ApiError(ErrorCategory.PRECONDITION, "project identity is stale")
    head = await db.scalar(
        select(ProjectRevisionHead)
        .where(
            ProjectRevisionHead.organization_id == link.organization_id,
            ProjectRevisionHead.remote_project_id == link.remote_project_id,
        )
        .with_for_update()
    )
    current_remote_revision = head.revision_id if head is not None else "initial"
    if current_remote_revision != plan.remote_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "project revision head is stale")
    link.local_revision = plan.local_revision
    link.remote_revision = plan.remote_revision
    link.provider_revision = plan.provider_revision
    link.revision += 1
    if plan.action in {"local_to_remote", "remote_to_local"}:
        selected_head = (
            plan.local_revision if plan.action == "local_to_remote" else plan.remote_revision
        )
        head = await db.scalar(
            select(ProjectRevisionHead)
            .where(
                ProjectRevisionHead.organization_id == link.organization_id,
                ProjectRevisionHead.remote_project_id == link.remote_project_id,
            )
            .with_for_update()
        )
        if head is None:
            head = ProjectRevisionHead(
                organization_id=link.organization_id,
                remote_project_id=link.remote_project_id,
                revision_id=selected_head,
            )
            db.add(head)
        else:
            head.revision_id = selected_head
    plan.state = "applied"
    plan.apply_idempotency_key = payload.idempotency_key
    plan.result = {"link_revision": link.revision, "action": plan.action}
    await db.flush()
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.sync_applied",
        target_table="project_sync_plan",
        target_id=plan.id,
        payload={
            "organization_id": link.organization_id,
            "link_id": link.id,
            "link_revision": link.revision,
            "action": plan.action,
        },
    )
    return sync_plan_body(plan)
