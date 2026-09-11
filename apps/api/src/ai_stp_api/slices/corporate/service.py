"""Corporate bootstrap, authorization, projects, and audit scenarios."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.auth.domain import normalize_email
from ai_stp_contracts.corporate import (
    CorporateAuditEntry,
    CorporateAuditList,
    CorporateBinding,
    CorporateBindingRequest,
    CorporateBootstrapRequest,
    CorporateContext,
    CorporateMember,
    CorporateMemberCreateRequest,
    CorporateMemberList,
    CorporateMembershipAssignment,
    CorporateMembershipAssignmentRequest,
    CorporateMemberUpdateRequest,
    CorporateOrganization,
    CorporateProjectCreateRequest,
    CorporateProjectList,
    CorporateProjectUpdateRequest,
    CorporateProjectView,
    CorporateRole,
    CorporateServicePrincipalCreateRequest,
    CorporateServicePrincipalUpdateRequest,
    CorporateServicePrincipalView,
    CorporateState,
    CorporateTeamCreateRequest,
    CorporateTeamList,
    CorporateTeamView,
    ProjectState,
    ScopeKind,
)
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.models import Account, AuditEvent
from ai_stp_platform.organization_models import (
    CorporateBootstrapReceipt,
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
)
from ai_stp_platform.organization_models import (
    CorporateRole as CorporateRoleRow,
)
from ai_stp_platform.tenant_scope import set_tenant_scope

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
            "project.create",
            "project.read",
            "project.update",
            "project.delete",
            "project.list",
            "team.create",
            "team.read",
            "team.update",
            "team.list",
            "audit.read",
            "audit.list",
            "service_principal.manage",
        }
    ),
    "lead": frozenset(
        {
            "organization.read",
            "member.read",
            "member.list",
            "project.create",
            "project.read",
            "project.update",
            "project.list",
            "team.read",
            "team.list",
        }
    ),
    "staff": frozenset(
        {"organization.read", "project.read", "project.list", "team.read", "team.list"}
    ),
}


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _organization_view(row: Organization) -> CorporateOrganization:
    return CorporateOrganization(
        organization_id=row.id,
        display_name=row.display_name,
        state=cast(CorporateState, row.state),
        authorization_revision=row.policy_revision,
    )


def _member_view(row: OrganizationMembership, account: Account) -> CorporateMember:
    return CorporateMember(
        account_id=row.account_id,
        display_name=account.display_name,
        role=cast(CorporateRole, row.role),
        state=cast(CorporateState, row.state),
        revision=row.revision,
    )


def _binding_view(row: CorporateRoleBinding) -> CorporateBinding:
    return CorporateBinding(
        binding_id=row.id,
        principal_type=cast("Literal['user', 'service_principal']", row.principal_type),
        account_id=row.account_id,
        service_principal_id=row.service_principal_id,
        role=cast(CorporateRole, row.role),
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
        revision=row.revision,
    )


def _team_view(row: CorporateTeam) -> CorporateTeamView:
    return CorporateTeamView(
        team_id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        state=cast("Literal['active', 'archived']", row.state),
        revision=row.revision,
    )


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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    receipt = await db.get(CorporateBootstrapReceipt, payload.idempotency_key)
    if receipt is not None:
        if receipt.request_fingerprint != fingerprint:
            raise ApiError(ErrorCategory.CONFLICT, "bootstrap idempotency key was reused")
        organization = await db.get(Organization, receipt.organization_id)
        if organization is None:
            raise ApiError(ErrorCategory.INTERNAL, "bootstrap receipt is invalid")
        return _organization_view(organization)
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
    db.add_all(
        (
            CorporateRoleRow(organization_id=organization.id, name="superadmin", parent_role=None),
            CorporateRoleRow(
                organization_id=organization.id, name="lead", parent_role="superadmin"
            ),
            CorporateRoleRow(organization_id=organization.id, name="staff", parent_role="lead"),
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
    return _organization_view(organization)


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


async def authorize(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    permission: str,
    scope_kind: str = "organization",
    scope_id: str | None = None,
    authorization_revision: int | None = None,
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
    allowed = await has_corporate_permission(
        db,
        organization_id=organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        permission=permission,
        scope_kind=scope_kind,
        scope_id=scope,
    )
    if not allowed:
        raise ApiError(ErrorCategory.PERMISSION, "capability is forbidden")
    return organization, membership


async def _store_receipt(
    db: AsyncSession,
    *,
    organization_id: str,
    key: str,
    operation: str,
    fingerprint: str,
    response: BaseModel,
) -> None:
    db.add(
        CorporateMutationReceipt(
            organization_id=organization_id,
            idempotency_key=key,
            operation=operation,
            request_fingerprint=fingerprint,
            response_body=response.model_dump(mode="json"),
        )
    )


async def _authorize_idempotent(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    permission: str,
    authorization_revision: int,
    idempotency_key: str,
    operation: str,
    fingerprint: str,
    scope_kind: str = "organization",
    scope_id: str | None = None,
) -> tuple[Organization, CorporateMutationReceipt | None]:
    organization, _ = await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=permission,
        scope_kind=scope_kind,
        scope_id=scope_id,
    )
    receipt = await db.get(CorporateMutationReceipt, (organization_id, idempotency_key))
    if receipt is not None:
        if receipt.operation != operation or receipt.request_fingerprint != fingerprint:
            raise ApiError(ErrorCategory.CONFLICT, "idempotency key was reused")
        return organization, receipt
    if authorization_revision != organization.policy_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "capability revision is stale")
    return organization, None


async def create_member(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateMemberCreateRequest,
    request_id: str | None,
) -> CorporateMember:
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.create",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="member.create",
        fingerprint=fingerprint,
    )
    if receipt is not None:
        return CorporateMember.model_validate(receipt.response_body)
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
        role=payload.role,
        state="active",
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
    db.add_all((membership, binding))
    organization.policy_revision += 1
    await db.flush()
    response = _member_view(membership, account)
    await _store_receipt(
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
    return CorporateMemberList(items=[_member_view(member, account) for member, account in rows])


async def update_member(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    account_id: str,
    payload: CorporateMemberUpdateRequest,
    request_id: str | None,
) -> CorporateMember:
    organization, _ = await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.update",
        authorization_revision=payload.authorization_revision,
    )
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
    row.revision += 1
    bindings = list(
        (
            await db.scalars(
                select(CorporateRoleBinding).where(
                    CorporateRoleBinding.organization_id == organization_id,
                    CorporateRoleBinding.account_id == account_id,
                    CorporateRoleBinding.scope_kind.in_(("organization", "project")),
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
    account = await db.get(Account, account_id)
    if account is None:
        raise ApiError(ErrorCategory.INTERNAL, "member account is missing")
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="member.update",
        target_table="organization_membership",
        target_id=account_id,
        request_id=request_id,
    )
    return _member_view(row, account)


async def read_member(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    account_id: str,
    request_id: str | None,
) -> CorporateMember:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="member.read")
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
    return _member_view(*row)


async def create_binding(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateBindingRequest,
    request_id: str | None,
) -> CorporateBinding:
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.manage",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="binding.create",
        fingerprint=fingerprint,
    )
    if receipt is not None:
        return CorporateBinding.model_validate(receipt.response_body)
    member = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.account_id == payload.account_id,
            OrganizationMembership.state == "active",
        )
    )
    if member is None:
        raise ApiError(ErrorCategory.PERMISSION, "member access denied")
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
    await _store_receipt(
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


async def create_project(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateProjectCreateRequest,
    request_id: str | None,
) -> CorporateProjectView:
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    _, receipt = await _authorize_idempotent(
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
    )
    if receipt is not None:
        return CorporateProjectView.model_validate(receipt.response_body)
    row = CorporateProject(
        id=new_id("remote_project"), organization_id=organization_id, name=payload.name
    )
    db.add(row)
    await db.flush()
    response = _project_view(row)
    await _store_receipt(
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


async def update_project(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    payload: CorporateProjectUpdateRequest,
    request_id: str | None,
) -> CorporateProjectView:
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.update",
        scope_kind="project",
        scope_id=project_id,
        authorization_revision=payload.authorization_revision,
    )
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
    row.name = payload.name
    row.state = payload.state
    row.revision += 1
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.update",
        target_table="corporate_project",
        target_id=row.id,
        request_id=request_id,
    )
    return _project_view(row)


async def create_team(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateTeamCreateRequest,
    request_id: str | None,
) -> CorporateTeamView:
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    _, receipt = await _authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="team.create",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="team.create",
        fingerprint=fingerprint,
    )
    if receipt is not None:
        return CorporateTeamView.model_validate(receipt.response_body)
    row = CorporateTeam(id=new_id("operation"), organization_id=organization_id, name=payload.name)
    db.add(row)
    await db.flush()
    response = _team_view(row)
    await _store_receipt(
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


async def create_service_principal(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateServicePrincipalCreateRequest,
    request_id: str | None,
) -> CorporateServicePrincipalView:
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="service_principal.manage",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="service_principal.create",
        fingerprint=fingerprint,
    )
    if receipt is not None:
        return CorporateServicePrincipalView.model_validate(receipt.response_body)
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
    await _store_receipt(
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
    organization, _ = await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="service_principal.manage",
        authorization_revision=payload.authorization_revision,
    )
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
    return _service_principal_view(principal, binding)


async def list_teams(
    db: AsyncSession, *, ctx: AuthContext, organization_id: str, request_id: str | None
) -> CorporateTeamList:
    _, membership = await authorize(
        db, ctx=ctx, organization_id=organization_id, permission="team.list"
    )
    query = select(CorporateTeam).where(CorporateTeam.organization_id == organization_id)
    if membership.role != "superadmin":
        query = query.join(
            CorporateTeamMember,
            (CorporateTeamMember.organization_id == CorporateTeam.organization_id)
            & (CorporateTeamMember.team_id == CorporateTeam.id),
        ).where(CorporateTeamMember.account_id == ctx.account_id)
    rows = list(
        (await db.scalars(query.order_by(CorporateTeam.name, CorporateTeam.id).limit(256))).all()
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="team.list",
        target_table="corporate_team",
        target_id=organization_id,
        request_id=request_id,
    )
    return CorporateTeamList(items=[_team_view(row) for row in rows])


async def assign_member(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: CorporateMembershipAssignmentRequest,
    request_id: str | None,
) -> CorporateMembershipAssignment:
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    operation = f"member.{payload.operation}"
    organization, receipt = await _authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.manage",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=fingerprint,
    )
    if payload.team_id is None and payload.project_id is None:
        raise ApiError(ErrorCategory.VALIDATION, "team_id or project_id is required")
    member = await db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.account_id == payload.account_id,
            OrganizationMembership.state == "active",
        )
    )
    if member is None:
        raise ApiError(ErrorCategory.PERMISSION, "member access denied")
    if receipt is not None:
        return CorporateMembershipAssignment.model_validate(receipt.response_body)
    bindings: list[CorporateRoleBinding] = []
    before: dict[str, object] = {}
    if payload.team_id is not None:
        team = await db.scalar(
            select(CorporateTeam).where(
                CorporateTeam.organization_id == organization_id,
                CorporateTeam.id == payload.team_id,
                CorporateTeam.state == "active",
            )
        )
        if team is None:
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
    await _store_receipt(
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
    permissions = sorted(
        set(
            (
                await db.scalars(
                    select(CorporateRolePermission.permission)
                    .join(
                        CorporateRoleBinding,
                        (
                            CorporateRoleBinding.organization_id
                            == CorporateRolePermission.organization_id
                        )
                        & (CorporateRoleBinding.role == CorporateRolePermission.role),
                    )
                    .where(
                        CorporateRoleBinding.organization_id == organization_id,
                        CorporateRoleBinding.account_id == ctx.account_id,
                        CorporateRoleBinding.state == "active",
                    )
                )
            ).all()
        )
    )
    project_query = select(CorporateProject).where(
        CorporateProject.organization_id == organization_id
    )
    team_query = select(CorporateTeam).where(CorporateTeam.organization_id == organization_id)
    if membership.role != "superadmin":
        project_query = project_query.join(
            CorporateProjectMember,
            (CorporateProjectMember.organization_id == CorporateProject.organization_id)
            & (CorporateProjectMember.project_id == CorporateProject.id),
        ).where(CorporateProjectMember.account_id == ctx.account_id)
        team_query = team_query.join(
            CorporateTeamMember,
            (CorporateTeamMember.organization_id == CorporateTeam.organization_id)
            & (CorporateTeamMember.team_id == CorporateTeam.id),
        ).where(CorporateTeamMember.account_id == ctx.account_id)
    project_rows = list(
        (await db.scalars(project_query.order_by(CorporateProject.name).limit(256))).all()
    )
    team_rows = list((await db.scalars(team_query.order_by(CorporateTeam.name).limit(256))).all())
    response = CorporateContext(
        organization=_organization_view(organization),
        member=_member_view(membership, account),
        bindings=[_binding_view(row) for row in bindings],
        projects=[_project_view(row) for row in project_rows],
        teams=[_team_view(row) for row in team_rows],
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
    actor_account_id: str | None,
    action: str | None,
    target_id: str | None,
    created_from: str | None,
    created_to: str | None,
    request_id: str | None,
) -> CorporateAuditList:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="audit.list")
    query = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
    if before_id is not None:
        query = query.where(AuditEvent.id < before_id)
    if actor_account_id is not None:
        query = query.where(AuditEvent.actor_account_id == actor_account_id)
    if action is not None:
        query = query.where(AuditEvent.action == action)
    if target_id is not None:
        query = query.where(AuditEvent.target_id == target_id)
    if created_from is not None:
        query = query.where(AuditEvent.created_at >= datetime.fromisoformat(created_from))
    if created_to is not None:
        query = query.where(AuditEvent.created_at <= datetime.fromisoformat(created_to))
    rows = list((await db.scalars(query.order_by(AuditEvent.id.desc()).limit(101))).all())
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
        items=[
            CorporateAuditEntry(
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
                created_at=format_timestamp(
                    row.created_at
                    if row.created_at.tzinfo is not None
                    else row.created_at.replace(tzinfo=UTC)
                ),
            )
            for row in page
        ],
        next_before_id=page[-1].id if len(rows) > 100 else None,
    )
