"""Durable, user-confirmed repository effects with live authority and reconciliation."""

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.session import AuthContext
from ai_stp_api.settings import Settings
from ai_stp_api.slices.github_connector.service import (
    _linked_subject,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_api.slices.publish.service import (
    _require_active_device,  # pyright: ignore[reportPrivateUsage]
)
from ai_stp_contracts.github_connector import (
    GitHubActionConfirmRequest,
    GitHubActionPlanRequest,
    GitHubActionPlanResponse,
    GitHubRepository,
)
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.github_authority import load_connector, require_repository, utc
from ai_stp_platform.github_client import GitHubClient, GitHubError, object_data
from ai_stp_platform.github_models import GitHubActionPlan
from ai_stp_platform.github_sources import request_digest


def response(plan: GitHubActionPlan) -> GitHubActionPlanResponse:
    warning = "repository_access"
    if plan.action == "make_public":
        warning = "repository_and_history_public"
    elif plan.action == "make_private":
        warning = "repository_private"
    elif plan.repository_owner_type == "User" and plan.previous_visibility == "private":
        warning = "personal_repository_write_access"
    return GitHubActionPlanResponse.model_validate(
        {
            "plan_id": plan.id,
            "plan_hash": plan.plan_hash,
            "action": plan.action,
            "actor_id": plan.account_id,
            "device_id": plan.device_id,
            "repository": {
                "installation_id": plan.installation_id,
                "repository_id": plan.repository_id,
                "owner_id": plan.repository_owner_id,
                "full_name": plan.repository_full_name,
                "html_url": f"https://github.com/{plan.repository_full_name}",
                "owner_type": plan.repository_owner_type,
                "private": plan.previous_visibility == "private",
                "can_administer": True,
                "permission": "administration",
            },
            "recipient": plan.recipient,
            "permission": plan.permission,
            "state": plan.state,
            "result": plan.result,
            "error_reason": plan.error_reason,
            "expires_at": format_timestamp(utc(plan.expires_at)),
            "warning": warning,
        }
    )


async def create_plan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    body: GitHubActionPlanRequest,
    settings: Settings,
    client: GitHubClient,
) -> GitHubActionPlanResponse:
    await _require_active_device(db, ctx=ctx, device_id=body.device_id)
    connector, token = await load_connector(
        db,
        account_id=ctx.account_id,
        purpose="administration",
        settings=settings.github_connector,
        lock=True,
    )
    if connector.github_subject != await _linked_subject(db, ctx.account_id):
        raise GitHubError("github_identity_mismatch", status=403)
    repo = await require_repository(
        client,
        token=token,
        purpose="administration",
        settings=settings.github_connector,
        installation_id=body.installation_id,
        repository_id=body.repository_id,
    )
    digest = request_digest(body.model_dump(mode="json", exclude={"idempotency_key"}))
    existing = await db.scalar(
        select(GitHubActionPlan).where(
            GitHubActionPlan.account_id == ctx.account_id,
            GitHubActionPlan.idempotency_key == body.idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != digest:
            raise GitHubError("idempotency_conflict", status=409)
        return response(existing)
    if (
        body.action == "invite_collaborator"
        and repo.owner_type == "User"
        and repo.private
        and body.permission != "push"
    ):
        raise GitHubError("personal_repository_requires_write", status=400)
    expiry = datetime.now(UTC) + timedelta(minutes=10)
    plan = GitHubActionPlan(
        id=str(uuid4()),
        account_id=ctx.account_id,
        device_id=body.device_id,
        connector_id=connector.id,
        authorization_revision=connector.authorization_revision,
        action=body.action,
        installation_id=repo.installation_id,
        repository_id=repo.repository_id,
        repository_owner_id=repo.owner_id,
        repository_owner_type=repo.owner_type,
        repository_full_name=repo.full_name,
        previous_visibility="private" if repo.private else "public",
        recipient=body.recipient,
        permission=body.permission,
        request_hash=digest,
        idempotency_key=body.idempotency_key,
        expires_at=expiry,
        state="planned",
        plan_hash=request_digest(
            {
                "request": digest,
                "actor": ctx.account_id,
                "repository": repo.model_dump(mode="json"),
                "authority": connector.authorization_revision,
                "expires_at": format_timestamp(expiry),
            }
        ),
    )
    db.add(plan)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="github.action_planned",
        target_table="github_action_plan",
        target_id=plan.id,
    )
    return response(plan)


async def _invitation_state(client: GitHubClient, plan: GitHubActionPlan, token: str) -> str | None:
    root = f"/repos/{plan.repository_full_name}"
    check = await client.api(
        "GET",
        f"{root}/collaborators/{plan.recipient}",
        token=token,
        accepted=frozenset({204, 404}),
    )
    if check.status == 204:
        return "accepted"
    for page in range(1, 11):
        reply = await client.api(
            "GET",
            f"{root}/invitations",
            token=token,
            params={"per_page": 100, "page": page},
        )
        data = reply.data
        if not isinstance(data, list) or len(cast(list[object], data)) > 100:
            raise GitHubError("invalid_upstream_response")
        for raw in cast(list[object], data):
            item = object_data(raw)
            invitee = object_data(item.get("invitee"))
            if str(invitee.get("login", "")).lower() == str(plan.recipient).lower():
                return "pending"
        if len(cast(list[object], data)) < 100:
            return None
    raise GitHubError("invitation_scope_too_large", status=400)


def _same_repository(plan: GitHubActionPlan, repo: GitHubRepository) -> None:
    if (
        repo.owner_id != plan.repository_owner_id
        or repo.full_name != plan.repository_full_name
        or repo.owner_type != plan.repository_owner_type
    ):
        raise GitHubError("repository_identity_changed", status=412)
    if plan.action == "invite_collaborator" and repo.private != (
        plan.previous_visibility == "private"
    ):
        raise GitHubError("repository_visibility_changed", status=412)
    if plan.action == "make_public" and plan.previous_visibility == "public" and repo.private:
        raise GitHubError("repository_visibility_changed", status=412)
    if plan.action == "make_private" and plan.previous_visibility == "private" and not repo.private:
        raise GitHubError("repository_visibility_changed", status=412)


async def read_plan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    plan_id: str,
    settings: Settings,
    client: GitHubClient,
) -> GitHubActionPlanResponse:
    connector, token = await load_connector(
        db,
        account_id=ctx.account_id,
        purpose="administration",
        settings=settings.github_connector,
        lock=True,
    )
    plan = await db.scalar(
        select(GitHubActionPlan)
        .where(
            GitHubActionPlan.id == plan_id,
            GitHubActionPlan.account_id == ctx.account_id,
        )
        .with_for_update()
    )
    if plan is None:
        raise GitHubError("action_plan_unavailable", status=404)
    if connector.github_subject != await _linked_subject(db, ctx.account_id):
        raise GitHubError("github_identity_mismatch", status=403)
    repo = await require_repository(
        client,
        token=token,
        purpose="administration",
        settings=settings.github_connector,
        installation_id=plan.installation_id,
        repository_id=plan.repository_id,
    )
    _same_repository(plan, repo)
    if (
        plan.state == "applied"
        and plan.action == "invite_collaborator"
        and plan.result == "pending"
    ):
        client_id, secret, _slug = settings.github_connector.credentials("administration")
        scoped = await client.scoped_token(
            token=token,
            client_id=client_id,
            client_secret=secret,
            owner_id=repo.owner_id,
            repository_id=repo.repository_id,
        )
        current = await _invitation_state(client, plan, scoped)
        if current is not None:
            plan.result = current
        else:
            plan.state, plan.result = "failed", None
            plan.error_reason = "invitation_no_longer_pending"
    return response(plan)


