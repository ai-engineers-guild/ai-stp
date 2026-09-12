"""Governed registry and canonical relation mutations (SPEC-080/081)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import BaseModel
from sqlalchemy import delete, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import (
    authorize,
    authorize_idempotent,
    mutation_fingerprint,
    store_mutation_receipt,
)
from ai_stp_contracts.technology import (
    CategoryList,
    CategoryView,
    CategoryWriteRequest,
    LandscapeProjectView,
    ProjectTeamList,
    ProjectTeamView,
    ProjectTeamWriteRequest,
    ProjectTechnologyList,
    ProjectTechnologyView,
    ProjectTechnologyWriteRequest,
    TechnologyDecisionRequest,
    TechnologyDecisionView,
    TechnologyLandscapeQuery,
    TechnologyLandscapeRow,
    TechnologyLandscapeView,
    TechnologyLifecycleRequest,
    TechnologyList,
    TechnologyMutation,
    TechnologyTeamList,
    TechnologyTeamView,
    TechnologyTeamWriteRequest,
    TechnologyView,
    TechnologyWriteRequest,
    normalize_technology_name,
)
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp
from ai_stp_platform.corporate_authorization import has_corporate_permission
from ai_stp_platform.organization_models import (
    CorporateProject,
    CorporateTeam,
    OrganizationMembership,
    ProjectIdentity,
)
from ai_stp_platform.technology_landscape import project_activity
from ai_stp_platform.technology_models import (
    OrganizationTechnologyDecision,
    ProjectTeamRelation,
    ProjectTechnologyRelation,
    Technology,
    TechnologyAlias,
    TechnologyCategory,
    TechnologyClassification,
    TechnologyLandscapePolicy,
    TechnologyTeamResponsibility,
    TechnologyUsageFact,
)


async def read_landscape(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    filters: TechnologyLandscapeQuery,
    request_id: str | None,
    now: datetime | None = None,
) -> TechnologyLandscapeView:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="landscape.read")
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="technology.list")
    evaluated_at = now or datetime.now(UTC)
    policy = await db.get(TechnologyLandscapePolicy, organization_id)
    months = policy.inactivity_months if policy else 9
    technologies = list(
        (
            await db.scalars(
                select(Technology)
                .where(Technology.organization_id == organization_id)
                .order_by(Technology.name, Technology.id)
            )
        ).all()
    )
    projects = {
        row.id: row
        for row in (
            await db.scalars(
                select(CorporateProject)
                .join(
                    ProjectIdentity,
                    (ProjectIdentity.organization_id == CorporateProject.organization_id)
                    & (ProjectIdentity.id == CorporateProject.id)
                    & (ProjectIdentity.namespace == "remote"),
                )
                .where(
                    CorporateProject.organization_id == organization_id,
                    ProjectIdentity.state == "active" if not filters.include_history else true(),
                )
            )
        ).all()
    }
    team_projects: set[str] | None = None
    if filters.team_id is not None:
        await authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission="team.read",
            scope_kind="team",
            scope_id=filters.team_id,
        )
        team_projects = set(
            (
                await db.scalars(
                    select(ProjectTeamRelation.project_id)
                    .join(
                        CorporateTeam,
                        (CorporateTeam.organization_id == ProjectTeamRelation.organization_id)
                        & (CorporateTeam.id == ProjectTeamRelation.team_id),
                    )
                    .where(
                        ProjectTeamRelation.organization_id == organization_id,
                        ProjectTeamRelation.team_id == filters.team_id,
                        ProjectTeamRelation.state == "current",
                        CorporateTeam.state == "active",
                    )
                )
            ).all()
        )
    relations = list(
        (
            await db.scalars(
                select(ProjectTechnologyRelation)
                .where(ProjectTechnologyRelation.organization_id == organization_id)
                .order_by(ProjectTechnologyRelation.project_id)
            )
        ).all()
    )
    rows: list[TechnologyLandscapeRow] = []
    # ponytail: O(technologies * relations) and per-row policy reads; batch for large tenants.
    for technology in technologies:
        if technology.redirect_id or (
            not filters.include_history and technology.lifecycle == "archived"
        ):
            continue
        if filters.technology_id and technology.id != filters.technology_id:
            continue
        if filters.lifecycle and technology.lifecycle != filters.lifecycle:
            continue
        if not await _readable(
            db, ctx, organization_id, "technology.read", "technology", technology.id
        ):
            continue
        metadata = await technology_view(db, technology)
        if filters.category_id and filters.category_id not in metadata.category_ids:
            continue
        if filters.adoption is not None:
            if not await _readable(
                db, ctx, organization_id, "technology_decision.read", "technology", technology.id
            ):
                continue
            decision = await db.get(
                OrganizationTechnologyDecision, (organization_id, technology.id)
            )
            if (decision.adoption if decision else "none") != filters.adoption:
                continue
        matched: list[LandscapeProjectView] = []
        proposals: set[str] = set()
        for relation in relations:
            if relation.technology_id != technology.id:
                continue
            project = projects.get(relation.project_id)
            if project is None or (filters.project_id and project.id != filters.project_id):
                continue
            if team_projects is not None and project.id not in team_projects:
                continue
            if not filters.include_history and (
                project.state != "active" or relation.state != "current"
            ):
                continue
            if not all(
                [
                    await _readable(db, ctx, organization_id, permission, "project", project.id)
                    for permission in (
                        "project.read",
                        "project_technology.list",
                        "project_technology.read",
                    )
                ]
            ):
                continue
            activity = project_activity(
                project.repository_activity_at,
                now=evaluated_at,
                inactivity_months=months,
                override=cast(Literal["active", "inactive"] | None, project.activity_override),
            )
            if activity == "inactive" and not filters.include_inactive:
                continue
            usage = await project_technology_view(db, relation)
            facts = [
                fact
                for fact in usage.facts
                if (filters.context is None or fact.context == filters.context)
                and (
                    fact.freshness == filters.freshness
                    if filters.freshness
                    else fact.freshness != "absent"
                )
            ]
            if any(fact.review == "proposed" for fact in facts):
                proposals.add(project.id)
            selected = [
                fact
                for fact in facts
                if (
                    fact.review == filters.review
                    if filters.review
                    else fact.review in ("confirmed", "overridden")
                )
            ]
            if selected:
                matched.append(
                    LandscapeProjectView(
                        project_id=project.id,
                        name=project.name,
                        activity=activity,
                        usage=usage.model_copy(update={"facts": selected}),
                    )
                )
        rows.append(
            TechnologyLandscapeRow(
                technology=metadata,
                project_count=len({item.project_id for item in matched}),
                proposed_project_count=len(proposals),
                projects=matched[
                    filters.project_offset : filters.project_offset + filters.project_limit
                ],
            )
        )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="technology.landscape.read",
        target_table="technology",
        target_id=organization_id,
        request_id=request_id,
    )
    return TechnologyLandscapeView(
        organization_id=organization_id,
        evaluated_at=format_timestamp(evaluated_at.astimezone(UTC)),
        inactivity_months=months,
        filters=filters,
        items=rows[filters.offset : filters.offset + filters.limit],
        total=len(rows),
    )


async def write_project_team(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    payload: ProjectTeamWriteRequest,
    request_id: str | None,
) -> ProjectTeamView:
    operation = "project.team.update"
    target = f"{project_id}/{payload.team_id}"
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=f"project_team.{_mutation_action(payload)}",
        scope_kind="project",
        scope_id=project_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=_effect(payload, target),
        request_id=request_id,
    )
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="team.read",
        scope_kind="team",
        scope_id=payload.team_id,
    )
    if receipt is not None:
        return ProjectTeamView.model_validate(receipt.response_body)
    project = await db.get(CorporateProject, project_id)
    team = await db.get(CorporateTeam, payload.team_id)
    if (
        project is None
        or project.organization_id != organization_id
        or team is None
        or team.organization_id != organization_id
    ):
        raise ApiError(ErrorCategory.PERMISSION, "relationship endpoint is unavailable")
    row = await db.scalar(
        select(ProjectTeamRelation).where(
            ProjectTeamRelation.organization_id == organization_id,
            ProjectTeamRelation.project_id == project_id,
            ProjectTeamRelation.team_id == payload.team_id,
        )
    )
    if (row.revision if row else 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "project team revision changed")
    if row is None and payload.state == "retired":
        raise ApiError(ErrorCategory.CONFLICT, "project team relation does not exist")
    if payload.state == "current" and (project.state != "active" or team.state != "active"):
        raise ApiError(ErrorCategory.VALIDATION, "current links require active endpoints")
    before = _project_team_view(row).model_dump(mode="json") if row else None
    owner = await db.scalar(
        select(ProjectTeamRelation).where(
            ProjectTeamRelation.organization_id == organization_id,
            ProjectTeamRelation.project_id == project_id,
            ProjectTeamRelation.role == "owner",
            ProjectTeamRelation.state == "current",
        )
    )
    if payload.replace_owner_relation_id is not None:
        if (
            owner is None
            or owner.id != payload.replace_owner_relation_id
            or owner.revision != payload.replace_owner_expected_revision
            or owner.team_id == payload.team_id
        ):
            raise ApiError(ErrorCategory.CONFLICT, "project owner revision changed")
        owner_before = _project_team_view(owner).model_dump(mode="json")
        owner.state = "retired"
        owner.revision += 1
        await db.flush()
        await emit_audit(
            db,
            actor_account_id=ctx.account_id,
            organization_id=organization_id,
            action="project.team.owner.replace",
            target_table="project_team_relation",
            target_id=owner.id,
            request_id=request_id,
            payload={
                "before": owner_before,
                "after": _project_team_view(owner).model_dump(mode="json"),
            },
        )
    elif (
        payload.role == "owner"
        and payload.state == "current"
        and owner is not None
        and owner.team_id != payload.team_id
    ):
        raise ApiError(ErrorCategory.CONFLICT, "project already has an owner; specify replacement")
    if row is None:
        row = ProjectTeamRelation(
            organization_id=organization_id,
            id=new_id("relation"),
            project_id=project_id,
            team_id=payload.team_id,
            role=payload.role,
            revision=1,
        )
        db.add(row)
    else:
        row.revision += 1
    row.role, row.state = payload.role, payload.state
    organization.policy_revision += 1
    await db.flush()
    response = _project_team_view(row)
    await _finish(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        target=target,
        target_table="project_team_relation",
        audit_target=row.id,
        response=response,
        before=before,
        request_id=request_id,
    )
    return response


def _project_team_view(row: ProjectTeamRelation) -> ProjectTeamView:
    return ProjectTeamView.model_validate(
        {
            "organization_id": row.organization_id,
            "relation_id": row.id,
            "project_id": row.project_id,
            "team_id": row.team_id,
            "role": row.role,
            "state": row.state,
            "revision": row.revision,
        }
    )


async def write_technology_team(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    technology_id: str,
    payload: TechnologyTeamWriteRequest,
    request_id: str | None,
) -> TechnologyTeamView:
    operation = "technology.team.update"
    target = f"{technology_id}/{payload.team_id}"
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=f"technology_team.{_mutation_action(payload)}",
        scope_kind="technology",
        scope_id=technology_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=_effect(payload, target),
        request_id=request_id,
    )
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="team.read",
        scope_kind="team",
        scope_id=payload.team_id,
    )
    if receipt is not None:
        return TechnologyTeamView.model_validate(receipt.response_body)
    technology = await db.get(Technology, (organization_id, technology_id))
    team = await db.get(CorporateTeam, payload.team_id)
    if technology is None or team is None or team.organization_id != organization_id:
        raise ApiError(ErrorCategory.PERMISSION, "relationship endpoint is unavailable")
    if technology.redirect_id is not None:
        raise ApiError(ErrorCategory.CONFLICT, "merged technology is read-only")
    if payload.state == "current" and (
        technology.lifecycle == "archived" or team.state != "active"
    ):
        raise ApiError(ErrorCategory.VALIDATION, "current responsibility requires active endpoints")
    row = await db.scalar(
        select(TechnologyTeamResponsibility).where(
            TechnologyTeamResponsibility.organization_id == organization_id,
            TechnologyTeamResponsibility.technology_id == technology_id,
            TechnologyTeamResponsibility.team_id == payload.team_id,
        )
    )
    if (row.revision if row else 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "technology responsibility revision changed")
    if row is None and payload.state == "retired":
        raise ApiError(ErrorCategory.CONFLICT, "technology responsibility does not exist")
    before = _technology_team_view(row).model_dump(mode="json") if row else None
    if row is None:
        row = TechnologyTeamResponsibility(
            organization_id=organization_id,
            id=new_id("relation"),
            technology_id=technology_id,
            team_id=payload.team_id,
            revision=1,
        )
        db.add(row)
    else:
        row.revision += 1
    row.state = payload.state
    organization.policy_revision += 1
    await db.flush()
    response = _technology_team_view(row)
    await _finish(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        target=target,
        target_table="technology_team_responsibility",
        audit_target=row.id,
        response=response,
        before=before,
        request_id=request_id,
    )
    return response


def _technology_team_view(row: TechnologyTeamResponsibility) -> TechnologyTeamView:
    return TechnologyTeamView.model_validate(
        {
            "organization_id": row.organization_id,
            "relation_id": row.id,
            "technology_id": row.technology_id,
            "team_id": row.team_id,
            "state": row.state,
            "revision": row.revision,
        }
    )


async def write_technology_decision(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    technology_id: str,
    payload: TechnologyDecisionRequest,
    request_id: str | None,
) -> TechnologyDecisionView:
    operation = "technology.decision.update"
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=f"technology_decision.{_mutation_action(payload)}",
        scope_kind="technology",
        scope_id=technology_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=_effect(payload, technology_id),
        request_id=request_id,
    )
    if receipt is not None:
        return TechnologyDecisionView.model_validate(receipt.response_body)
    technology = await db.get(Technology, (organization_id, technology_id))
    if technology is None:
        raise ApiError(ErrorCategory.PERMISSION, "technology access denied")
    if technology.redirect_id is not None or technology.lifecycle == "archived":
        raise ApiError(ErrorCategory.CONFLICT, "technology is unavailable for new decisions")
    row = await db.get(OrganizationTechnologyDecision, (organization_id, technology_id))
    if (row.revision if row else 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "technology decision revision changed")
    if payload.approved != (row.approved if row else False):
        await authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission="technology.approve",
            scope_kind="technology",
            scope_id=technology_id,
        )
    if (
        payload.lead_account_id is not None
        and await db.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.account_id == payload.lead_account_id,
                OrganizationMembership.state == "active",
            )
        )
        is None
    ):
        raise ApiError(ErrorCategory.PERMISSION, "responsible lead is unavailable")
    before = _decision_view(row).model_dump(mode="json") if row else None
    if row is None:
        row = OrganizationTechnologyDecision(
            organization_id=organization_id, technology_id=technology_id, revision=1
        )
        db.add(row)
    else:
        row.revision += 1
    row.lead_account_id, row.approved, row.adoption = (
        payload.lead_account_id,
        payload.approved,
        payload.adoption,
    )
    organization.policy_revision += 1
    await db.flush()
    response = _decision_view(row)
    await _finish(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        target=technology_id,
        target_table="organization_technology_decision",
        response=response,
        before=before,
        request_id=request_id,
    )
    return response


def _decision_view(row: OrganizationTechnologyDecision) -> TechnologyDecisionView:
    return TechnologyDecisionView.model_validate(
        {
            "technology_id": row.technology_id,
            "revision": row.revision,
            "lead_account_id": row.lead_account_id,
            "approved": row.approved,
            "adoption": row.adoption,
        }
    )


async def _readable(
    db: AsyncSession,
    ctx: AuthContext,
    organization_id: str,
    permission: str,
    scope_kind: str,
    scope_id: str,
) -> bool:
    return await has_corporate_permission(
        db,
        organization_id=organization_id,
        principal_type="user",
        principal_id=ctx.account_id,
        permission=permission,
        scope_kind=scope_kind,
        scope_id=scope_id,
    )


async def list_project_teams(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str | None,
    team_id: str | None,
    include_history: bool,
    request_id: str | None,
    offset: int = 0,
    limit: int = 128,
) -> ProjectTeamList:
    if (project_id is None) == (team_id is None):
        raise ApiError(ErrorCategory.VALIDATION, "one relationship anchor is required")
    kind, anchor = ("project", project_id) if project_id else ("team", team_id)
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=f"{kind}.read",
        scope_kind=kind,
        scope_id=anchor,
    )
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project_team.list",
        scope_kind=kind,
        scope_id=anchor,
    )
    query = (
        select(ProjectTeamRelation)
        .join(
            CorporateProject,
            (CorporateProject.organization_id == ProjectTeamRelation.organization_id)
            & (CorporateProject.id == ProjectTeamRelation.project_id),
        )
        .join(
            CorporateTeam,
            (CorporateTeam.organization_id == ProjectTeamRelation.organization_id)
            & (CorporateTeam.id == ProjectTeamRelation.team_id),
        )
        .join(
            ProjectIdentity,
            (ProjectIdentity.organization_id == CorporateProject.organization_id)
            & (ProjectIdentity.id == CorporateProject.id),
        )
        .where(
            ProjectTeamRelation.organization_id == organization_id,
        )
    )
    query = (
        query.where(ProjectTeamRelation.project_id == project_id)
        if project_id
        else query.where(ProjectTeamRelation.team_id == team_id)
    )
    if not include_history:
        query = query.where(
            ProjectTeamRelation.state == "current",
            CorporateProject.state == "active",
            CorporateTeam.state == "active",
            ProjectIdentity.state == "active",
        )
    rows = list(
        (
            await db.scalars(
                query.order_by(ProjectTeamRelation.project_id, ProjectTeamRelation.team_id)
            )
        ).all()
    )
    visible: list[ProjectTeamView] = []
    for row in rows:
        if (
            await _readable(
                db, ctx, organization_id, "project_team.list", "project", row.project_id
            )
            and await _readable(
                db, ctx, organization_id, "project_team.read", "project", row.project_id
            )
            and await _readable(db, ctx, organization_id, "project.read", "project", row.project_id)
            and await _readable(db, ctx, organization_id, "team.read", "team", row.team_id)
        ):
            visible.append(_project_team_view(row))
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.team.list",
        target_table="project_team_relation",
        target_id=anchor or organization_id,
        request_id=request_id,
    )
    return ProjectTeamList(items=visible[offset : offset + limit], total=len(visible))


async def list_technology_teams(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    technology_id: str | None,
    team_id: str | None,
    include_history: bool,
    request_id: str | None,
    offset: int = 0,
    limit: int = 128,
) -> TechnologyTeamList:
    if (technology_id is None) == (team_id is None):
        raise ApiError(ErrorCategory.VALIDATION, "one relationship anchor is required")
    kind, anchor = ("technology", technology_id) if technology_id else ("team", team_id)
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=f"{kind}.read",
        scope_kind=kind,
        scope_id=anchor,
    )
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="technology_team.list",
        scope_kind=kind,
        scope_id=anchor,
    )
    query = (
        select(TechnologyTeamResponsibility)
        .join(
            Technology,
            (Technology.organization_id == TechnologyTeamResponsibility.organization_id)
            & (Technology.id == TechnologyTeamResponsibility.technology_id),
        )
        .join(
            CorporateTeam,
            (CorporateTeam.organization_id == TechnologyTeamResponsibility.organization_id)
            & (CorporateTeam.id == TechnologyTeamResponsibility.team_id),
        )
        .where(
            TechnologyTeamResponsibility.organization_id == organization_id,
        )
    )
    query = (
        query.where(TechnologyTeamResponsibility.technology_id == technology_id)
        if technology_id
        else query.where(TechnologyTeamResponsibility.team_id == team_id)
    )
    if not include_history:
        query = query.where(
            TechnologyTeamResponsibility.state == "current",
            Technology.lifecycle != "archived",
            Technology.redirect_id.is_(None),
            CorporateTeam.state == "active",
        )
    rows = list(
        (
            await db.scalars(
                query.order_by(
                    TechnologyTeamResponsibility.technology_id, TechnologyTeamResponsibility.team_id
                )
            )
        ).all()
    )
    visible: list[TechnologyTeamView] = []
    for row in rows:
        if (
            await _readable(
                db, ctx, organization_id, "technology_team.list", "technology", row.technology_id
            )
            and await _readable(
                db, ctx, organization_id, "technology_team.read", "technology", row.technology_id
            )
            and await _readable(
                db, ctx, organization_id, "technology.read", "technology", row.technology_id
            )
            and await _readable(db, ctx, organization_id, "team.read", "team", row.team_id)
        ):
            visible.append(_technology_team_view(row))
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="technology.team.list",
        target_table="technology_team_responsibility",
        target_id=anchor or organization_id,
        request_id=request_id,
    )
    return TechnologyTeamList(items=visible[offset : offset + limit], total=len(visible))


async def list_project_technologies(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str | None,
    technology_id: str | None,
    include_history: bool,
    request_id: str | None,
    offset: int = 0,
    limit: int = 128,
) -> ProjectTechnologyList:
    if (project_id is None) == (technology_id is None):
        raise ApiError(ErrorCategory.VALIDATION, "one relationship anchor is required")
    kind, anchor = ("project", project_id) if project_id else ("technology", technology_id)
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=f"{kind}.read",
        scope_kind=kind,
        scope_id=anchor,
    )
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="project_technology.list",
        scope_kind=kind,
        scope_id=anchor,
    )
    query = (
        select(ProjectTechnologyRelation)
        .join(
            CorporateProject,
            (CorporateProject.organization_id == ProjectTechnologyRelation.organization_id)
            & (CorporateProject.id == ProjectTechnologyRelation.project_id),
        )
        .join(
            ProjectIdentity,
            (ProjectIdentity.organization_id == CorporateProject.organization_id)
            & (ProjectIdentity.id == CorporateProject.id),
        )
        .join(
            Technology,
            (Technology.organization_id == ProjectTechnologyRelation.organization_id)
            & (Technology.id == ProjectTechnologyRelation.technology_id),
        )
        .where(
            ProjectTechnologyRelation.organization_id == organization_id,
        )
    )
    query = (
        query.where(ProjectTechnologyRelation.project_id == project_id)
        if project_id
        else query.where(ProjectTechnologyRelation.technology_id == technology_id)
    )
    if not include_history:
        query = query.where(
            ProjectTechnologyRelation.state == "current",
            CorporateProject.state == "active",
            ProjectIdentity.state == "active",
            Technology.lifecycle != "archived",
            Technology.redirect_id.is_(None),
        )
    rows = list(
        (
            await db.scalars(
                query.order_by(
                    ProjectTechnologyRelation.project_id, ProjectTechnologyRelation.technology_id
                )
            )
        ).all()
    )
    visible: list[ProjectTechnologyView] = []
    for row in rows:
        if (
            await _readable(
                db, ctx, organization_id, "project_technology.list", "project", row.project_id
            )
            and await _readable(
                db, ctx, organization_id, "project_technology.read", "project", row.project_id
            )
            and await _readable(db, ctx, organization_id, "project.read", "project", row.project_id)
            and await _readable(
                db, ctx, organization_id, "technology.read", "technology", row.technology_id
            )
        ):
            visible.append(await project_technology_view(db, row))
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="project.technology.list",
        target_table="project_technology_relation",
        target_id=anchor or organization_id,
        request_id=request_id,
    )
    return ProjectTechnologyList(items=visible[offset : offset + limit], total=len(visible))


async def read_technology_decision(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    technology_id: str,
    request_id: str | None,
) -> TechnologyDecisionView:
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="technology_decision.read",
        scope_kind="technology",
        scope_id=technology_id,
    )
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="technology.read",
        scope_kind="technology",
        scope_id=technology_id,
    )
    row = await db.get(OrganizationTechnologyDecision, (organization_id, technology_id))
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "technology decision is unavailable")
    response = _decision_view(row)
    if (
        row.lead_account_id is not None
        and await db.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.account_id == row.lead_account_id,
                OrganizationMembership.state == "active",
            )
        )
        is None
    ):
        response = response.model_copy(update={"lead_account_id": None})
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="technology.decision.read",
        target_table="organization_technology_decision",
        target_id=technology_id,
        request_id=request_id,
    )
    return response


async def list_categories(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    request_id: str | None,
) -> CategoryList:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="category.list")
    rows = list(
        (
            await db.scalars(
                select(TechnologyCategory)
                .where(
                    TechnologyCategory.organization_id == organization_id,
                )
                .order_by(TechnologyCategory.normalized_name, TechnologyCategory.id)
            )
        ).all()
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="category.list",
        target_table="technology_category",
        target_id=organization_id,
        request_id=request_id,
    )
    return CategoryList(
        items=[
            CategoryView(
                category_id=row.id,
                name=row.name,
                description=row.description,
                revision=row.revision,
                provenance=row.provenance,
            )
            for row in rows
        ]
    )


async def read_technology(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    technology_id: str,
    request_id: str | None,
) -> TechnologyView:
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="technology.read",
        scope_kind="technology",
        scope_id=technology_id,
    )
    row = await db.get(Technology, (organization_id, technology_id))
    if row is None:
        raise ApiError(ErrorCategory.PERMISSION, "technology access denied")
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="technology.read",
        target_table="technology",
        target_id=technology_id,
        request_id=request_id,
    )
    return await technology_view(db, row)


async def list_technologies(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    include_archived: bool,
    offset: int,
    limit: int,
    request_id: str | None,
) -> TechnologyList:
    await authorize(db, ctx=ctx, organization_id=organization_id, permission="technology.list")
    query = select(Technology).where(Technology.organization_id == organization_id)
    if not include_archived:
        query = query.where(Technology.lifecycle != "archived", Technology.redirect_id.is_(None))
    rows = list((await db.scalars(query.order_by(Technology.name, Technology.id))).all())
    authorized: list[Technology] = []
    # ponytail: per-row policy checks; batch the same evaluator if large registries need it.
    for row in rows:
        if await has_corporate_permission(
            db,
            organization_id=organization_id,
            principal_type="user",
            principal_id=ctx.account_id,
            permission="technology.read",
            scope_kind="technology",
            scope_id=row.id,
        ):
            authorized.append(row)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="technology.list",
        target_table="technology",
        target_id=organization_id,
        request_id=request_id,
    )
    return TechnologyList(
        total=len(authorized),
        items=[await technology_view(db, row) for row in authorized[offset : offset + limit]],
    )


def _mutation_action(payload: TechnologyMutation) -> str:
    if getattr(payload, "state", None) == "retired":
        return "delete"
    return "create" if payload.expected_revision == 0 else "update"


def _effect(payload: TechnologyMutation, target: str) -> str:
    return mutation_fingerprint(
        {
            "target": target,
            "body": payload.model_dump(
                mode="json", exclude={"idempotency_key", "authorization_revision"}
            ),
        }
    )


async def _finish(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: TechnologyMutation,
    operation: str,
    target: str,
    response: BaseModel,
    before: Mapping[str, object] | None,
    request_id: str | None,
    target_table: str = "technology",
    audit_target: str | None = None,
) -> None:
    await store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation=operation,
        fingerprint=_effect(payload, target),
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action=operation,
        target_table=target_table,
        target_id=audit_target or target,
        request_id=request_id,
        payload={"before": before, "after": response.model_dump(mode="json")},
    )


async def technology_view(db: AsyncSession, row: Technology) -> TechnologyView:
    categories = list(
        (
            await db.scalars(
                select(TechnologyClassification.category_id)
                .where(
                    TechnologyClassification.organization_id == row.organization_id,
                    TechnologyClassification.technology_id == row.id,
                )
                .order_by(TechnologyClassification.category_id)
            )
        ).all()
    )
    aliases = list(
        (
            await db.scalars(
                select(TechnologyAlias.name)
                .where(
                    TechnologyAlias.organization_id == row.organization_id,
                    TechnologyAlias.technology_id == row.id,
                    TechnologyAlias.canonical.is_(False),
                )
                .order_by(TechnologyAlias.normalized_name)
            )
        ).all()
    )
    return TechnologyView.model_validate(
        {
            "organization_id": row.organization_id,
            "technology_id": row.id,
            "name": row.name,
            "description": row.description,
            "category_ids": categories,
            "aliases": aliases,
            "icon_url": row.icon_url,
            "official_urls": row.official_urls,
            "lifecycle": row.lifecycle,
            "revision": row.revision,
            "redirect_id": row.redirect_id,
            "provenance": row.provenance,
        }
    )


async def write_category(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    category_id: str | None,
    payload: CategoryWriteRequest,
    request_id: str | None,
) -> CategoryView:
    target = category_id or "create"
    if category_id is None and payload.expected_revision != 0:
        raise ApiError(ErrorCategory.VALIDATION, "creation requires expected revision zero")
    operation = "category.create" if payload.expected_revision == 0 else "category.update"
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=operation,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=_effect(payload, target),
        request_id=request_id,
    )
    if receipt is not None:
        return CategoryView.model_validate(receipt.response_body)
    category_id = category_id or new_id("category")
    row = await db.get(TechnologyCategory, (organization_id, category_id))
    if (row.revision if row else 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "category revision changed")
    normalized = normalize_technology_name(payload.metadata.name)
    collision = await db.scalar(
        select(TechnologyCategory.id).where(
            TechnologyCategory.organization_id == organization_id,
            TechnologyCategory.normalized_name == normalized,
            TechnologyCategory.id != category_id,
        )
    )
    if collision is not None:
        raise ApiError(ErrorCategory.CONFLICT, "category name already exists")
    before = (
        {"name": row.name, "description": row.description, "revision": row.revision}
        if row
        else None
    )
    if row is None:
        row = TechnologyCategory(
            organization_id=organization_id,
            id=category_id,
            name=payload.metadata.name,
            normalized_name=normalized,
            provenance="manual",
            revision=1,
        )
        db.add(row)
    else:
        row.revision += 1
    row.name, row.normalized_name = payload.metadata.name, normalized
    row.description = payload.metadata.description
    organization.policy_revision += 1
    await db.flush()
    response = CategoryView(
        category_id=row.id,
        name=row.name,
        description=row.description,
        revision=row.revision,
        provenance=row.provenance,
    )
    await _finish(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        target=target,
        audit_target=category_id,
        target_table="technology_category",
        response=response,
        before=before,
        request_id=request_id,
    )
    return response


async def write_technology(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    technology_id: str | None,
    payload: TechnologyWriteRequest,
    request_id: str | None,
) -> TechnologyView:
    target = technology_id or "create"
    if technology_id is None and payload.expected_revision != 0:
        raise ApiError(ErrorCategory.VALIDATION, "creation requires expected revision zero")
    operation = "technology.create" if payload.expected_revision == 0 else "technology.update"
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=operation,
        scope_kind="technology",
        scope_id=technology_id or "*",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=_effect(payload, target),
        request_id=request_id,
    )
    if receipt is not None:
        return TechnologyView.model_validate(receipt.response_body)
    technology_id = technology_id or new_id("technology")
    row = await db.get(Technology, (organization_id, technology_id))
    if (row.revision if row else 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "technology revision changed")
    if row is not None and row.redirect_id is not None:
        raise ApiError(ErrorCategory.CONFLICT, "merged technology is read-only")
    categories = list(
        (
            await db.scalars(
                select(TechnologyCategory.id).where(
                    TechnologyCategory.organization_id == organization_id,
                    TechnologyCategory.id.in_(payload.metadata.category_ids),
                )
            )
        ).all()
    )
    if set(categories) != set(payload.metadata.category_ids):
        raise ApiError(ErrorCategory.VALIDATION, "category is unavailable")
    names = [payload.metadata.name, *payload.metadata.aliases]
    normalized = [normalize_technology_name(name) for name in names]
    if len(set(normalized)) != len(normalized):
        raise ApiError(ErrorCategory.CONFLICT, "canonical name collides with an alias")
    collision = await db.scalar(
        select(TechnologyAlias.technology_id).where(
            TechnologyAlias.organization_id == organization_id,
            TechnologyAlias.normalized_name.in_(normalized),
            TechnologyAlias.technology_id != technology_id,
        )
    )
    if collision is not None:
        raise ApiError(ErrorCategory.CONFLICT, "technology name or alias already exists")
    before = (await technology_view(db, row)).model_dump(mode="json") if row else None
    if row is None:
        row = Technology(
            organization_id=organization_id,
            id=technology_id,
            name=payload.metadata.name,
            provenance="manual",
            revision=1,
        )
        db.add(row)
        await db.flush()
    else:
        row.revision += 1
    row.name, row.description = payload.metadata.name, payload.metadata.description
    row.icon_url, row.official_urls = payload.metadata.icon_url, payload.metadata.official_urls
    await db.execute(
        delete(TechnologyAlias).where(
            TechnologyAlias.organization_id == organization_id,
            TechnologyAlias.technology_id == technology_id,
        )
    )
    await db.execute(
        delete(TechnologyClassification).where(
            TechnologyClassification.organization_id == organization_id,
            TechnologyClassification.technology_id == technology_id,
        )
    )
    db.add_all(
        TechnologyAlias(
            organization_id=organization_id,
            technology_id=technology_id,
            name=name,
            normalized_name=value,
            canonical=index == 0,
        )
        for index, (name, value) in enumerate(zip(names, normalized, strict=True))
    )
    db.add_all(
        TechnologyClassification(
            organization_id=organization_id, technology_id=technology_id, category_id=category
        )
        for category in categories
    )
    organization.policy_revision += 1
    await db.flush()
    response = await technology_view(db, row)
    await _finish(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        target=target,
        audit_target=technology_id,
        response=response,
        before=before,
        request_id=request_id,
    )
    return response


async def change_lifecycle(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    technology_id: str,
    payload: TechnologyLifecycleRequest,
    request_id: str | None,
) -> TechnologyView:
    operation = "technology.approve" if payload.lifecycle == "active" else "technology.update"
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=operation,
        scope_kind="technology",
        scope_id=technology_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=_effect(payload, technology_id),
        request_id=request_id,
    )
    if receipt is not None:
        return TechnologyView.model_validate(receipt.response_body)
    row = await db.get(Technology, (organization_id, technology_id))
    if row is None or row.revision != payload.expected_revision or row.redirect_id is not None:
        raise ApiError(ErrorCategory.CONFLICT, "technology revision changed")
    transitions = {
        "draft": {"active", "archived"},
        "active": {"deprecated", "archived"},
        "deprecated": {"active", "archived"},
        "archived": {row.restore_lifecycle},
    }
    if payload.lifecycle not in transitions[row.lifecycle]:
        raise ApiError(ErrorCategory.VALIDATION, "invalid technology lifecycle transition")
    before = (await technology_view(db, row)).model_dump(mode="json")
    if payload.lifecycle == "archived":
        row.restore_lifecycle = row.lifecycle
    row.lifecycle = payload.lifecycle
    row.revision += 1
    organization.policy_revision += 1
    response = await technology_view(db, row)
    await _finish(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        target=technology_id,
        response=response,
        before=before,
        request_id=request_id,
    )
    return response


async def project_technology_view(
    db: AsyncSession,
    row: ProjectTechnologyRelation,
) -> ProjectTechnologyView:
    facts = list(
        (
            await db.scalars(
                select(TechnologyUsageFact)
                .where(
                    TechnologyUsageFact.organization_id == row.organization_id,
                    TechnologyUsageFact.relation_id == row.id,
                )
                .order_by(TechnologyUsageFact.context)
            )
        ).all()
    )
    return ProjectTechnologyView.model_validate(
        {
            "organization_id": row.organization_id,
            "relation_id": row.id,
            "project_id": row.project_id,
            "technology_id": row.technology_id,
            "state": row.state,
            "revision": row.revision,
            "facts": [
                {
                    "context": fact.context,
                    "version": fact.version,
                    "version_kind": fact.version_kind,
                    "review": fact.review,
                    "freshness": fact.freshness,
                    "evidence": fact.evidence,
                }
                for fact in facts
            ],
        }
    )


async def write_project_technology(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    payload: ProjectTechnologyWriteRequest,
    request_id: str | None,
) -> ProjectTechnologyView:
    operation = "project.technology.update"
    target = f"{project_id}/{payload.technology_id}"
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission=f"project_technology.{_mutation_action(payload)}",
        scope_kind="project",
        scope_id=project_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        fingerprint=_effect(payload, target),
        request_id=request_id,
    )
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="technology.read",
        scope_kind="technology",
        scope_id=payload.technology_id,
    )
    if receipt is not None:
        return ProjectTechnologyView.model_validate(receipt.response_body)
    project = await db.scalar(
        select(CorporateProject)
        .join(
            ProjectIdentity,
            (ProjectIdentity.organization_id == CorporateProject.organization_id)
            & (ProjectIdentity.id == CorporateProject.id),
        )
        .where(
            CorporateProject.organization_id == organization_id,
            CorporateProject.id == project_id,
            CorporateProject.state == "active",
            ProjectIdentity.state == "active",
        )
    )
    technology = await db.get(Technology, (organization_id, payload.technology_id))
    if project is None or technology is None or technology.redirect_id is not None:
        raise ApiError(ErrorCategory.PERMISSION, "relationship endpoint is unavailable")
    row = await db.scalar(
        select(ProjectTechnologyRelation).where(
            ProjectTechnologyRelation.organization_id == organization_id,
            ProjectTechnologyRelation.project_id == project_id,
            ProjectTechnologyRelation.technology_id == payload.technology_id,
        )
    )
    if (row.revision if row else 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.CONFLICT, "project technology revision changed")
    if row is None and payload.state == "retired":
        raise ApiError(ErrorCategory.CONFLICT, "project technology relation does not exist")
    if (row is None or row.state == "retired") and technology.lifecycle != "active":
        raise ApiError(ErrorCategory.VALIDATION, "new usage requires an active technology")
    before = (await project_technology_view(db, row)).model_dump(mode="json") if row else None
    if row is None:
        row = ProjectTechnologyRelation(
            organization_id=organization_id,
            id=new_id("relation"),
            project_id=project_id,
            technology_id=technology.id,
            revision=1,
        )
        db.add(row)
        await db.flush()
    else:
        row.revision += 1
    row.state = payload.state
    fact = await db.get(TechnologyUsageFact, (organization_id, row.id, payload.fact.context))
    if fact is None:
        fact = TechnologyUsageFact(
            organization_id=organization_id,
            relation_id=row.id,
            context=payload.fact.context,
            review=payload.review,
        )
        db.add(fact)
    fact.review, fact.version = payload.review, payload.fact.version
    fact.version_kind = payload.fact.version_kind
    fact.evidence = [entry.model_dump(mode="json") for entry in payload.fact.evidence]
    fact.freshness = "current"
    organization.policy_revision += 1
    await db.flush()
    response = await project_technology_view(db, row)
    await _finish(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation=operation,
        target=target,
        target_table="project_technology_relation",
        audit_target=row.id,
        response=response,
        before=before,
        request_id=request_id,
    )
    return response
