"""Durable, user-confirmed GitLab repository effects with live reconciliation."""

from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_api.slices.corporate import service as corporate_service
from ai_stp_api.slices.gitlab_connector.service import (
    _linked_subjects,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_api.slices.publish.service import (
    _require_active_device,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_contracts.gitlab_connector import (
    GitLabActionConfirmRequest,
    GitLabActionPlanRequest,
    GitLabActionPlanResponse,
)
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.gitlab_authority import load_connector, require_project, utc
from ai_stp_platform.gitlab_client import GitLabClient, GitLabError, GitLabRepository
from ai_stp_platform.gitlab_models import GitLabActionPlan, GitLabConnector
from ai_stp_platform.gitlab_sources import request_digest

_ACCESS_LEVEL = {"guest": 10, "reporter": 20, "developer": 30, "maintainer": 40}

# The organization permission each plan action requires; connect itself only
# needs ``connector.gitlab.use`` — the granulary lives here.
ACTION_PERMISSION: dict[str, str] = {
    "grant_access": "connector.gitlab.access",
    "revoke_access": "connector.gitlab.access",
    "make_public": "connector.gitlab.visibility",
    "make_private": "connector.gitlab.visibility",
    "create_repository": "connector.gitlab.create",
}


def response(plan: GitLabActionPlan) -> GitLabActionPlanResponse:
    warning: Literal[
        "repository_and_history_public",
        "repository_private",
        "repository_internal",
        "repository_access",
        "repository_access_revoked",
        "repository_created",
    ] = "repository_access"
    if plan.action == "make_public":
        warning = "repository_and_history_public"
    elif plan.action == "make_private":
        warning = "repository_private"
    elif plan.action == "revoke_access":
        warning = "repository_access_revoked"
    elif plan.action == "create_repository":
        warning = "repository_created"
    return GitLabActionPlanResponse.model_validate(
        {
            "plan_id": plan.id,
            "plan_hash": plan.plan_hash,
            "action": plan.action,
            "actor_id": plan.account_id,
            "device_id": plan.device_id,
            "gitlab_base_url": plan.gitlab_base_url,
            "project_id": plan.project_id,
            "path_with_namespace": plan.path_with_namespace,
            "previous_visibility": plan.previous_visibility,
            "recipient": plan.recipient,
            "access_level": plan.access_level,
            "name": plan.name,
            "path": plan.path,
            "target_visibility": plan.target_visibility,
            "state": plan.state,
            "result": plan.result,
            "error_reason": plan.error_reason,
            "expires_at": format_timestamp(utc(plan.expires_at)),
            "warning": warning,
        }
    )


async def _admin_connector(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    client: GitLabClient,
    settings: Settings,
) -> tuple[GitLabConnector, str]:
    connector, token = await load_connector(
        db,
        account_id=ctx.account_id,
        gitlab_base_url=client.base_url,
        client=client,
        settings=settings.gitlab,
        purpose="administration",
        lock=True,
    )
    # The route organization is where the action permission was checked, so the
    # grant must have been consented through that same organization's OAuth app.
    if connector.connection_organization_id != organization_id or (
        not settings.gitlab.connector_enabled(connector.connection_organization_id)
    ):
        raise GitLabError("connector_not_configured")
    if connector.gitlab_subject not in await _linked_subjects(db, ctx.account_id):
        raise GitLabError("gitlab_identity_mismatch", status=403)
    return connector, token


async def create_plan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    body: GitLabActionPlanRequest,
    settings: Settings,
    client: GitLabClient,
) -> GitLabActionPlanResponse:
    await corporate_service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=ACTION_PERMISSION[body.action],
    )
    await _require_active_device(db, ctx=ctx, device_id=body.device_id)
    connector, token = await _admin_connector(
        db, ctx=ctx, organization_id=organization_id, client=client, settings=settings
    )
    repository: GitLabRepository | None = None
    recipient_id: int | None = None
    if body.action == "create_repository":
        if not body.name or not body.path or not body.target_visibility:
            raise GitLabError("invalid_action_request", status=400)
    else:
        if body.project_id is None:
            raise GitLabError("invalid_action_request", status=400)
        repository = await require_project(client, token=token, project_id=body.project_id)
        if repository.visibility is None:
            raise GitLabError("invalid_gitlab_response")
        if body.action in {"grant_access", "revoke_access"}:
            if not body.recipient:
                raise GitLabError("invalid_action_request", status=400)
            identity = await client.find_user(body.recipient, token=token)
            if identity is None:
                raise GitLabError("gitlab_recipient_unknown", status=404)
            if f"{identity.user_id}" == connector.gitlab_subject.rpartition(":")[2]:
                raise GitLabError("self_access_change_refused", status=400)
            recipient_id = identity.user_id
    digest = request_digest(body.model_dump(mode="json", exclude={"idempotency_key"}))
    existing = await db.scalar(
        select(GitLabActionPlan).where(
            GitLabActionPlan.account_id == ctx.account_id,
            GitLabActionPlan.idempotency_key == body.idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != digest:
            raise GitLabError("idempotency_conflict", status=409)
        return response(existing)
    expiry = datetime.now(UTC) + timedelta(minutes=10)
    plan = GitLabActionPlan(
        id=str(uuid4()),
        account_id=ctx.account_id,
        device_id=body.device_id,
        connector_id=connector.id,
        gitlab_base_url=client.base_url,
        authorization_revision=connector.authorization_revision,
        action=body.action,
        project_id=None if repository is None else repository.repository_id,
        namespace_id=None if repository is None else repository.namespace_id,
        path_with_namespace=None if repository is None else repository.path_with_namespace,
        previous_visibility=None if repository is None else repository.visibility,
        recipient_id=recipient_id,
        recipient=body.recipient,
        access_level=body.access_level,
        name=body.name,
        path=body.path,
        target_visibility=body.target_visibility,
        request_hash=digest,
        idempotency_key=body.idempotency_key,
        expires_at=expiry,
        state="planned",
        plan_hash=request_digest(
            {
                "request": digest,
                "actor": ctx.account_id,
                "project": None if repository is None else repository.repository_id,
                "path_with_namespace": None
                if repository is None
                else repository.path_with_namespace,
                "recipient_id": recipient_id,
                "authority": connector.authorization_revision,
                "expires_at": format_timestamp(expiry),
            }
        ),
    )
    db.add(plan)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="gitlab.action_planned",
        target_table="gitlab_action_plan",
        target_id=plan.id,
        payload={"action": plan.action},
    )
    return response(plan)


async def _load_plan(db: AsyncSession, *, ctx: AuthContext, plan_id: str) -> GitLabActionPlan:
    plan = await db.scalar(
        select(GitLabActionPlan)
        .where(
            GitLabActionPlan.id == plan_id,
            GitLabActionPlan.account_id == ctx.account_id,
        )
        .with_for_update()
    )
    if plan is None:
        raise GitLabError("action_plan_unavailable", status=404)
    return plan


def _same_project(plan: GitLabActionPlan, repository: GitLabRepository) -> None:
    if (
        repository.namespace_id != plan.namespace_id
        or repository.path_with_namespace != plan.path_with_namespace
    ):
        raise GitLabError("repository_identity_changed", status=412)
    if plan.action in {"grant_access", "revoke_access"} and (
        repository.visibility != plan.previous_visibility
    ):
        raise GitLabError("repository_visibility_changed", status=412)
    target = {"make_public": "public", "make_private": "private"}.get(plan.action)
    # Replay safety: after the plan applied, the repository legitimately sits at
    # the target visibility — only a drift to a third state is a changed plan.
    if (
        target is not None
        and repository.visibility != plan.previous_visibility
        and repository.visibility != target
    ):
        raise GitLabError("repository_visibility_changed", status=412)


async def read_plan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    plan_id: str,
    settings: Settings,
    client: GitLabClient,
) -> GitLabActionPlanResponse:
    plan = await _load_plan(db, ctx=ctx, plan_id=plan_id)
    await corporate_service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=ACTION_PERMISSION[plan.action],
    )
    await _admin_connector(
        db, ctx=ctx, organization_id=organization_id, client=client, settings=settings
    )
    return response(plan)