async def confirm(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    plan_id: str,
    body: GitHubActionConfirmRequest,
    settings: Settings,
    client: GitHubClient,
) -> GitHubActionPlanResponse:
    # Connector row is the per-account/purpose serialization point shared with disconnect.
    connector, token = await load_connector(
        db,
        account_id=ctx.account_id,
        purpose="administration",
        settings=settings.github_connector,
        lock=True,
    )
    plan = await db.scalar(
        select(GitHubActionPlan)
        .where(
            GitHubActionPlan.id == plan_id,
            GitHubActionPlan.account_id == ctx.account_id,
        )
        .with_for_update()
    )
    if plan is None:
        raise GitHubError("action_plan_unavailable", status=404)
    await _require_active_device(db, ctx=ctx, device_id=plan.device_id)
    if body.plan_hash != plan.plan_hash:
        raise GitHubError("action_plan_mismatch", status=412)
    if (
        plan.action in {"make_public", "make_private"}
        and body.typed_repository_name != plan.repository_full_name
    ):
        raise GitHubError("exact_repository_name_required", status=400)
    if (
        connector.id != plan.connector_id
        or connector.authorization_revision != plan.authorization_revision
        or connector.github_subject != await _linked_subject(db, ctx.account_id)
    ):
        raise GitHubError("reauthorization_required", status=403)
    repo = await require_repository(
        client,
        token=token,
        purpose="administration",
        settings=settings.github_connector,
        installation_id=plan.installation_id,
        repository_id=plan.repository_id,
    )
    _same_repository(plan, repo)
    if plan.state == "applied":
        return response(plan)
    expired = utc(plan.expires_at) <= datetime.now(UTC)
    if expired and plan.state != "unknown":
        raise GitHubError("action_plan_expired", status=412)
    if plan.state == "failed":
        raise GitHubError("new_action_plan_required", status=412)
    client_id, secret, _slug = settings.github_connector.credentials("administration")
    scoped = await client.scoped_token(
        token=token,
        client_id=client_id,
        client_secret=secret,
        owner_id=repo.owner_id,
        repository_id=repo.repository_id,
    )
    # No broad token is used in a name-addressed mutation: a rename cannot target another repo.
    try:
        result = None
        if plan.action in {"make_public", "make_private"}:
            target_private = plan.action == "make_private"
            result = "private" if target_private else "public"
            if repo.private == target_private:
                pass
            else:
                if expired:
                    raise GitHubError("action_plan_expired", status=412)
                reply = await client.api(
                    "PATCH",
                    f"/repos/{repo.full_name}",
                    token=scoped,
                    body={"visibility": result},
                )
                data = object_data(reply.data)
                if (
                    data.get("id") != repo.repository_id
                    or data.get("private") is not target_private
                ):
                    raise GitHubError("github_action_outcome_unknown")
        else:
            result = await _invitation_state(client, plan, scoped)
            if result is None:
                if expired:
                    raise GitHubError("action_plan_expired", status=412)
                reply = await client.api(
                    "PUT",
                    f"/repos/{repo.full_name}/collaborators/{plan.recipient}",
                    token=scoped,
                    body={"permission": plan.permission},
                )
                result = "accepted" if reply.status == 204 else "pending"
        plan.state, plan.result, plan.error_reason = "applied", result, None
    except GitHubError as error:
        plan.state = (
            "unknown"
            if error.status >= 500 or error.status == 429 or (expired and plan.state == "unknown")
            else "failed"
        )
        plan.error_reason = error.reason
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        action="github.action_completed",
        target_table="github_action_plan",
        target_id=plan.id,
        reason=plan.error_reason,
        payload={"outcome": plan.state, "action": plan.action},
    )
    return response(plan)
