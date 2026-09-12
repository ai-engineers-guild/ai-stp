"""Corporate bootstrap, authorization, projects, and audit scenarios."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.auth.domain import normalize_email
from ai_stp_contracts.corporate import (
    CorporateAuditEntry,
    CorporateAuditExport,
    CorporateAuditList,
    CorporateBinding,
    CorporateBindingList,
    CorporateBindingRequest,
    CorporateBindingUpdateRequest,
    CorporateBootstrapRequest,
    CorporateContext,
    CorporateDeleteRequest,
    CorporateDeleteResult,
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
    CorporateRoleCreateRequest,
    CorporateRoleList,
    CorporateRoleUpdateRequest,
    CorporateRoleView,
    CorporateServicePrincipalCreateRequest,
    CorporateServicePrincipalList,
    CorporateServicePrincipalUpdateRequest,
    CorporateServicePrincipalView,
    CorporateState,
    CorporateTeamCreateRequest,
    CorporateTeamList,
    CorporateTeamUpdateRequest,
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
        }
    ),
    "lead": frozenset(
        {
            "organization.read",
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

_ROLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_BUILT_IN_ROLES: frozenset[str] = frozenset(ROLE_PERMISSIONS)
_KNOWN_PERMISSIONS: frozenset[str] = frozenset(
    permission for permissions in ROLE_PERMISSIONS.values() for permission in permissions
)


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
        role=row.role,
        state=cast(CorporateState, row.state),
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


async def _effective_role_permissions(
    db: AsyncSession, *, organization_id: str, roles: set[str]
) -> list[str]:
    if not roles:
        return []
    role_rows = list(
        (
            await db.scalars(
                select(CorporateRoleRow).where(CorporateRoleRow.organization_id == organization_id)
            )
        ).all()
    )
    parents = {row.name: row.parent_role for row in role_rows}
    permission_rows = list(
        (
            await db.scalars(
                select(CorporateRolePermission).where(
                    CorporateRolePermission.organization_id == organization_id
                )
            )
        ).all()
    )
    direct: dict[str, set[str]] = {}
    for row in permission_rows:
        direct.setdefault(row.role, set()).add(row.permission)
    effective: set[str] = set()
    for role in roles:
        current: str | None = role
        seen: set[str] = set()
        while current is not None and current not in seen and len(seen) < 32:
            seen.add(current)
            effective.update(direct.get(current, ()))
            current = parents.get(current)
    return sorted(effective)


def _role_permissions(payload: list[str]) -> list[str]:
    permissions = sorted(set(payload))
    if any(permission not in _KNOWN_PERMISSIONS for permission in permissions):
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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
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
    await db.flush()
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
    # Technology, catalog-object, telemetry, and system resources have no
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
    request_id: str | None = None,
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
    if authorization_revision != organization.policy_revision:
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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
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
    await _store_receipt(
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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
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
    await _store_receipt(
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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
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
    await _store_receipt(
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
        request_id=request_id,
    )
    if receipt is not None:
        return CorporateMember.model_validate(receipt.response_body)
    await _ensure_role_exists(db, organization_id=organization_id, role=payload.role)
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
    db.add(membership)
    await db.flush()
    db.add(binding)
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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.update",
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
    await _ensure_role_exists(db, organization_id=organization_id, role=payload.role)
    before = {"role": row.role, "state": row.state, "revision": row.revision}
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
    response = _member_view(row, account)
    await _store_receipt(
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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.delete",
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
    await _store_receipt(
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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
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
    await _store_receipt(
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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
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
    await _store_receipt(
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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
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
    row = CorporateProject(
        id=new_id("remote_project"), organization_id=organization_id, name=payload.name
    )
    db.add(row)
    await db.flush()
    organization.policy_revision += 1
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
    return _project_view(row)


async def update_project(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    payload: CorporateProjectUpdateRequest,
    request_id: str | None,
) -> CorporateProjectView:
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.update",
        idempotency_key=payload.idempotency_key,
        operation="project.update",
        fingerprint=fingerprint,
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
    before = {"name": row.name, "state": row.state, "revision": row.revision}
    row.name = payload.name
    row.state = payload.state
    row.revision += 1
    organization.policy_revision += 1
    response = _project_view(row)
    await _store_receipt(
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


async def delete_project(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    payload: CorporateDeleteRequest,
    request_id: str | None,
) -> CorporateDeleteResult:
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project.delete",
        idempotency_key=payload.idempotency_key,
        operation="project.delete",
        fingerprint=fingerprint,
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
    before = {"name": row.name, "state": row.state}
    await db.execute(
        delete(CorporateRoleBinding).where(
            CorporateRoleBinding.organization_id == organization_id,
            CorporateRoleBinding.scope_kind == "project",
            CorporateRoleBinding.scope_id == project_id,
        )
    )
    await db.delete(row)
    organization.policy_revision += 1
    response = CorporateDeleteResult(resource_id=project_id)
    await _store_receipt(
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
        payload={"before": before, "after": None},
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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
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
    row = CorporateTeam(id=new_id("operation"), organization_id=organization_id, name=payload.name)
    db.add(row)
    await db.flush()
    organization.policy_revision += 1
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
    return _team_view(row)


async def update_team(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    team_id: str,
    payload: CorporateTeamUpdateRequest,
    request_id: str | None,
) -> CorporateTeamView:
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
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
    row.state = payload.state
    row.revision += 1
    organization.policy_revision += 1
    response = _team_view(row)
    await _store_receipt(
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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
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
    await _store_receipt(
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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
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
    await _store_receipt(
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
    fingerprint = _fingerprint(payload.model_dump(mode="json", exclude={"idempotency_key"}))
    organization, receipt = await _authorize_idempotent(
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
    await _store_receipt(
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
            OrganizationMembership.state == "active",
        )
    )
    if member is None:
        raise ApiError(ErrorCategory.PERMISSION, "member access denied")
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
    permissions = await _effective_role_permissions(
        db,
        organization_id=organization_id,
        roles={row.role for row in bindings},
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
    before_created_at: str | None,
    actor_account_id: str | None,
    action: str | None,
    target_id: str | None,
    created_from: str | None,
    created_to: str | None,
    request_id: str | None,
) -> CorporateAuditList:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="audit.list")
    query = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
    if before_created_at is not None:
        cursor_created_at = datetime.fromisoformat(before_created_at)
        if before_id is None:
            query = query.where(AuditEvent.created_at < cursor_created_at)
        else:
            query = query.where(
                (AuditEvent.created_at < cursor_created_at)
                | ((AuditEvent.created_at == cursor_created_at) & (AuditEvent.id < before_id))
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
        query = query.where(AuditEvent.created_at >= datetime.fromisoformat(created_from))
    if created_to is not None:
        query = query.where(AuditEvent.created_at <= datetime.fromisoformat(created_to))
    rows = list(
        (
            await db.scalars(
                query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(101)
            )
        ).all()
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
    query = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
    if before_created_at is not None:
        cursor_created_at = datetime.fromisoformat(before_created_at)
        if before_id is None:
            query = query.where(AuditEvent.created_at < cursor_created_at)
        else:
            query = query.where(
                (AuditEvent.created_at < cursor_created_at)
                | ((AuditEvent.created_at == cursor_created_at) & (AuditEvent.id < before_id))
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
        query = query.where(AuditEvent.created_at >= datetime.fromisoformat(created_from))
    if created_to is not None:
        query = query.where(AuditEvent.created_at <= datetime.fromisoformat(created_to))
    rows = list(
        (await db.scalars(query.order_by(AuditEvent.created_at, AuditEvent.id).limit(10000))).all()
    )
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