async def confirm(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    plan_id: str,
    body: GitLabActionConfirmRequest,
    settings: Settings,
    client: GitLabClient,
) -> GitLabActionPlanResponse:
    plan = await _load_plan(db, ctx=ctx, plan_id=plan_id)
    await corporate_service.authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=ACTION_PERMISSION[plan.action],
    )
    connector, token = await _admin_connector(
        db, ctx=ctx, organization_id=organization_id, client=client, settings=settings
    )
    await _require_active_device(db, ctx=ctx, device_id=plan.device_id)
    if body.plan_hash != plan.plan_hash:
        raise GitLabError("action_plan_mismatch", status=412)
    if (
        plan.action in {"make_public", "make_private"}
        and body.typed_project_path != plan.path_with_namespace
    ):
        raise GitLabError("exact_project_path_required", status=400)
    if (
        connector.id != plan.connector_id
        or connector.authorization_revision != plan.authorization_revision
    ):
        raise GitLabError("reauthorization_required", status=403)
    repository: GitLabRepository | None = None
    if plan.action != "create_repository":
        if plan.project_id is None:
            raise GitLabError("action_plan_unavailable", status=404)
        repository = await require_project(client, token=token, project_id=plan.project_id)
        _same_project(plan, repository)
    if plan.state == "applied":
        return response(plan)
    expired = utc(plan.expires_at) <= datetime.now(UTC)
    if expired and plan.state != "unknown":
        raise GitLabError("action_plan_expired", status=412)
    if plan.state == "failed":
        raise GitLabError("new_action_plan_required", status=412)
    try:
        result = None
        if plan.action in {"make_public", "make_private"}:
            target = "private" if plan.action == "make_private" else "public"
            if repository is not None and repository.visibility == target:
                result = target
            else:
                if expired:
                    raise GitLabError("action_plan_expired", status=412)
                updated = await client.set_visibility(
                    cast(int, plan.project_id), target, token=token
                )
                result = cast(str, updated.visibility)
        elif plan.action in {"grant_access", "revoke_access"}:
            if expired:
                raise GitLabError("action_plan_expired", status=412)
            if plan.recipient_id is None:
                raise GitLabError("action_plan_unavailable", status=404)
            # Retried confirmations and ``unknown`` plans reach here again, so
            # the upstream "already there" answers collapse onto the result.
            if plan.action == "grant_access":
                try:
                    await client.add_member(
                        cast(int, plan.project_id),
                        plan.recipient_id,
                        _ACCESS_LEVEL[cast(str, plan.access_level)],
                        token=token,
                    )
                except GitLabError as error:
                    if error.reason != "gitlab_action_conflict":
                        raise
                result = "granted"
            else:
                try:
                    await client.remove_member(
                        cast(int, plan.project_id), plan.recipient_id, token=token
                    )
                except GitLabError as error:
                    if error.reason != "gitlab_repository_inaccessible":
                        raise
                result = "revoked"
        else:
            if expired:
                raise GitLabError("action_plan_expired", status=412)
            created = await client.create_project(
                cast(str, plan.name),
                cast(str, plan.path),
                cast(str, plan.target_visibility),
                token=token,
            )
            plan.project_id = created.repository_id
            plan.namespace_id = created.namespace_id
            plan.path_with_namespace = created.path_with_namespace
            result = "created"
        plan.state, plan.result, plan.error_reason = "applied", result, None
    except GitLabError as error:
        plan.state = (
            "unknown"
            if error.status >= 500 or error.status == 429 or (expired and plan.state == "unknown")
            else "failed"
        )
        plan.error_reason = error.reason
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="gitlab.action_completed",
        target_table="gitlab_action_plan",
        target_id=plan.id,
        reason=plan.error_reason,
        payload={"outcome": plan.state, "action": plan.action},
    )
    return response(plan)
