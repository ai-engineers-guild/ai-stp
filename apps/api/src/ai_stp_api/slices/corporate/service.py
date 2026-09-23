"""Corporate bootstrap, authorization, projects, and audit scenarios."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.auth.domain import normalize_email
from ai_stp_contracts.context import context_authorization_revision
from ai_stp_contracts.corporate import (
    CorporateAuditEntry,
    CorporateAuditExport,
    CorporateAuditList,
    CorporateBinding,
    CorporateBindingList,
    CorporateBindingRequest,
    CorporateBindingUpdateRequest,
    CorporateBootstrapRequest,
    CorporateCatalogAssignment,
    CorporateContext,
    CorporateDeleteRequest,
    CorporateDeleteResult,
    CorporateJobTitleCreateRequest,
    CorporateJobTitleList,
    CorporateJobTitleUpdateRequest,
    CorporateJobTitleView,
    CorporateMember,
    CorporateMemberCreateRequest,
    CorporateMemberList,
    CorporateMembershipAssignment,
    CorporateMembershipAssignmentRequest,
    CorporateMemberUpdateRequest,
    CorporateOrganization,
    CorporateProjectCreateRequest,
    CorporateProjectLifecycleRequest,
    CorporateProjectList,
    CorporateProjectRepository,
    CorporateProjectUpdateRequest,
    CorporateProjectView,
    CorporateRoleCreateRequest,
    CorporateRoleList,
    CorporateRoleUpdateRequest,
    CorporateRoleView,
    CorporateServicePrincipalCreateRequest,
    CorporateServicePrincipalList,
    CorporateServicePrincipalUpdateRequest,
    CorporateServicePrincipalView,
    CorporateState,
    CorporateTeamCatalogObject,
    CorporateTeamCreateRequest,
    CorporateTeamList,
    CorporateTeamUpdateRequest,
    CorporateTeamView,
    ProjectLifecycle,
    ProjectState,
    ScopeKind,
)
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.catalog_ownership_models import (
    CorporateCatalogOwnership as CorporateCatalogOwnershipRow,
)
from ai_stp_platform.catalog_read import get_visible_metadata
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.models import Account, AuditEvent
from ai_stp_platform.organization_models import (
    CorporateBootstrapReceipt,
    CorporateJobTitle,
    CorporateMutationReceipt,
    CorporateProject,
    CorporateProjectMember,
    CorporateProvisionedIdentity,
    CorporateRoleBinding,
    CorporateRolePermission,
    CorporateServicePrincipal,
    CorporateTeam,
    CorporateTeamMember,
    Organization,
    OrganizationMembership,
    ProjectIdentity,
    ProjectLink,
)
from ai_stp_platform.organization_models import (
    CorporateCatalogAssignment as CorporateCatalogAssignmentRow,
)
from ai_stp_platform.organization_models import (
    CorporateCatalogMaintainer as CorporateCatalogMaintainerRow,
)
from ai_stp_platform.organization_models import (
    CorporateRole as CorporateRoleRow,
)
from ai_stp_platform.technology_models import (
    ProjectTeamRelation,
    ProjectTechnologyRelation,
    Technology,
    TechnologyTeamResponsibility,
)
from ai_stp_platform.tenant_scope import set_tenant_scope

TECHNOLOGY_PERMISSIONS = frozenset(
    {
        "category.create",
        "category.read",
        "category.update",
        "category.delete",
        "category.list",
        "technology.create",
        "technology.read",
        "technology.update",
        "technology.delete",
        "technology.list",
        "technology.approve",
        "technology.merge",
        "technology.responsibility",
        "landscape.read",
        "landscape.manage",
        "technology.scan.publish",
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "superadmin": frozenset(
        {
            "organization.read",
            "organization.manage",
            "member.create",
            "member.read",
            "member.update",
            "member.delete",
            "member.list",
            "member.manage",
            "binding.create",
            "binding.read",
            "binding.update",
            "binding.delete",
            "binding.list",
            "project.create",
            "project.read",
            "project.update",
            "project.delete",
            "project.list",
            "team.create",
            "team.read",
            "team.update",
            "team.delete",
            "team.list",
            "audit.read",
            "audit.list",
            "audit.export",
            "service_principal.manage",
            "service_principal.read",
            "service_principal.list",
            "service_principal.delete",
            "role.create",
            "role.read",
            "role.update",
            "role.delete",
            "role.list",
            "job_title.create",
            "job_title.read",
            "job_title.update",
            "job_title.list",
            "telemetry.write",
            "telemetry.read",
            "telemetry.list",
            "telemetry.export",
            "telemetry.manage",
            "telemetry.delete",
            "telemetry_usage.ingest",
            "telemetry_usage.read",
            "telemetry_usage.events",
            "telemetry_usage.export",
        }
    ),
    "lead": frozenset(
        {
            "organization.read",
            "member.read",
            "member.update",
            "member.delete",
            "project.read",
            "project.update",
            "project.list",
            "team.read",
            "team.update",
            "team.delete",
            "team.list",
            "telemetry.read",
            "telemetry_usage.ingest",
            "telemetry_usage.read",
        }
    ),
    "staff": frozenset(
        {
            "organization.read",
            "project.read",
            "project.list",
            "team.read",
            "team.list",
            "telemetry_usage.ingest",
        }
    ),
}

RELATION_PERMISSIONS = frozenset(
    f"{resource}.{action}"
    for resource in ("project_team", "project_technology", "technology_team", "technology_decision")
    for action in ("create", "read", "update", "delete", "list")
)
GOVERNANCE_PERMISSIONS = frozenset(
    {
        "catalog_object.read",
        "catalog_object.edit",
        "catalog_object.delete",
        "catalog_object.publish",
        "catalog_object.verify",
        "catalog_object.assign",
        "catalog_object.ownership_transfer",
        "catalog_object.maintainer",
        "catalog_object.lifecycle",
        "catalog_object.audit",
        "catalog_object.explain",
    }
)
ROLE_PERMISSIONS["superadmin"] |= (
    TECHNOLOGY_PERMISSIONS | RELATION_PERMISSIONS | GOVERNANCE_PERMISSIONS
)
ROLE_PERMISSIONS["lead"] |= {"catalog_object.read", "catalog_object.assign"}
ROLE_PERMISSIONS["staff"] |= {"catalog_object.read"}

_ROLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_BUILT_IN_ROLES: frozenset[str] = frozenset(ROLE_PERMISSIONS)
KNOWN_PERMISSIONS: frozenset[str] = frozenset(
    permission for permissions in ROLE_PERMISSIONS.values() for permission in permissions
)


def mutation_fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def organization_view(row: Organization) -> CorporateOrganization:
    return CorporateOrganization(
        organization_id=row.id,
        display_name=row.display_name,
        state=cast(CorporateState, row.state),
        authorization_revision=row.policy_revision,
    )


def member_view(
    row: OrganizationMembership, account: Account, job_title_name: str | None = None
) -> CorporateMember:
    return CorporateMember(
        account_id=row.account_id,
        display_name=row.display_name if row.display_name is not None else account.display_name,
        role=row.role,
        state=cast(CorporateState, row.state),
        revision=row.revision,
        job_title_id=row.job_title_id,
        job_title_name=job_title_name,
    )


def _normalize_job_title(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def job_title_view(row: CorporateJobTitle) -> CorporateJobTitleView:
    return CorporateJobTitleView(
        job_title_id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        normalized_name=row.normalized_name,
        description=row.description,
        state=cast(Literal["current", "retired"], row.state),
        revision=row.revision,
    )


def _binding_view(row: CorporateRoleBinding) -> CorporateBinding:
    return CorporateBinding(
        binding_id=row.id,
        principal_type=cast("Literal['user', 'service_principal']", row.principal_type),
        account_id=row.account_id,
        service_principal_id=row.service_principal_id,
        role=row.role,
        scope_kind=cast(ScopeKind, row.scope_kind),
        scope_id=row.scope_id,
        state=cast("Literal['active', 'revoked']", row.state),
        revision=row.revision,
    )


def _project_view(row: CorporateProject) -> CorporateProjectView:
    return CorporateProjectView(
        project_id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        state=cast(ProjectState, row.state),
        lifecycle=cast(ProjectLifecycle, row.lifecycle),
        restore_lifecycle=cast("Literal['active','deprecated']", row.restore_lifecycle),
        revision=row.revision,
        repository_activity_at=(
            format_timestamp(row.repository_activity_at.replace(tzinfo=UTC))
            if row.repository_activity_at is not None
            else None
        ),
        source_availability=cast(
            "Literal['unknown', 'available', 'unavailable']", row.source_availability
        ),
    )


async def team_lead_ids(db: AsyncSession, row: CorporateTeam) -> list[str]:
    """Read all active tenant-local leads before any presentation limit."""
    if row.state != "active":
        return []
    leads = list(
        (
            await db.scalars(
                select(CorporateRoleBinding.account_id)
                .join(
                    OrganizationMembership,
                    (OrganizationMembership.organization_id == CorporateRoleBinding.organization_id)
                    & (OrganizationMembership.account_id == CorporateRoleBinding.account_id),
                )
                .where(
                    CorporateRoleBinding.organization_id == row.organization_id,
                    CorporateRoleBinding.scope_kind == "team",
                    CorporateRoleBinding.scope_id == row.id,
                    CorporateRoleBinding.role == "lead",
                    CorporateRoleBinding.state == "active",
                    OrganizationMembership.state == "active",
                )
                .distinct()
                .order_by(CorporateRoleBinding.account_id)
            )
        ).all()
    )
    return [account_id for account_id in leads if account_id is not None]


async def team_view(
    db: AsyncSession, row: CorporateTeam, *, ctx: AuthContext, profile: bool = False
) -> CorporateTeamView:
    leads = await team_lead_ids(db, row)
    can_list = ctx.account_id in leads or await has_corporate_permission(
        db,
        organization_id=row.organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        permission="member.list",
        scope_kind="team",
        scope_id=row.id,
    )
    query = (
        select(OrganizationMembership, Account)
        .join(
            Account,
            Account.id == OrganizationMembership.account_id,
        )
        .where(
            OrganizationMembership.organization_id == row.organization_id,
            OrganizationMembership.account_id.in_(
                select(CorporateTeamMember.account_id).where(
                    CorporateTeamMember.organization_id == row.organization_id,
                    CorporateTeamMember.team_id == row.id,
                )
            )
            | OrganizationMembership.account_id.in_(leads),
        )
    )
    if not can_list:
        query = query.where(OrganizationMembership.account_id.in_([ctx.account_id, *leads]))
    pairs = (await db.execute(query.order_by(Account.id).limit(256))).all()
    assignments: list[CorporateCatalogAssignment] = []
    effective_assignments: list[CorporateCatalogAssignment] = []
    project_ids: list[str] = []
    technology_ids: list[str] = []
    effective_permissions: list[str] = []
    available_actions: list[str] = []
    governance_history: list[dict[str, object]] = []
    owned_catalog_objects: list[CorporateTeamCatalogObject] = []
    maintained_catalog_objects: list[CorporateTeamCatalogObject] = []
    if profile:
        assignment_rows = (
            await db.scalars(
                select(CorporateCatalogAssignmentRow)
                .where(
                    CorporateCatalogAssignmentRow.organization_id == row.organization_id,
                    CorporateCatalogAssignmentRow.team_id == row.id,
                    CorporateCatalogAssignmentRow.state == "current",
                )
                .order_by(CorporateCatalogAssignmentRow.id)
            )
        ).all()
        assignments = [
            CorporateCatalogAssignment(
                assignment_id=item.id,
                organization_id=item.organization_id,
                subject_kind="team",
                subject_id=row.id,
                object_kind=cast(Literal["setup", "component"], item.object_kind),
                stable_id=item.stable_id,
                version=item.version,
                state=cast(Literal["current", "retired"], item.state),
                revision=item.revision,
            )
            for item in assignment_rows
        ]
        owned_rows = (
            await db.scalars(
                select(CorporateCatalogOwnershipRow)
                .where(
                    CorporateCatalogOwnershipRow.organization_id == row.organization_id,
                    CorporateCatalogOwnershipRow.owner_kind == "team",
                    CorporateCatalogOwnershipRow.owner_id == row.id,
                )
                .order_by(CorporateCatalogOwnershipRow.stable_id)
            )
        ).all()
        owned_catalog_objects = [
            CorporateTeamCatalogObject(
                organization_id=item.organization_id,
                object_kind=cast(Literal["setup", "component"], item.object_kind),
                stable_id=item.stable_id,
                relation="owner",
                state="current",
                revision=item.revision,
            )
            for item in owned_rows
        ]
        maintained_rows = (
            await db.scalars(
                select(CorporateCatalogMaintainerRow)
                .where(
                    CorporateCatalogMaintainerRow.organization_id == row.organization_id,
                    CorporateCatalogMaintainerRow.subject_kind == "team",
                    CorporateCatalogMaintainerRow.subject_id == row.id,
                    CorporateCatalogMaintainerRow.state == "current",
                )
                .order_by(CorporateCatalogMaintainerRow.stable_id)
            )
        ).all()
        maintained_catalog_objects = [
            CorporateTeamCatalogObject(
                organization_id=item.organization_id,
                object_kind=cast(Literal["setup", "component"], item.object_kind),
                stable_id=item.stable_id,
                version=item.version,
                relation="maintainer",
                state=item.state,
                revision=item.revision,
            )
            for item in maintained_rows
        ]
        visible_member_ids = {
            member.account_id for member, _account in pairs if member.state == "active"
        }
        team_member_ids = set(
            (
                await db.scalars(
                    select(CorporateTeamMember.account_id).where(
                        CorporateTeamMember.organization_id == row.organization_id,
                        CorporateTeamMember.team_id == row.id,
                    )
                )
            ).all()
        )
        member_ids = sorted(visible_member_ids & team_member_ids)
        direct_rows = (
            await db.scalars(
                select(CorporateCatalogAssignmentRow)
                .where(
                    CorporateCatalogAssignmentRow.organization_id == row.organization_id,
                    CorporateCatalogAssignmentRow.account_id.in_(member_ids),
                    CorporateCatalogAssignmentRow.state == "current",
                )
                .order_by(CorporateCatalogAssignmentRow.id)
            )
        ).all()
        direct_assignments = [
            CorporateCatalogAssignment(
                assignment_id=item.id,
                organization_id=item.organization_id,
                subject_kind="employee",
                subject_id=item.account_id,
                object_kind=cast(Literal["setup", "component"], item.object_kind),
                stable_id=item.stable_id,
                version=item.version,
                state=cast(Literal["current", "retired"], item.state),
                revision=item.revision,
            )
            for item in direct_rows
            if item.account_id is not None
        ]
        derived_assignments = [
            item.model_copy(
                update={
                    "subject_kind": "employee",
                    "subject_id": member_id,
                    "source_team_id": row.id,
                }
            )
            for member_id in member_ids
            for item in assignments
        ]
        effective_assignments = [*direct_assignments, *derived_assignments]
        project_ids = list(
            (
                await db.scalars(
                    select(ProjectTeamRelation.project_id).where(
                        ProjectTeamRelation.organization_id == row.organization_id,
                        ProjectTeamRelation.team_id == row.id,
                        ProjectTeamRelation.state == "current",
                    )
                )
            ).all()
        )
        if project_ids:
            technology_ids = list(
                (
                    await db.scalars(
                        select(ProjectTechnologyRelation.technology_id)
                        .where(
                            ProjectTechnologyRelation.organization_id == row.organization_id,
                            ProjectTechnologyRelation.project_id.in_(project_ids),
                            ProjectTechnologyRelation.state == "current",
                        )
                        .distinct()
                    )
                ).all()
            )
        for permission in sorted(KNOWN_PERMISSIONS):
            if await has_corporate_permission(
                db,
                organization_id=row.organization_id,
                principal_type="user",
                principal_id=ctx.account_id,
                permission=permission,
                scope_kind="team",
                scope_id=row.id,
            ):
                effective_permissions.append(permission)
        available_actions = [
            action
            for action, permission in (
                ("team.update", "team.update"),
                ("team.delete", "team.delete"),
                ("assignment.manage", "catalog_object.assign"),
                ("maintainer.manage", "catalog_object.maintainer"),
                ("audit.explain", "catalog_object.explain"),
            )
            if permission in effective_permissions
        ]
        from ai_stp_api.slices.corporate.entity_profiles import can_edit_profile

        if await can_edit_profile(
            db,
            ctx=ctx,
            organization_id=row.organization_id,
            subject_kind="team",
            subject_id=row.id,
        ):
            available_actions.append("entity_profile.update")
        history_rows = list(
            (
                await db.scalars(
                    select(AuditEvent)
                    .where(
                        AuditEvent.organization_id == row.organization_id,
                        AuditEvent.target_table == "corporate_team",
                        AuditEvent.target_id == row.id,
                    )
                    .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                    .limit(64)
                )
            ).all()
        )
        governance_history = [
            {
                "action": item.action,
                "outcome": item.outcome,
                "actor_account_id": item.actor_account_id,
                "reason": item.reason,
                "created_at": format_timestamp(item.created_at),
            }
            for item in history_rows
        ]
    return CorporateTeamView(
        members=[member_view(member, account) for member, account in pairs],
        lead_account_ids=leads[:256],
        team_id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        state=cast("Literal['active', 'archived']", row.state),
        revision=row.revision,
        project_ids=project_ids,
        technology_ids=technology_ids,
        assignments=assignments,
        effective_assignments=effective_assignments,
        effective_permissions=effective_permissions,
        available_actions=available_actions,
        governance_history=governance_history,
        owned_catalog_objects=owned_catalog_objects,
        maintained_catalog_objects=maintained_catalog_objects,
    )


async def _role_view(db: AsyncSession, row: CorporateRoleRow) -> CorporateRoleView:
    permissions = list(
        (
            await db.scalars(
                select(CorporateRolePermission.permission)
                .where(
                    CorporateRolePermission.organization_id == row.organization_id,
                    CorporateRolePermission.role == row.name,
                )
                .order_by(CorporateRolePermission.permission)
            )
        ).all()
    )
    return CorporateRoleView(
        name=row.name,
        parent_role=row.parent_role,
        permissions=permissions,
        revision=row.revision,
    )


def _role_permissions(payload: list[str]) -> list[str]:
    permissions = sorted(set(payload))
    if any(permission not in KNOWN_PERMISSIONS for permission in permissions):
        raise ApiError(ErrorCategory.VALIDATION, "corporate permission is unavailable")
    return permissions


async def _validate_role_parent(
    db: AsyncSession, *, organization_id: str, role_name: str, parent_role: str | None
) -> None:
    if not _ROLE_NAME_RE.fullmatch(role_name) or (
        parent_role is not None and not _ROLE_NAME_RE.fullmatch(parent_role)
    ):
        raise ApiError(ErrorCategory.VALIDATION, "corporate role name is invalid")
    if parent_role is None:
        return
    if parent_role == role_name:
        raise ApiError(ErrorCategory.VALIDATION, "corporate role hierarchy contains a cycle")
    if (
        await db.scalar(
            select(CorporateRoleRow.name).where(
                CorporateRoleRow.organization_id == organization_id,
                CorporateRoleRow.name == parent_role,
            )
        )
        is None
    ):
        raise ApiError(ErrorCategory.VALIDATION, "corporate parent role is unavailable")
    current: str | None = parent_role
    seen: set[str] = set()
    while current is not None and current not in seen and len(seen) < 32:
        seen.add(current)
        current = await db.scalar(
            select(CorporateRoleRow.parent_role).where(
                CorporateRoleRow.organization_id == organization_id,
                CorporateRoleRow.name == current,
            )
        )
    if current == role_name or len(seen) >= 32:
        raise ApiError(ErrorCategory.VALIDATION, "corporate role hierarchy contains a cycle")


def _service_principal_view(
    row: CorporateServicePrincipal, binding: CorporateRoleBinding
) -> CorporateServicePrincipalView:
    return CorporateServicePrincipalView(
        service_principal_id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        state=cast(CorporateState, row.state),
        revision=row.revision,
        binding=_binding_view(binding),
    )


async def bootstrap(
    db: AsyncSession, *, payload: CorporateBootstrapRequest, request_id: str | None
) -> CorporateOrganization:
    await set_tenant_scope(db, "*")
    await db.execute(select(func.pg_advisory_xact_lock(7901)))
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    receipt = await db.get(CorporateBootstrapReceipt, payload.idempotency_key)
    if receipt is not None:
        if receipt.request_fingerprint != fingerprint:
            raise ApiError(ErrorCategory.CONFLICT, "bootstrap idempotency key was reused")
        organization = await db.get(Organization, receipt.organization_id)
        if organization is None:
            raise ApiError(ErrorCategory.INTERNAL, "bootstrap receipt is invalid")
        await emit_audit(
            db,
            actor_account_id=receipt.account_id,
            organization_id=receipt.organization_id,
            action="corporate.bootstrap.replay",
            target_table="corporate_bootstrap_receipt",
            target_id=receipt.organization_id,
            reason="idempotent_replay",
            request_id=request_id,
        )
        return organization_view(organization)
    existing = await db.scalar(
        select(Organization).where(Organization.kind == "corporate").with_for_update()
    )
    if existing is not None:
        raise ApiError(ErrorCategory.CONFLICT, "corporate bootstrap is closed")
    account = await db.get(Account, payload.superadmin_account_id)
    if account is None or account.status != "active":
        raise ApiError(ErrorCategory.VALIDATION, "bootstrap account is not active")
    organization = Organization(
        id=new_id("organization"),
        kind="corporate",
        owner_account_id=None,
        display_name=payload.organization_name,
        state="active",
        policy_revision=1,
    )
    db.add(organization)
    await db.flush()
    await set_tenant_scope(db, organization.id)
    membership = OrganizationMembership(
        organization_id=organization.id,
        account_id=account.id,
        role="superadmin",
        state="active",
    )
    db.add(membership)
    await db.flush()
    db.add_all(
        (
            CorporateRoleRow(organization_id=organization.id, name="superadmin", parent_role=None),
            CorporateRoleRow(organization_id=organization.id, name="lead", parent_role=None),
            CorporateRoleRow(organization_id=organization.id, name="staff", parent_role=None),
        )
    )
    for role, permissions in ROLE_PERMISSIONS.items():
        db.add_all(
            CorporateRolePermission(
                organization_id=organization.id, role=role, permission=permission
            )
            for permission in permissions
        )
    db.add(
        CorporateRoleBinding(
            id=new_id("operation"),
            organization_id=organization.id,
            account_id=account.id,
            role="superadmin",
            scope_kind="organization",
            scope_id=organization.id,
            state="active",
        )
    )
    db.add(
        CorporateBootstrapReceipt(
            idempotency_key=payload.idempotency_key,
            request_fingerprint=fingerprint,
            organization_id=organization.id,
            account_id=account.id,
        )
    )
    await emit_audit(
        db,
        actor_account_id=account.id,
        organization_id=organization.id,
        action="corporate.bootstrap",
        target_table="organization",
        target_id=organization.id,
        request_id=request_id,
    )
    return organization_view(organization)


async def _organization_and_membership(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str
) -> tuple[Organization, OrganizationMembership]:
    await set_tenant_scope(db, organization_id)
    pair = (
        await db.execute(
            select(Organization, OrganizationMembership)
            .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
            .where(
                Organization.id == organization_id,
                Organization.kind == "corporate",
                Organization.state == "active",
                OrganizationMembership.account_id == ctx.account_id,
                OrganizationMembership.state == "active",
            )
        )
    ).one_or_none()
    if pair is None:
        raise ApiError(ErrorCategory.PERMISSION, "organization access denied")
    return pair[0], pair[1]


organization_and_membership = _organization_and_membership


async def authorize(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    permission: str,
    scope_kind: str = "organization",
    scope_id: str | None = None,
    authorization_revision: int | None = None,
    extra_grant: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[Organization, OrganizationMembership]:
    organization, membership = await _organization_and_membership(
        db, ctx=ctx, organization_id=organization_id
    )
    if (
        authorization_revision is not None
        and authorization_revision != organization.policy_revision
    ):
        raise ApiError(ErrorCategory.PRECONDITION, "capability revision is stale")
    scope = scope_id or organization_id
    if permission in {"entity_profile.update", "entity_profile.owner"}:
        from ai_stp_api.slices.corporate.entity_profiles import can_edit_profile

        if not await can_edit_profile(
            db,
            ctx=ctx,
            organization_id=organization_id,
            subject_kind=scope_kind,
            subject_id=scope,
            owner_assignment=permission == "entity_profile.owner",
        ):
            raise ApiError(ErrorCategory.PERMISSION, "profile edit is forbidden")
        return organization, membership
    allowed = await has_corporate_permission(
        db,
        organization_id=organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        permission=permission,
        scope_kind=scope_kind,
        scope_id=scope,
    )
    if not allowed and scope_kind == "member":
        # Organization-wide member administration keeps working for org-scoped
        # roles; scoped (team) grants already matched inside the evaluator.
        allowed = await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=ctx.account_id,
            permission=permission,
            scope_kind="organization",
            scope_id=organization_id,
        )
    if not allowed and extra_grant is not None:
        allowed = await extra_grant()
    if not allowed:
        raise ApiError(ErrorCategory.PERMISSION, "capability is forbidden")
    return organization, membership


async def _scope_target_exists(
    db: AsyncSession, *, organization_id: str, scope_kind: str, scope_id: str
) -> bool:
    if scope_kind == "organization":
        return scope_id in {"*", organization_id}
    if scope_kind == "team":
        return (
            await db.scalar(
                select(CorporateTeam.id).where(
                    CorporateTeam.organization_id == organization_id,
                    CorporateTeam.id == scope_id,
                    CorporateTeam.state == "active",
                )
            )
            is not None
        )
    if scope_kind == "project":
        return (
            await db.scalar(
                select(CorporateProject.id).where(
                    CorporateProject.organization_id == organization_id,
                    CorporateProject.id == scope_id,
                    CorporateProject.state == "active",
                )
            )
            is not None
        )
    if scope_kind == "technology":
        return (
            await db.scalar(
                select(Technology.id).where(
                    Technology.organization_id == organization_id,
                    Technology.id == scope_id,
                    Technology.lifecycle.in_(("active", "deprecated")),
                    Technology.redirect_id.is_(None),
                )
            )
            is not None
        )
    # Catalog-object, telemetry, and system resources have no
    # B2B-01 resource table yet; accepting arbitrary IDs would create a grant
    # that cannot be tenant-checked. Their owning feature must add this check.
    return False


async def _ensure_role_exists(db: AsyncSession, *, organization_id: str, role: str) -> None:
    if (
        await db.scalar(
            select(CorporateRoleRow.name).where(
                CorporateRoleRow.organization_id == organization_id,
                CorporateRoleRow.name == role,
            )
        )
        is None
    ):
        raise ApiError(ErrorCategory.VALIDATION, "corporate role is unavailable")


async def _ensure_current_job_title(
    db: AsyncSession, *, organization_id: str, job_title_id: str | None
) -> None:
    if job_title_id is None:
        return
    if (
        await db.scalar(
            select(CorporateJobTitle.id).where(
                CorporateJobTitle.organization_id == organization_id,
                CorporateJobTitle.id == job_title_id,
                CorporateJobTitle.state == "current",
            )
        )
        is None
    ):
        raise ApiError(ErrorCategory.VALIDATION, "job title is unavailable")


async def _ensure_active_teams(
    db: AsyncSession, *, organization_id: str, team_ids: list[str]
) -> None:
    unique_ids = list(dict.fromkeys(team_ids))
    rows = list(
        (
            await db.scalars(
                select(CorporateTeam).where(
                    CorporateTeam.organization_id == organization_id,
                    CorporateTeam.id.in_(unique_ids),
                    CorporateTeam.state == "active",
                )
            )
        ).all()
    )
    if len(rows) != len(unique_ids):
        raise ApiError(ErrorCategory.VALIDATION, "team relationship is unavailable")


async def _ensure_active_projects(
    db: AsyncSession, *, organization_id: str, project_ids: list[str]
) -> None:
    unique_ids = list(dict.fromkeys(project_ids))
    rows = list(
        (
            await db.scalars(
                select(CorporateProject).where(
                    CorporateProject.organization_id == organization_id,
                    CorporateProject.id.in_(unique_ids),
                    CorporateProject.state == "active",
                    CorporateProject.lifecycle == "active",
                )
            )
        ).all()
    )
    if len(rows) != len(unique_ids):
        raise ApiError(ErrorCategory.VALIDATION, "project relationship is unavailable")


async def _ensure_active_technologies(
    db: AsyncSession, *, organization_id: str, technology_ids: list[str]
) -> None:
    unique_ids = list(dict.fromkeys(technology_ids))
    rows = list(
        (
            await db.scalars(
                select(Technology).where(
                    Technology.organization_id == organization_id,
                    Technology.id.in_(unique_ids),
                    Technology.lifecycle == "active",
                    Technology.redirect_id.is_(None),
                )
            )
        ).all()
    )
    if len(rows) != len(unique_ids):
        raise ApiError(ErrorCategory.VALIDATION, "technology relationship is unavailable")


async def _ensure_active_members(
    db: AsyncSession, *, organization_id: str, account_ids: list[str]
) -> None:
    unique_ids = list(dict.fromkeys(account_ids))
    rows = list(
        (
            await db.scalars(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.account_id.in_(unique_ids),
                    OrganizationMembership.state == "active",
                )
            )
        ).all()
    )
    if len(rows) != len(unique_ids):
        raise ApiError(ErrorCategory.VALIDATION, "employee relationship is unavailable")


async def store_mutation_receipt(
    db: AsyncSession,
    *,
    organization_id: str,
    key: str,
    operation: str,
    fingerprint: str,
    response: BaseModel,
    effect_metadata: Mapping[str, object] | None = None,
) -> None:
    body = response.model_dump(mode="json")
    if effect_metadata is not None:
        body["_mutation_effect"] = dict(effect_metadata)
    db.add(
        CorporateMutationReceipt(
            organization_id=organization_id,
            idempotency_key=key,
            operation=operation,
            request_fingerprint=fingerprint,
            response_body=body,
        )
    )


async def authorize_idempotent(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    permission: str,
    authorization_revision: int | str,
    idempotency_key: str,
    operation: str,
    fingerprint: str,
    request_id: str | None = None,
    scope_kind: str = "organization",
    scope_id: str | None = None,
    legacy_fingerprint: str | None = None,
    extra_grant: Callable[[], Awaitable[bool]] | None = None,
) -> tuple[Organization, CorporateMutationReceipt | None]:
    organization, membership = await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=permission,
        scope_kind=scope_kind,
        scope_id=scope_id,
        extra_grant=extra_grant,
    )
    # ponytail: per-tenant mutation lock; split locks if measured throughput needs it.
    locked = await db.scalar(
        select(Organization)
        .where(Organization.id == organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None:
        raise ApiError(ErrorCategory.PERMISSION, "organization access denied")
    organization, membership = await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=permission,
        scope_kind=scope_kind,
        scope_id=scope_id,
        extra_grant=extra_grant,
    )
    receipt = await db.get(CorporateMutationReceipt, (organization_id, idempotency_key))
    if receipt is not None:
        if receipt.operation != operation or receipt.request_fingerprint not in {
            fingerprint,
            legacy_fingerprint,
        }:
            raise ApiError(ErrorCategory.CONFLICT, "idempotency key was reused")
        if scope_kind in {"team", "project"} and scope_id not in {None, "*"}:
            receipt_scope_id = receipt.response_body.get(
                f"{scope_kind}_id",
                receipt.response_body.get("resource_id", receipt.response_body.get("subject_id")),
            )
            if receipt_scope_id is None and operation not in {
                "entity.profile.upload",
                "entity.profile.update",
                # The source assignment is the scoped object; its scope id is
                # part of the fingerprint but is not repeated in the result.
                "catalog_assignment.distribute",
            }:
                raise ApiError(ErrorCategory.CONFLICT, "idempotency key was reused")
            if receipt_scope_id is not None and receipt_scope_id != scope_id:
                raise ApiError(ErrorCategory.CONFLICT, "idempotency key was reused")
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            organization_id=organization_id,
            action=f"{operation}.replay",
            target_table="corporate_mutation_receipt",
            target_id=organization_id,
            reason="idempotent_replay",
            payload={"operation": operation},
            request_id=request_id,
        )
        return organization, receipt
    expected_authorization_revision = (
        context_authorization_revision(
            "corporate", organization_id, organization.policy_revision, membership.revision
        )
        if isinstance(authorization_revision, str)
        else organization.policy_revision
    )
    if authorization_revision != expected_authorization_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "capability revision is stale")
    return organization, None


async def create_role(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateRoleCreateRequest,
    request_id: str | None,
) -> CorporateRoleView:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="role.create",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="role.create",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateRoleView.model_validate(receipt.response_body)
    await _validate_role_parent(
        db,
        organization_id=organization_id,
        role_name=payload.name,
        parent_role=payload.parent_role,
    )
    permissions = _role_permissions(payload.permissions)
    if await db.get(CorporateRoleRow, (organization_id, payload.name)) is not None:
        raise ApiError(ErrorCategory.CONFLICT, "corporate role already exists")
    row = CorporateRoleRow(
        organization_id=organization_id,
        name=payload.name,
        parent_role=payload.parent_role,
    )
    db.add(row)
    db.add_all(
        CorporateRolePermission(
            organization_id=organization_id, role=payload.name, permission=permission
        )
        for permission in permissions
    )
    organization.policy_revision += 1
    await db.flush()
    response = await _role_view(db, row)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="role.create",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="role.create",
        target_table="corporate_role",
        target_id=payload.name,
        request_id=request_id,
        payload={"after": response.model_dump(mode="json")},
    )
    return response


async def list_roles(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, request_id: str | None
) -> CorporateRoleList:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="role.list")
    rows = list(
        (
            await db.scalars(
                select(CorporateRoleRow)
                .where(CorporateRoleRow.organization_id == organization_id)
                .order_by(CorporateRoleRow.name)
                .limit(256)
            )
        ).all()
    )
    response = CorporateRoleList(items=[await _role_view(db, row) for row in rows])
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="role.list",
        target_table="corporate_role",
        target_id=organization_id,
        request_id=request_id,
    )
    return response


async def read_role(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    role_name: str,
    request_id: str | None,
) -> CorporateRoleView:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="role.read")
    row = await db.get(CorporateRoleRow, (organization_id, role_name))
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "corporate role not found")
    response = await _role_view(db, row)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="role.read",
        target_table="corporate_role",
        target_id=role_name,
        request_id=request_id,
    )
    return response


async def update_role(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    role_name: str,
    payload: CorporateRoleUpdateRequest,
    request_id: str | None,
) -> CorporateRoleView:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="role.update",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="role.update",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateRoleView.model_validate(receipt.response_body)
    row = await db.scalar(
        select(CorporateRoleRow)
        .where(
            CorporateRoleRow.organization_id == organization_id,
            CorporateRoleRow.name == role_name,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "corporate role not found")
    if role_name in _BUILT_IN_ROLES:
        raise ApiError(ErrorCategory.CONFLICT, "built-in corporate role is immutable")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "corporate role revision changed")
    await _validate_role_parent(
        db,
        organization_id=organization_id,
        role_name=role_name,
        parent_role=payload.parent_role,
    )
    permissions = _role_permissions(payload.permissions)
    before = await _role_view(db, row)
    row.parent_role = payload.parent_role
    row.revision += 1
    await db.execute(
        delete(CorporateRolePermission).where(
            CorporateRolePermission.organization_id == organization_id,
            CorporateRolePermission.role == role_name,
        )
    )
    db.add_all(
        CorporateRolePermission(
            organization_id=organization_id, role=role_name, permission=permission
        )
        for permission in permissions
    )
    organization.policy_revision += 1
    await db.flush()
    response = await _role_view(db, row)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="role.update",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="role.update",
        target_table="corporate_role",
        target_id=role_name,
        request_id=request_id,
        payload={
            "before": before.model_dump(mode="json"),
            "after": response.model_dump(mode="json"),
        },
    )
    return response


async def delete_role(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    role_name: str,
    payload: CorporateDeleteRequest,
    request_id: str | None,
) -> CorporateDeleteResult:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="role.delete",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="role.delete",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateDeleteResult.model_validate(receipt.response_body)
    row = await db.scalar(
        select(CorporateRoleRow)
        .where(
            CorporateRoleRow.organization_id == organization_id,
            CorporateRoleRow.name == role_name,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.NOT_FOUND, "corporate role not found")
    if role_name in _BUILT_IN_ROLES:
        raise ApiError(ErrorCategory.CONFLICT, "built-in corporate role is immutable")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "corporate role revision changed")
    in_use = await db.scalar(
        select(CorporateRoleBinding.id).where(
            CorporateRoleBinding.organization_id == organization_id,
            CorporateRoleBinding.role == role_name,
            CorporateRoleBinding.state == "active",
        )
    )
    child = await db.scalar(
        select(CorporateRoleRow.name).where(
            CorporateRoleRow.organization_id == organization_id,
            CorporateRoleRow.parent_role == role_name,
        )
    )
    if in_use is not None or child is not None:
        raise ApiError(ErrorCategory.CONFLICT, "corporate role is still referenced")
    await db.delete(row)
    organization.policy_revision += 1
    response = CorporateDeleteResult(resource_id=role_name)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="role.delete",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="role.delete",
        target_table="corporate_role",
        target_id=role_name,
        request_id=request_id,
    )
    return response


async def create_job_title(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateJobTitleCreateRequest,
    request_id: str | None,
) -> CorporateJobTitleView:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="job_title.create",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="job_title.create",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateJobTitleView.model_validate(receipt.response_body)
    name = " ".join(unicodedata.normalize("NFKC", payload.name).split())
    normalized_name = _normalize_job_title(name)
    if not name or await db.scalar(
        select(CorporateJobTitle.id).where(
            CorporateJobTitle.organization_id == organization_id,
            CorporateJobTitle.normalized_name == normalized_name,
        )
    ):
        raise ApiError(ErrorCategory.CONFLICT, "job title already exists")
    row = CorporateJobTitle(
        id=new_id("job_title"),
        organization_id=organization_id,
        name=name,
        normalized_name=normalized_name,
        description=payload.description.strip(),
        state="current",
    )
    db.add(row)
    organization.policy_revision += 1
    await db.flush()
    response = job_title_view(row)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="job_title.create",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="job_title.create",
        target_table="corporate_job_title",
        target_id=row.id,
        request_id=request_id,
    )
    return response


async def list_job_titles(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, request_id: str | None
) -> CorporateJobTitleList:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="job_title.list")
    rows = (
        await db.scalars(
            select(CorporateJobTitle)
            .where(CorporateJobTitle.organization_id == organization_id)
            .order_by(CorporateJobTitle.normalized_name, CorporateJobTitle.id)
            .limit(256)
        )
    ).all()
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="job_title.list",
        target_table="corporate_job_title",
        target_id=organization_id,
        request_id=request_id,
    )
    return CorporateJobTitleList(items=[job_title_view(row) for row in rows])


async def update_job_title(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    job_title_id: str,
    payload: CorporateJobTitleUpdateRequest,
    request_id: str | None,
) -> CorporateJobTitleView:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="job_title.update",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="job_title.update",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateJobTitleView.model_validate(receipt.response_body)
    row = await db.scalar(
        select(CorporateJobTitle)
        .where(
            CorporateJobTitle.organization_id == organization_id,
            CorporateJobTitle.id == job_title_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "job title access denied")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "job title revision changed")
    name = " ".join(unicodedata.normalize("NFKC", payload.name).split())
    normalized_name = _normalize_job_title(name)
    duplicate = await db.scalar(
        select(CorporateJobTitle.id).where(
            CorporateJobTitle.organization_id == organization_id,
            CorporateJobTitle.normalized_name == normalized_name,
            CorporateJobTitle.id != job_title_id,
        )
    )
    if duplicate:
        raise ApiError(ErrorCategory.CONFLICT, "job title already exists")
    row.name = name
    row.normalized_name = normalized_name
    row.description = payload.description.strip()
    row.state = payload.state
    row.revision += 1
    organization.policy_revision += 1
    await db.flush()
    response = job_title_view(row)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="job_title.update",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="job_title.update",
        target_table="corporate_job_title",
        target_id=job_title_id,
        request_id=request_id,
    )
    return response


async def create_member(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateMemberCreateRequest,
    request_id: str | None,
) -> CorporateMember:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.create",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="member.create",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateMember.model_validate(receipt.response_body)
    await _ensure_active_teams(db, organization_id=organization_id, team_ids=payload.team_ids)
    await _ensure_active_projects(
        db, organization_id=organization_id, project_ids=payload.project_ids
    )
    await _ensure_role_exists(db, organization_id=organization_id, role=payload.role)
    await _ensure_current_job_title(
        db, organization_id=organization_id, job_title_id=payload.job_title_id
    )
    if payload.catalog_assignments:
        if not await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=ctx.account_id,
            permission="catalog_object.assign",
        ):
            raise ApiError(ErrorCategory.PERMISSION, "catalog assignment access denied")
        assignment_keys: set[tuple[str, str]] = set()
        for assignment in payload.catalog_assignments:
            key = (assignment.stable_id, assignment.version)
            if key in assignment_keys:
                raise ApiError(ErrorCategory.VALIDATION, "duplicate catalog assignment")
            assignment_keys.add(key)
            catalog = await get_visible_metadata(
                db,
                object_kind=assignment.object_kind,
                stable_id=assignment.stable_id,
                version=assignment.version,
                account_id=ctx.account_id,
            )
            if (
                catalog is None
                or catalog.published_at is None
                or catalog.lifecycle_state not in {"active", "deprecated"}
            ):
                raise ApiError(ErrorCategory.PERMISSION, "catalog version is unavailable")
    account = await db.get(Account, payload.account_id) if payload.account_id else None
    if account is None:
        account = Account(id=new_id("account"), status="active", display_name=payload.display_name)
        db.add(account)
        await db.flush()
    if payload.email is not None:
        db.add(
            CorporateProvisionedIdentity(
                organization_id=organization_id,
                normalized_email=normalize_email(payload.email),
                account_id=account.id,
            )
        )
    existing = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.account_id == account.id,
        )
    )
    if existing is not None:
        raise ApiError(ErrorCategory.CONFLICT, "member already exists")
    membership = OrganizationMembership(
        organization_id=organization_id,
        account_id=account.id,
        display_name=payload.display_name.strip(),
        role=payload.role,
        state="active",
        job_title_id=payload.job_title_id,
    )
    binding = CorporateRoleBinding(
        id=new_id("operation"),
        organization_id=organization_id,
        account_id=account.id,
        role=payload.role,
        scope_kind="organization",
        scope_id=organization_id,
        state="active",
    )
    db.add(membership)
    await db.flush()
    db.add(binding)
    for team_id in dict.fromkeys(payload.team_ids):
        db.add(
            CorporateTeamMember(
                organization_id=organization_id,
                team_id=team_id,
                account_id=account.id,
                role="staff",
            )
        )
        db.add(
            CorporateRoleBinding(
                id=new_id("operation"),
                organization_id=organization_id,
                account_id=account.id,
                role="staff",
                scope_kind="team",
                scope_id=team_id,
                state="active",
            )
        )
    for project_id in dict.fromkeys(payload.project_ids):
        db.add(
            CorporateProjectMember(
                organization_id=organization_id,
                project_id=project_id,
                account_id=account.id,
            )
        )
    for assignment in payload.catalog_assignments:
        db.add(
            CorporateCatalogAssignmentRow(
                id=new_id("operation"),
                organization_id=organization_id,
                account_id=account.id,
                object_kind=assignment.object_kind,
                stable_id=assignment.stable_id,
                version=assignment.version,
                state="current",
                revision=1,
            )
        )
    organization.policy_revision += 1
    await db.flush()
    response = member_view(membership, account)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="member.create",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="member.create",
        target_table="organization_membership",
        target_id=account.id,
        request_id=request_id,
    )
    return response


async def list_members(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, request_id: str | None
) -> CorporateMemberList:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="member.list")
    rows = (
        await db.execute(
            select(OrganizationMembership, Account)
            .join(Account, Account.id == OrganizationMembership.account_id)
            .where(OrganizationMembership.organization_id == organization_id)
            .order_by(Account.id)
            .limit(256)
        )
    ).all()
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="member.list",
        target_table="organization_membership",
        target_id=organization_id,
        request_id=request_id,
    )
    return CorporateMemberList(items=[member_view(member, account) for member, account in rows])


async def list_project_members(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    request_id: str | None,
) -> CorporateMemberList:
    await read_project(
        db, ctx=ctx, organization_id=organization_id, project_id=project_id, request_id=request_id
    )
    members = await list_members(
        db, ctx=ctx, organization_id=organization_id, request_id=request_id
    )
    assigned = set(
        (
            await db.scalars(
                select(CorporateProjectMember.account_id).where(
                    CorporateProjectMember.organization_id == organization_id,
                    CorporateProjectMember.project_id == project_id,
                )
            )
        ).all()
    )
    return CorporateMemberList(
        items=[member for member in members.items if member.account_id in assigned]
    )


async def list_member_projects(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    account_id: str,
    request_id: str | None,
) -> CorporateProjectList:
    await read_member(
        db, ctx=ctx, organization_id=organization_id, account_id=account_id, request_id=request_id
    )
    projects = await list_projects(
        db, ctx=ctx, organization_id=organization_id, request_id=request_id
    )
    assigned = set(
        (
            await db.scalars(
                select(CorporateProjectMember.project_id).where(
                    CorporateProjectMember.organization_id == organization_id,
                    CorporateProjectMember.account_id == account_id,
                )
            )
        ).all()
    )
    return CorporateProjectList(
        items=[project for project in projects.items if project.project_id in assigned]
    )


async def update_member(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    account_id: str,
    payload: CorporateMemberUpdateRequest,
    request_id: str | None,
) -> CorporateMember:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.update",
        scope_kind="member",
        scope_id=account_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="member.update",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateMember.model_validate(receipt.response_body)
    row = await db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.account_id == account_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "member access denied")
    account = await db.get(Account, account_id)
    if account is None:
        raise ApiError(ErrorCategory.INTERNAL, "member account is missing")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "member revision changed")
    org_admin = await has_corporate_permission(
        db,
        organization_id=organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        permission="member.update",
        scope_kind="organization",
        scope_id=organization_id,
    )
    if not org_admin and (row.role == "superadmin" or payload.role != row.role):
        # Scoped (team) member administration cannot change organization roles
        # or touch a superadmin membership.
        raise ApiError(ErrorCategory.PERMISSION, "member role change is forbidden")
    await _ensure_role_exists(db, organization_id=organization_id, role=payload.role)
    await _ensure_current_job_title(
        db, organization_id=organization_id, job_title_id=payload.job_title_id
    )
    before = {
        "role": row.role,
        "state": row.state,
        "job_title_id": row.job_title_id,
        "revision": row.revision,
    }
    removes_superadmin = row.role == "superadmin" and (
        payload.role != "superadmin" or payload.state != "active"
    )
    if removes_superadmin:
        active_superadmins = await db.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == "superadmin",
                OrganizationMembership.state == "active",
            )
        )
        if active_superadmins == 1:
            raise ApiError(ErrorCategory.CONFLICT, "last superadmin cannot be changed")
    row.role = payload.role
    row.state = payload.state
    row.job_title_id = payload.job_title_id
    row.revision += 1
    bindings = list(
        (
            await db.scalars(
                select(CorporateRoleBinding).where(
                    CorporateRoleBinding.organization_id == organization_id,
                    CorporateRoleBinding.account_id == account_id,
                    CorporateRoleBinding.state == "active",
                )
            )
        ).all()
    )
    scopes = {(binding.scope_kind, binding.scope_id) for binding in bindings}
    scopes.add(("organization", organization_id))
    for binding in bindings:
        binding.state = "revoked"
        binding.revision += 1
    if payload.state == "active":
        db.add_all(
            [
                CorporateRoleBinding(
                    id=new_id("operation"),
                    organization_id=organization_id,
                    account_id=account_id,
                    role=payload.role,
                    scope_kind=scope_kind,
                    scope_id=scope_id,
                    state="active",
                )
                for scope_kind, scope_id in scopes
            ]
        )
    organization.policy_revision += 1
    response = member_view(row, account)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="member.update",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="member.update",
        target_table="organization_membership",
        target_id=account_id,
        request_id=request_id,
        payload={
            "before": before,
            "after": {"role": row.role, "state": row.state, "revision": row.revision},
        },
    )
    return response


async def delete_member(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    account_id: str,
    payload: CorporateDeleteRequest,
    request_id: str | None,
) -> CorporateDeleteResult:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.delete",
        scope_kind="member",
        scope_id=account_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="member.delete",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateDeleteResult.model_validate(receipt.response_body)
    row = await db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.account_id == account_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "member access denied")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "member revision changed")
    org_admin = await has_corporate_permission(
        db,
        organization_id=organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        permission="member.delete",
        scope_kind="organization",
        scope_id=organization_id,
    )
    if not org_admin and row.role == "superadmin":
        raise ApiError(ErrorCategory.PERMISSION, "member delete is forbidden")
    if row.role == "superadmin" and row.state == "active":
        active_superadmins = await db.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == "superadmin",
                OrganizationMembership.state == "active",
            )
        )
        if active_superadmins == 1:
            raise ApiError(ErrorCategory.CONFLICT, "last superadmin cannot be changed")
    before = {"role": row.role, "state": row.state}
    await db.execute(
        delete(CorporateRoleBinding).where(
            CorporateRoleBinding.organization_id == organization_id,
            CorporateRoleBinding.account_id == account_id,
        )
    )
    await db.execute(
        delete(CorporateTeamMember).where(
            CorporateTeamMember.organization_id == organization_id,
            CorporateTeamMember.account_id == account_id,
        )
    )
    await db.execute(
        delete(CorporateProjectMember).where(
            CorporateProjectMember.organization_id == organization_id,
            CorporateProjectMember.account_id == account_id,
        )
    )
    await db.execute(
        delete(CorporateProvisionedIdentity).where(
            CorporateProvisionedIdentity.organization_id == organization_id,
            CorporateProvisionedIdentity.account_id == account_id,
        )
    )
    await db.delete(row)
    organization.policy_revision += 1
    response = CorporateDeleteResult(resource_id=account_id)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="member.delete",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="member.delete",
        target_table="organization_membership",
        target_id=account_id,
        request_id=request_id,
        payload={"before": before, "after": None},
    )
    return response


async def read_member(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    account_id: str,
    request_id: str | None,
) -> CorporateMember:
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.read",
        scope_kind="member",
        scope_id=account_id,
    )
    result = await db.execute(
        select(OrganizationMembership, Account)
        .join(Account, Account.id == OrganizationMembership.account_id)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.account_id == account_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "member access denied")
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="member.read",
        target_table="organization_membership",
        target_id=account_id,
        request_id=request_id,
    )
    from ai_stp_api.slices.corporate.subject_access import subject_available_actions

    actions = await subject_available_actions(
        db,
        account_id=ctx.account_id,
        organization_id=organization_id,
        subject_kind="employee",
        subject_id=account_id,
    )
    return member_view(*row).model_copy(update={"available_actions": actions})


async def create_binding(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateBindingRequest,
    request_id: str | None,
) -> CorporateBinding:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="binding.create",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="binding.create",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateBinding.model_validate(receipt.response_body)
    if (
        await db.scalar(
            select(CorporateRoleRow.name).where(
                CorporateRoleRow.organization_id == organization_id,
                CorporateRoleRow.name == payload.role,
            )
        )
        is None
    ):
        raise ApiError(ErrorCategory.VALIDATION, "corporate role is unavailable")
    member = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.account_id == payload.account_id,
            OrganizationMembership.state == "active",
        )
    )
    if member is None:
        raise ApiError(ErrorCategory.PERMISSION, "member access denied")
    if not await _scope_target_exists(
        db,
        organization_id=organization_id,
        scope_kind=payload.scope_kind,
        scope_id=payload.scope_id,
    ):
        raise ApiError(ErrorCategory.PERMISSION, "binding scope denied")
    if (
        await db.scalar(
            select(CorporateRoleBinding.id).where(
                CorporateRoleBinding.organization_id == organization_id,
                CorporateRoleBinding.principal_type == "user",
                CorporateRoleBinding.account_id == payload.account_id,
                CorporateRoleBinding.role == payload.role,
                CorporateRoleBinding.scope_kind == payload.scope_kind,
                CorporateRoleBinding.scope_id == payload.scope_id,
                CorporateRoleBinding.state == "active",
            )
        )
        is not None
    ):
        raise ApiError(ErrorCategory.CONFLICT, "binding already exists")
    row = CorporateRoleBinding(
        id=new_id("operation"),
        organization_id=organization_id,
        account_id=payload.account_id,
        role=payload.role,
        scope_kind=payload.scope_kind,
        scope_id=payload.scope_id,
        state="active",
    )
    db.add(row)
    organization.policy_revision += 1
    await db.flush()
    response = _binding_view(row)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="binding.create",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="binding.create",
        target_table="corporate_role_binding",
        target_id=row.id,
        request_id=request_id,
    )
    return response


async def list_bindings(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    request_id: str | None,
) -> CorporateBindingList:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="binding.list")
    rows = list(
        (
            await db.scalars(
                select(CorporateRoleBinding)
                .where(CorporateRoleBinding.organization_id == organization_id)
                .order_by(CorporateRoleBinding.id)
                .limit(256)
            )
        ).all()
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="binding.list",
        target_table="corporate_role_binding",
        target_id=organization_id,
        request_id=request_id,
    )
    return CorporateBindingList(items=[_binding_view(row) for row in rows])


async def read_binding(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    binding_id: str,
    request_id: str | None,
) -> CorporateBinding:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="binding.read")
    row = await db.scalar(
        select(CorporateRoleBinding).where(
            CorporateRoleBinding.organization_id == organization_id,
            CorporateRoleBinding.id == binding_id,
        )
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "binding access denied")
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="binding.read",
        target_table="corporate_role_binding",
        target_id=binding_id,
        request_id=request_id,
    )
    return _binding_view(row)


async def update_binding(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    binding_id: str,
    payload: CorporateBindingUpdateRequest,
    request_id: str | None,
) -> CorporateBinding:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="binding.update",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="binding.update",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateBinding.model_validate(receipt.response_body)
    row = await db.scalar(
        select(CorporateRoleBinding)
        .where(
            CorporateRoleBinding.organization_id == organization_id,
            CorporateRoleBinding.id == binding_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "binding access denied")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "binding revision changed")
    if (
        await db.scalar(
            select(CorporateRoleRow.name).where(
                CorporateRoleRow.organization_id == organization_id,
                CorporateRoleRow.name == payload.role,
            )
        )
        is None
    ):
        raise ApiError(ErrorCategory.VALIDATION, "corporate role is unavailable")
    if payload.state == "active" and not await _scope_target_exists(
        db,
        organization_id=organization_id,
        scope_kind=payload.scope_kind,
        scope_id=payload.scope_id,
    ):
        raise ApiError(ErrorCategory.PERMISSION, "binding scope denied")
    principal_filter = (
        CorporateRoleBinding.account_id == row.account_id
        if row.principal_type == "user"
        else CorporateRoleBinding.service_principal_id == row.service_principal_id
    )
    if payload.state == "active" and (
        await db.scalar(
            select(CorporateRoleBinding.id).where(
                CorporateRoleBinding.organization_id == organization_id,
                CorporateRoleBinding.principal_type == row.principal_type,
                principal_filter,
                CorporateRoleBinding.role == payload.role,
                CorporateRoleBinding.scope_kind == payload.scope_kind,
                CorporateRoleBinding.scope_id == payload.scope_id,
                CorporateRoleBinding.state == "active",
                CorporateRoleBinding.id != binding_id,
            )
        )
        is not None
    ):
        raise ApiError(ErrorCategory.CONFLICT, "binding already exists")
    if (
        row.state == "active"
        and row.role == "superadmin"
        and row.principal_type == "user"
        and (payload.role != "superadmin" or payload.state != "active")
    ):
        count = await db.scalar(
            select(func.count())
            .select_from(CorporateRoleBinding)
            .where(
                CorporateRoleBinding.organization_id == organization_id,
                CorporateRoleBinding.account_id == row.account_id,
                CorporateRoleBinding.role == "superadmin",
                CorporateRoleBinding.state == "active",
            )
        )
        if count == 1:
            raise ApiError(ErrorCategory.CONFLICT, "last superadmin cannot be changed")
    before = _binding_view(row).model_dump(mode="json")
    row.role = payload.role
    row.scope_kind = payload.scope_kind
    row.scope_id = payload.scope_id
    row.state = payload.state
    row.revision += 1
    organization.policy_revision += 1
    response = _binding_view(row)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="binding.update",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="binding.update",
        target_table="corporate_role_binding",
        target_id=binding_id,
        request_id=request_id,
        payload={"before": before, "after": response.model_dump(mode="json")},
    )
    return response


async def delete_binding(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    binding_id: str,
    payload: CorporateDeleteRequest,
    request_id: str | None,
) -> CorporateDeleteResult:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="binding.delete",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="binding.delete",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateDeleteResult.model_validate(receipt.response_body)
    row = await db.scalar(
        select(CorporateRoleBinding)
        .where(
            CorporateRoleBinding.organization_id == organization_id,
            CorporateRoleBinding.id == binding_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "binding access denied")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "binding revision changed")
    if row.state == "active" and row.role == "superadmin" and row.principal_type == "user":
        count = await db.scalar(
            select(func.count())
            .select_from(CorporateRoleBinding)
            .where(
                CorporateRoleBinding.organization_id == organization_id,
                CorporateRoleBinding.account_id == row.account_id,
                CorporateRoleBinding.role == "superadmin",
                CorporateRoleBinding.state == "active",
            )
        )
        if count == 1:
            raise ApiError(ErrorCategory.CONFLICT, "last superadmin cannot be changed")
    before = _binding_view(row).model_dump(mode="json")
    await db.delete(row)
    organization.policy_revision += 1
    response = CorporateDeleteResult(resource_id=binding_id)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="binding.delete",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="binding.delete",
        target_table="corporate_role_binding",
        target_id=binding_id,
        request_id=request_id,
        payload={"before": before, "after": None},
    )
    return response


async def create_project(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateProjectCreateRequest,
    request_id: str | None,
) -> CorporateProjectView:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.create",
        scope_kind="project",
        scope_id="*",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="project.create",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateProjectView.model_validate(receipt.response_body)
    if payload.owner_team_id is not None:
        await _ensure_active_teams(
            db, organization_id=organization_id, team_ids=[payload.owner_team_id]
        )
    await _ensure_active_technologies(
        db, organization_id=organization_id, technology_ids=list(payload.technology_ids)
    )
    row = CorporateProject(
        id=new_id("remote_project"),
        organization_id=organization_id,
        name=payload.name,
        lifecycle="active",
        profile={"description": payload.description},
    )
    db.add(
        ProjectIdentity(
            id=row.id,
            organization_id=organization_id,
            namespace="remote",
            external_key=f"corporate:{row.id}",
            display_name=row.name,
            state="active",
        )
    )
    await db.flush()
    db.add(row)
    await db.flush()
    if payload.owner_team_id is not None:
        db.add(
            ProjectTeamRelation(
                organization_id=organization_id,
                id=new_id("relation"),
                project_id=row.id,
                team_id=payload.owner_team_id,
                role="owner",
            )
        )
    for technology_id in dict.fromkeys(payload.technology_ids):
        db.add(
            ProjectTechnologyRelation(
                organization_id=organization_id,
                id=new_id("relation"),
                project_id=row.id,
                project_namespace="remote",
                technology_id=technology_id,
            )
        )
    await db.flush()
    organization.policy_revision += 1
    response = _project_view(row)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="project.create",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.create",
        target_table="corporate_project",
        target_id=row.id,
        request_id=request_id,
    )
    return response


async def list_projects(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, request_id: str | None
) -> CorporateProjectList:
    _, membership = await authorize(
        db, ctx=ctx, organization_id=organization_id, permission="project.list"
    )
    query = select(CorporateProject).where(CorporateProject.organization_id == organization_id)
    if membership.role != "superadmin":
        query = query.join(
            CorporateProjectMember,
            (CorporateProjectMember.organization_id == CorporateProject.organization_id)
            & (CorporateProjectMember.project_id == CorporateProject.id),
        ).where(CorporateProjectMember.account_id == ctx.account_id)
    rows = list(
        (
            await db.scalars(query.order_by(CorporateProject.name, CorporateProject.id).limit(256))
        ).all()
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.list",
        target_table="corporate_project",
        target_id=organization_id,
        request_id=request_id,
    )
    return CorporateProjectList(items=[_project_view(row) for row in rows])


async def read_project(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    request_id: str | None,
) -> CorporateProjectView:
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.read",
        scope_kind="project",
        scope_id=project_id,
    )
    row = await db.scalar(
        select(CorporateProject).where(
            CorporateProject.organization_id == organization_id,
            CorporateProject.id == project_id,
        )
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "project access denied")
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.read",
        target_table="corporate_project",
        target_id=project_id,
        request_id=request_id,
    )
    from ai_stp_api.slices.corporate.subject_access import subject_available_actions

    actions = await subject_available_actions(
        db,
        account_id=ctx.account_id,
        organization_id=organization_id,
        subject_kind="project",
        subject_id=project_id,
    )
    linked = list(
        (
            await db.scalars(
                select(ProjectIdentity)
                .join(
                    ProjectLink,
                    (ProjectLink.organization_id == ProjectIdentity.organization_id)
                    & (ProjectLink.provider_project_id == ProjectIdentity.id),
                )
                .where(
                    ProjectLink.organization_id == organization_id,
                    ProjectLink.remote_project_id == project_id,
                    ProjectLink.state == "linked",
                    ProjectIdentity.provider_kind == "gitlab",
                )
                .distinct()
                .order_by(ProjectIdentity.id)
                .limit(257)
            )
        ).all()
    )
    if len(linked) > 256:
        raise ApiError(ErrorCategory.VALIDATION, "project repository limit exceeded")
    repositories = [
        CorporateProjectRepository(
            provider_project_id=identity.id,
            namespace=identity.observed_name or identity.display_name,
            repository_url=identity.current_url,
            default_branch=identity.provider_default_branch,
            observed_revision=identity.provider_observed_revision,
            observed_at=format_timestamp(identity.observed_at) if identity.observed_at else None,
        )
        for identity in linked
        if identity.current_url is not None
    ]
    return _project_view(row).model_copy(
        update={"available_actions": actions, "repositories": repositories}
    )


async def update_project(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    payload: CorporateProjectUpdateRequest,
    request_id: str | None,
) -> CorporateProjectView:
    fingerprint = mutation_fingerprint(
        {
            "project_id": project_id,
            "payload": payload.model_dump(mode="json", exclude={"idempotency_key"}),
        }
    )
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.update",
        idempotency_key=payload.idempotency_key,
        operation="project.update",
        fingerprint=fingerprint,
        legacy_fingerprint=mutation_fingerprint(
            payload.model_dump(mode="json", exclude={"idempotency_key"})
        ),
        request_id=request_id,
        scope_kind="project",
        scope_id=project_id,
        authorization_revision=payload.authorization_revision,
    )
    if receipt is not None:
        return CorporateProjectView.model_validate(receipt.response_body)
    row = await db.scalar(
        select(CorporateProject)
        .where(
            CorporateProject.organization_id == organization_id,
            CorporateProject.id == project_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "project access denied")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "project revision changed")
    if row.lifecycle == "deleted":
        raise ApiError(ErrorCategory.CONFLICT, "deleted project requires explicit restoration")
    before = {"name": row.name, "state": row.state, "revision": row.revision}
    identity = await db.scalar(
        select(ProjectIdentity)
        .where(
            ProjectIdentity.organization_id == organization_id,
            ProjectIdentity.id == project_id,
            ProjectIdentity.namespace == "remote",
        )
        .with_for_update()
    )
    if identity is None:
        raise ApiError(ErrorCategory.CONFLICT, "project identity is unavailable")
    identity.display_name = payload.name
    identity.state = payload.state
    identity.revision += 1
    row.name = payload.name
    # Unchanged compatibility state must not silently revive a deprecated project.
    if payload.state != row.state:
        if row.lifecycle in {"active", "deprecated"}:
            row.restore_lifecycle = row.lifecycle
        row.lifecycle = payload.state
    row.state = payload.state
    row.revision += 1
    organization.policy_revision += 1
    response = _project_view(row)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="project.update",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.update",
        target_table="corporate_project",
        target_id=row.id,
        request_id=request_id,
        payload={
            "before": before,
            "after": {"name": row.name, "state": row.state, "revision": row.revision},
        },
    )
    return response


async def change_project_lifecycle(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    payload: CorporateProjectLifecycleRequest,
    request_id: str | None,
) -> CorporateProjectView:
    fingerprint = mutation_fingerprint(
        {
            "project_id": project_id,
            "payload": payload.model_dump(mode="json", exclude={"idempotency_key"}),
        }
    )
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.update",
        scope_kind="project",
        scope_id=project_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="project.lifecycle",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateProjectView.model_validate(receipt.response_body)
    row = await db.scalar(
        select(CorporateProject)
        .where(
            CorporateProject.organization_id == organization_id,
            CorporateProject.id == project_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "project access denied")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "project revision changed")
    before = _project_view(row).model_dump(mode="json")
    if payload.target == "restore":
        if row.lifecycle not in {"archived", "deleted"}:
            raise ApiError(ErrorCategory.CONFLICT, "project is not restorable")
        target = row.restore_lifecycle
    else:
        if row.lifecycle in {"archived", "deleted"}:
            raise ApiError(ErrorCategory.CONFLICT, "project requires explicit restoration")
        target = payload.target
    if target == row.lifecycle:
        raise ApiError(ErrorCategory.CONFLICT, "project lifecycle is unchanged")
    identity = await db.scalar(
        select(ProjectIdentity)
        .where(
            ProjectIdentity.organization_id == organization_id,
            ProjectIdentity.id == project_id,
            ProjectIdentity.namespace == "remote",
        )
        .with_for_update()
    )
    if identity is None:
        raise ApiError(ErrorCategory.CONFLICT, "project identity is unavailable")
    if row.lifecycle in {"active", "deprecated"}:
        row.restore_lifecycle = row.lifecycle
    row.lifecycle = target
    row.state = "active" if target == "active" else "archived"
    row.revision += 1
    identity.state = row.state
    identity.revision += 1
    organization.policy_revision += 1
    response = _project_view(row)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="project.lifecycle",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.lifecycle",
        target_table="corporate_project",
        target_id=project_id,
        request_id=request_id,
        payload={"before": before, "after": response.model_dump(mode="json")},
    )
    return response


async def delete_project(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    payload: CorporateDeleteRequest,
    request_id: str | None,
) -> CorporateDeleteResult:
    fingerprint = mutation_fingerprint(
        {
            "project_id": project_id,
            "payload": payload.model_dump(mode="json", exclude={"idempotency_key"}),
        }
    )
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.delete",
        idempotency_key=payload.idempotency_key,
        operation="project.delete",
        fingerprint=fingerprint,
        legacy_fingerprint=mutation_fingerprint(
            payload.model_dump(mode="json", exclude={"idempotency_key"})
        ),
        request_id=request_id,
        scope_kind="project",
        scope_id=project_id,
        authorization_revision=payload.authorization_revision,
    )
    if receipt is not None:
        return CorporateDeleteResult.model_validate(receipt.response_body)
    row = await db.scalar(
        select(CorporateProject)
        .where(
            CorporateProject.organization_id == organization_id,
            CorporateProject.id == project_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "project access denied")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "project revision changed")
    if row.lifecycle == "deleted":
        raise ApiError(ErrorCategory.CONFLICT, "project is already deleted")
    before = _project_view(row).model_dump(mode="json")
    identity = await db.scalar(
        select(ProjectIdentity)
        .where(
            ProjectIdentity.organization_id == organization_id,
            ProjectIdentity.id == project_id,
            ProjectIdentity.namespace == "remote",
        )
        .with_for_update()
    )
    if identity is None:
        raise ApiError(ErrorCategory.CONFLICT, "project identity is unavailable")
    if row.lifecycle in {"active", "deprecated"}:
        row.restore_lifecycle = row.lifecycle
    row.lifecycle, row.state = "deleted", "archived"
    row.revision += 1
    identity.state = "deleted"
    identity.revision += 1
    organization.policy_revision += 1
    response = CorporateDeleteResult(resource_id=project_id)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="project.delete",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.delete",
        target_table="corporate_project",
        target_id=project_id,
        request_id=request_id,
        payload={"before": before, "after": _project_view(row).model_dump(mode="json")},
    )
    return response


async def create_team(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateTeamCreateRequest,
    request_id: str | None,
) -> CorporateTeamView:
    fingerprint = mutation_fingerprint(
        payload.model_dump(
            mode="json",
            exclude={"idempotency_key"}
            | ({"description"} if "description" not in payload.model_fields_set else set()),
        )
    )
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="team.create",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="team.create",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateTeamView.model_validate(receipt.response_body)
    employee_ids = list(dict.fromkeys(payload.employee_ids))
    if payload.lead_account_id is not None and payload.lead_account_id not in employee_ids:
        raise ApiError(ErrorCategory.VALIDATION, "team lead must be an employee of the team")
    await _ensure_active_members(db, organization_id=organization_id, account_ids=employee_ids)
    await _ensure_active_projects(
        db, organization_id=organization_id, project_ids=list(payload.project_ids)
    )
    await _ensure_active_technologies(
        db, organization_id=organization_id, technology_ids=list(payload.technology_ids)
    )
    row = CorporateTeam(
        id=new_id("operation"),
        organization_id=organization_id,
        name=payload.name,
        description=payload.description,
    )
    db.add(row)
    await db.flush()
    for account_id in employee_ids:
        team_role = "lead" if account_id == payload.lead_account_id else "staff"
        db.add(
            CorporateTeamMember(
                organization_id=organization_id,
                team_id=row.id,
                account_id=account_id,
                role=team_role,
            )
        )
        db.add(
            CorporateRoleBinding(
                id=new_id("operation"),
                organization_id=organization_id,
                account_id=account_id,
                role=team_role,
                scope_kind="team",
                scope_id=row.id,
                state="active",
            )
        )
    for project_id in dict.fromkeys(payload.project_ids):
        db.add(
            ProjectTeamRelation(
                organization_id=organization_id,
                id=new_id("relation"),
                project_id=project_id,
                team_id=row.id,
                role="contributor",
            )
        )
    for technology_id in dict.fromkeys(payload.technology_ids):
        db.add(
            TechnologyTeamResponsibility(
                organization_id=organization_id,
                id=new_id("relation"),
                technology_id=technology_id,
                team_id=row.id,
            )
        )
    await db.flush()
    organization.policy_revision += 1
    response = await team_view(db, row, ctx=ctx)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="team.create",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="team.create",
        target_table="corporate_team",
        target_id=row.id,
        request_id=request_id,
    )
    return response


async def read_team(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    team_id: str,
    request_id: str | None,
) -> CorporateTeamView:
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="team.read",
        scope_kind="team",
        scope_id=team_id,
    )
    row = await db.scalar(
        select(CorporateTeam).where(
            CorporateTeam.organization_id == organization_id,
            CorporateTeam.id == team_id,
        )
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "team access denied")
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="team.read",
        target_table="corporate_team",
        target_id=team_id,
        request_id=request_id,
    )
    return await team_view(db, row, ctx=ctx, profile=True)


async def update_team(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    team_id: str,
    payload: CorporateTeamUpdateRequest,
    request_id: str | None,
) -> CorporateTeamView:
    fingerprint = mutation_fingerprint(
        payload.model_dump(
            mode="json",
            exclude={"idempotency_key"}
            | ({"description"} if "description" not in payload.model_fields_set else set()),
        )
    )
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="team.update",
        idempotency_key=payload.idempotency_key,
        operation="team.update",
        fingerprint=fingerprint,
        request_id=request_id,
        scope_kind="team",
        scope_id=team_id,
        authorization_revision=payload.authorization_revision,
    )
    if receipt is not None:
        return CorporateTeamView.model_validate(receipt.response_body)
    row = await db.scalar(
        select(CorporateTeam)
        .where(
            CorporateTeam.organization_id == organization_id,
            CorporateTeam.id == team_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "team access denied")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "team revision changed")
    before = {"name": row.name, "state": row.state, "revision": row.revision}
    row.name = payload.name
    if "description" in payload.model_fields_set:
        row.description = payload.description
    row.state = payload.state
    row.revision += 1
    organization.policy_revision += 1
    response = await team_view(db, row, ctx=ctx)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="team.update",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="team.update",
        target_table="corporate_team",
        target_id=team_id,
        request_id=request_id,
        payload={
            "before": before,
            "after": {"name": row.name, "state": row.state, "revision": row.revision},
        },
    )
    return response


async def delete_team(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    team_id: str,
    payload: CorporateDeleteRequest,
    request_id: str | None,
) -> CorporateDeleteResult:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="team.delete",
        idempotency_key=payload.idempotency_key,
        operation="team.delete",
        fingerprint=fingerprint,
        request_id=request_id,
        scope_kind="team",
        scope_id=team_id,
        authorization_revision=payload.authorization_revision,
    )
    if receipt is not None:
        return CorporateDeleteResult.model_validate(receipt.response_body)
    row = await db.scalar(
        select(CorporateTeam)
        .where(
            CorporateTeam.organization_id == organization_id,
            CorporateTeam.id == team_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "team access denied")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "team revision changed")
    before = {"name": row.name, "state": row.state}
    await db.execute(
        delete(CorporateRoleBinding).where(
            CorporateRoleBinding.organization_id == organization_id,
            CorporateRoleBinding.scope_kind == "team",
            CorporateRoleBinding.scope_id == team_id,
        )
    )
    await db.delete(row)
    organization.policy_revision += 1
    response = CorporateDeleteResult(resource_id=team_id)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="team.delete",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="team.delete",
        target_table="corporate_team",
        target_id=team_id,
        request_id=request_id,
        payload={"before": before, "after": None},
    )
    return response


async def create_service_principal(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateServicePrincipalCreateRequest,
    request_id: str | None,
) -> CorporateServicePrincipalView:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="service_principal.manage",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="service_principal.create",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateServicePrincipalView.model_validate(receipt.response_body)
    if (
        await db.scalar(
            select(CorporateRoleRow.name).where(
                CorporateRoleRow.organization_id == organization_id,
                CorporateRoleRow.name == payload.role,
            )
        )
        is None
    ):
        raise ApiError(ErrorCategory.VALIDATION, "corporate role is unavailable")
    if not await _scope_target_exists(
        db,
        organization_id=organization_id,
        scope_kind=payload.scope_kind,
        scope_id=payload.scope_id,
    ):
        raise ApiError(ErrorCategory.PERMISSION, "binding scope denied")
    principal = CorporateServicePrincipal(
        id=new_id("service_principal"), organization_id=organization_id, name=payload.name
    )
    db.add(principal)
    await db.flush()
    binding = CorporateRoleBinding(
        id=new_id("operation"),
        organization_id=organization_id,
        principal_type="service_principal",
        service_principal_id=principal.id,
        role=payload.role,
        scope_kind=payload.scope_kind,
        scope_id=payload.scope_id,
    )
    db.add(binding)
    organization.policy_revision += 1
    await db.flush()
    response = _service_principal_view(principal, binding)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="service_principal.create",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="service_principal.create",
        target_table="corporate_service_principal",
        target_id=principal.id,
        request_id=request_id,
        payload={
            "before": None,
            "after": {"state": principal.state, "binding_state": binding.state},
        },
    )
    return response


async def update_service_principal(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    service_principal_id: str,
    payload: CorporateServicePrincipalUpdateRequest,
    request_id: str | None,
) -> CorporateServicePrincipalView:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="service_principal.manage",
        idempotency_key=payload.idempotency_key,
        operation="service_principal.update",
        fingerprint=fingerprint,
        request_id=request_id,
        authorization_revision=payload.authorization_revision,
    )
    if receipt is not None:
        return CorporateServicePrincipalView.model_validate(receipt.response_body)
    principal = await db.scalar(
        select(CorporateServicePrincipal)
        .where(
            CorporateServicePrincipal.organization_id == organization_id,
            CorporateServicePrincipal.id == service_principal_id,
        )
        .with_for_update()
    )
    binding = await db.scalar(
        select(CorporateRoleBinding).where(
            CorporateRoleBinding.organization_id == organization_id,
            CorporateRoleBinding.service_principal_id == service_principal_id,
        )
    )
    if principal is None or binding is None:
        raise ApiError(ErrorCategory.PERMISSION, "service principal access denied")
    if principal.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "service principal revision changed")
    before = {"state": principal.state, "binding_state": binding.state}
    principal.state = payload.state
    principal.revision += 1
    binding.state = "active" if payload.state == "active" else "revoked"
    binding.revision += 1
    organization.policy_revision += 1
    response = _service_principal_view(principal, binding)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="service_principal.update",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="service_principal.update",
        target_table="corporate_service_principal",
        target_id=principal.id,
        request_id=request_id,
        payload={
            "before": before,
            "after": {"state": principal.state, "binding_state": binding.state},
        },
    )
    return response


async def read_service_principal(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    service_principal_id: str,
    request_id: str | None,
) -> CorporateServicePrincipalView:
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="service_principal.read",
    )
    row = await db.scalar(
        select(CorporateServicePrincipal).where(
            CorporateServicePrincipal.organization_id == organization_id,
            CorporateServicePrincipal.id == service_principal_id,
        )
    )
    binding = await db.scalar(
        select(CorporateRoleBinding).where(
            CorporateRoleBinding.organization_id == organization_id,
            CorporateRoleBinding.service_principal_id == service_principal_id,
        )
    )
    if row is None or binding is None:
        raise ApiError(ErrorCategory.PERMISSION, "service principal access denied")
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="service_principal.read",
        target_table="corporate_service_principal",
        target_id=service_principal_id,
        request_id=request_id,
    )
    return _service_principal_view(row, binding)


async def list_service_principals(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    request_id: str | None,
) -> CorporateServicePrincipalList:
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="service_principal.list",
    )
    rows = list(
        (
            await db.execute(
                select(CorporateServicePrincipal, CorporateRoleBinding)
                .join(
                    CorporateRoleBinding,
                    (
                        CorporateRoleBinding.organization_id
                        == CorporateServicePrincipal.organization_id
                    )
                    & (CorporateRoleBinding.service_principal_id == CorporateServicePrincipal.id),
                )
                .where(CorporateServicePrincipal.organization_id == organization_id)
                .order_by(CorporateServicePrincipal.name, CorporateServicePrincipal.id)
                .limit(256)
            )
        ).all()
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="service_principal.list",
        target_table="corporate_service_principal",
        target_id=organization_id,
        request_id=request_id,
    )
    return CorporateServicePrincipalList(
        items=[_service_principal_view(principal, binding) for principal, binding in rows]
    )


async def delete_service_principal(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    service_principal_id: str,
    payload: CorporateDeleteRequest,
    request_id: str | None,
) -> CorporateDeleteResult:
    fingerprint = mutation_fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="service_principal.delete",
        idempotency_key=payload.idempotency_key,
        operation="service_principal.delete",
        fingerprint=fingerprint,
        request_id=request_id,
        authorization_revision=payload.authorization_revision,
    )
    if receipt is not None:
        return CorporateDeleteResult.model_validate(receipt.response_body)
    row = await db.scalar(
        select(CorporateServicePrincipal)
        .where(
            CorporateServicePrincipal.organization_id == organization_id,
            CorporateServicePrincipal.id == service_principal_id,
        )
        .with_for_update()
    )
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "service principal access denied")
    if row.revision != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "service principal revision changed")
    before = {"name": row.name, "state": row.state}
    await db.execute(
        delete(CorporateRoleBinding).where(
            CorporateRoleBinding.organization_id == organization_id,
            CorporateRoleBinding.service_principal_id == service_principal_id,
        )
    )
    await db.delete(row)
    organization.policy_revision += 1
    response = CorporateDeleteResult(resource_id=service_principal_id)
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="service_principal.delete",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="service_principal.delete",
        target_table="corporate_service_principal",
        target_id=service_principal_id,
        request_id=request_id,
        payload={"before": before, "after": None},
    )
    return response


async def list_teams(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, request_id: str | None
) -> CorporateTeamList:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="organization.read")
    query = select(CorporateTeam).where(CorporateTeam.organization_id == organization_id)
    if not await has_corporate_permission(
        db,
        organization_id=organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        permission="team.list",
        scope_kind="team",
        scope_id="*",
    ):
        query = query.where(
            CorporateTeam.id.in_(
                select(CorporateTeamMember.team_id).where(
                    CorporateTeamMember.organization_id == organization_id,
                    CorporateTeamMember.account_id == ctx.account_id,
                )
            )
            | CorporateTeam.id.in_(
                select(CorporateRoleBinding.scope_id).where(
                    CorporateRoleBinding.organization_id == organization_id,
                    CorporateRoleBinding.account_id == ctx.account_id,
                    CorporateRoleBinding.scope_kind == "team",
                    CorporateRoleBinding.state == "active",
                )
            )
        )
    rows = await db.stream_scalars(
        query.order_by(CorporateTeam.name, CorporateTeam.id).execution_options(yield_per=256)
    )
    visible: list[CorporateTeamView] = []
    async for row in rows:
        assigned = await db.get(CorporateTeamMember, (organization_id, row.id, ctx.account_id))
        if (row.state == "archived" and assigned is not None) or await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=ctx.account_id,
            permission="team.list",
            scope_kind="team",
            scope_id=row.id,
        ):
            visible.append(await team_view(db, row, ctx=ctx))
            if len(visible) == 256:
                break
    await rows.close()
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="team.list",
        target_table="corporate_team",
        target_id=organization_id,
        request_id=request_id,
    )
    return CorporateTeamList(items=visible)


async def assign_member(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateMembershipAssignmentRequest,
    request_id: str | None,
) -> CorporateMembershipAssignment:
    # Authorization revision is a fresh-operation precondition, not an assignment effect.
    fingerprint = mutation_fingerprint(
        payload.model_dump(mode="json", exclude={"idempotency_key", "authorization_revision"})
    )
    operation = f"member.{payload.operation}"
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.manage",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=fingerprint,
        legacy_fingerprint=mutation_fingerprint(
            payload.model_dump(mode="json", exclude={"idempotency_key"})
        ),
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateMembershipAssignment.model_validate(receipt.response_body)
    if payload.team_id is None and payload.project_id is None:
        raise ApiError(ErrorCategory.VALIDATION, "team_id or project_id is required")
    member = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.account_id == payload.account_id,
        )
    )
    if member is None or (payload.operation == "assign" and member.state != "active"):
        raise ApiError(ErrorCategory.PERMISSION, "member access denied")
    bindings: list[CorporateRoleBinding] = []
    before: dict[str, object] = {}
    if payload.team_id is not None:
        team = await db.scalar(
            select(CorporateTeam).where(
                CorporateTeam.organization_id == organization_id,
                CorporateTeam.id == payload.team_id,
            )
        )
        if team is None or (payload.operation == "assign" and team.state != "active"):
            raise ApiError(ErrorCategory.PERMISSION, "team access denied")
        team_member = await db.get(
            CorporateTeamMember, (organization_id, team.id, payload.account_id)
        )
        before["team_role"] = team_member.role if team_member is not None else None
        if payload.operation == "remove":
            if team_member is not None:
                await db.delete(team_member)
        else:
            if team_member is None:
                db.add(
                    CorporateTeamMember(
                        organization_id=organization_id,
                        team_id=team.id,
                        account_id=payload.account_id,
                        role=payload.team_role,
                    )
                )
            else:
                team_member.role = payload.team_role
        active_team_bindings = list(
            (
                await db.scalars(
                    select(CorporateRoleBinding).where(
                        CorporateRoleBinding.organization_id == organization_id,
                        CorporateRoleBinding.account_id == payload.account_id,
                        CorporateRoleBinding.scope_kind == "team",
                        CorporateRoleBinding.scope_id == team.id,
                        CorporateRoleBinding.state == "active",
                    )
                )
            ).all()
        )
        for binding in active_team_bindings:
            binding.state = "revoked"
            binding.revision += 1
        if payload.operation == "assign":
            bindings.append(
                CorporateRoleBinding(
                    id=new_id("operation"),
                    organization_id=organization_id,
                    account_id=payload.account_id,
                    role=payload.team_role,
                    scope_kind="team",
                    scope_id=team.id,
                    state="active",
                )
            )
    if payload.project_id is not None:
        project = await db.scalar(
            select(CorporateProject).where(
                CorporateProject.organization_id == organization_id,
                CorporateProject.id == payload.project_id,
                CorporateProject.state == "active",
            )
        )
        if project is None:
            raise ApiError(ErrorCategory.PERMISSION, "project access denied")
        project_member = await db.get(
            CorporateProjectMember, (organization_id, project.id, payload.account_id)
        )
        before["project_assigned"] = project_member is not None
        if payload.operation == "remove":
            if project_member is not None:
                await db.delete(project_member)
        elif project_member is None:
            db.add(
                CorporateProjectMember(
                    organization_id=organization_id,
                    project_id=project.id,
                    account_id=payload.account_id,
                )
            )
        active_project_bindings = list(
            (
                await db.scalars(
                    select(CorporateRoleBinding).where(
                        CorporateRoleBinding.organization_id == organization_id,
                        CorporateRoleBinding.account_id == payload.account_id,
                        CorporateRoleBinding.scope_kind == "project",
                        CorporateRoleBinding.scope_id == project.id,
                        CorporateRoleBinding.state == "active",
                    )
                )
            ).all()
        )
        for binding in active_project_bindings:
            binding.state = "revoked"
            binding.revision += 1
        if payload.operation == "assign":
            bindings.append(
                CorporateRoleBinding(
                    id=new_id("operation"),
                    organization_id=organization_id,
                    account_id=payload.account_id,
                    role=member.role,
                    scope_kind="project",
                    scope_id=project.id,
                    state="active",
                )
            )
    db.add_all(bindings)
    organization.policy_revision += 1
    await db.flush()
    response = CorporateMembershipAssignment(
        account_id=payload.account_id,
        team_id=payload.team_id,
        project_id=payload.project_id,
        team_role=payload.team_role,
        operation=payload.operation,
        bindings=[_binding_view(row) for row in bindings],
    )
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation=operation,
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action=f"member.{payload.operation}",
        target_table="organization_membership",
        target_id=payload.account_id,
        request_id=request_id,
        payload={
            "before": before,
            "after": {
                "team_role": payload.team_role if payload.operation == "assign" else None,
                "project_assigned": payload.operation == "assign"
                if payload.project_id is not None
                else None,
            },
        },
    )
    return response


async def read_context(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, request_id: str | None
) -> CorporateContext:
    organization, membership = await authorize(
        db, ctx=ctx, organization_id=organization_id, permission="organization.read"
    )
    account = await db.get(Account, ctx.account_id)
    if account is None:
        raise ApiError(ErrorCategory.INTERNAL, "member account is missing")
    bindings = list(
        (
            await db.scalars(
                select(CorporateRoleBinding).where(
                    CorporateRoleBinding.organization_id == organization_id,
                    CorporateRoleBinding.account_id == ctx.account_id,
                    CorporateRoleBinding.state == "active",
                )
            )
        ).all()
    )
    permissions: list[str] = []
    for permission in sorted(KNOWN_PERMISSIONS):
        if await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=ctx.account_id,
            permission=permission,
        ):
            permissions.append(permission)
    project_query = select(CorporateProject).where(
        CorporateProject.organization_id == organization_id
    )
    project_rows = list(
        (await db.scalars(project_query.order_by(CorporateProject.name, CorporateProject.id))).all()
    )
    project_rows = [
        row
        for row in project_rows
        if await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=ctx.account_id,
            permission="project.read",
            scope_kind="project",
            scope_id=row.id,
        )
    ][:256]
    response = CorporateContext(
        organization=organization_view(organization),
        member=member_view(membership, account),
        bindings=[_binding_view(row) for row in bindings],
        projects=[_project_view(row) for row in project_rows],
        teams=(
            await list_teams(db, ctx=ctx, organization_id=organization_id, request_id=request_id)
        ).items,
        capabilities=permissions,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="organization.context.read",
        target_table="organization",
        target_id=organization_id,
        request_id=request_id,
    )
    return response


async def list_audit(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    before_id: int | None,
    before_created_at: str | None,
    actor_account_id: str | None,
    action: str | None,
    target_id: str | None,
    created_from: str | None,
    created_to: str | None,
    request_id: str | None,
) -> CorporateAuditList:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="audit.list")
    audit_time = func.date_trunc("milliseconds", AuditEvent.created_at)
    query = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
    if before_created_at is not None:
        cursor_created_at = datetime.fromisoformat(before_created_at)
        if before_id is None:
            query = query.where(audit_time < cursor_created_at)
        else:
            query = query.where(
                (audit_time < cursor_created_at)
                | ((audit_time == cursor_created_at) & (AuditEvent.id < before_id))
            )
    elif before_id is not None:
        query = query.where(AuditEvent.id < before_id)
    if actor_account_id is not None:
        query = query.where(AuditEvent.actor_account_id == actor_account_id)
    if action is not None:
        query = query.where(AuditEvent.action == action)
    if target_id is not None:
        query = query.where(AuditEvent.target_id == target_id)
    if created_from is not None:
        query = query.where(audit_time >= datetime.fromisoformat(created_from))
    if created_to is not None:
        query = query.where(audit_time <= datetime.fromisoformat(created_to))
    rows = list(
        (await db.scalars(query.order_by(audit_time.desc(), AuditEvent.id.desc()).limit(101))).all()
    )
    page = rows[:100]
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="audit.list",
        target_table="audit_event",
        target_id=organization_id,
        request_id=request_id,
    )
    return CorporateAuditList(
        items=[_audit_entry(row) for row in page],
        next_before_created_at=(_audit_entry(page[-1]).created_at if len(rows) > 100 else None),
        next_before_id=page[-1].id if len(rows) > 100 else None,
    )


def _audit_entry(row: AuditEvent) -> CorporateAuditEntry:
    return CorporateAuditEntry(
        audit_id=row.id,
        actor_account_id=row.actor_account_id,
        actor_type=cast("Literal['user', 'service_principal', 'system']", row.actor_type),
        actor_id=row.actor_id,
        effective_role_bindings=row.effective_role_bindings,
        action=row.action,
        target_table=row.target_table,
        target_id=row.target_id,
        outcome=cast("Literal['succeeded', 'denied', 'failed']", row.outcome),
        reason=row.reason,
        request_id=row.request_id,
        payload=row.payload,
        created_at=format_timestamp(
            row.created_at
            if row.created_at.tzinfo is not None
            else row.created_at.replace(tzinfo=UTC)
        ),
    )


def audit_entry(row: AuditEvent) -> CorporateAuditEntry:
    """Project an audit row for feature services that expose retained history."""
    return _audit_entry(row)


async def export_audit(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    before_id: int | None,
    before_created_at: str | None,
    actor_account_id: str | None,
    action: str | None,
    target_id: str | None,
    created_from: str | None,
    created_to: str | None,
    request_id: str | None,
) -> CorporateAuditExport:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="audit.export")
    audit_time = func.date_trunc("milliseconds", AuditEvent.created_at)
    query = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
    if before_created_at is not None:
        cursor_created_at = datetime.fromisoformat(before_created_at)
        if before_id is None:
            query = query.where(audit_time < cursor_created_at)
        else:
            query = query.where(
                (audit_time < cursor_created_at)
                | ((audit_time == cursor_created_at) & (AuditEvent.id < before_id))
            )
    elif before_id is not None:
        query = query.where(AuditEvent.id < before_id)
    if actor_account_id is not None:
        query = query.where(AuditEvent.actor_account_id == actor_account_id)
    if action is not None:
        query = query.where(AuditEvent.action == action)
    if target_id is not None:
        query = query.where(AuditEvent.target_id == target_id)
    if created_from is not None:
        query = query.where(audit_time >= datetime.fromisoformat(created_from))
    if created_to is not None:
        query = query.where(audit_time <= datetime.fromisoformat(created_to))
    rows = list((await db.scalars(query.order_by(audit_time, AuditEvent.id).limit(10000))).all())
    response = CorporateAuditExport(
        organization_id=organization_id,
        exported_at=format_timestamp(datetime.now(UTC)),
        items=[_audit_entry(row) for row in rows],
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="audit.export",
        target_table="audit_event",
        target_id=organization_id,
        request_id=request_id,
        payload={"count": len(rows)},
    )
    return response
