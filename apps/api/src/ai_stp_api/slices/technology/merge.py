"""Digest-pinned technology merges retain canonical endpoints and reviewed history."""

from typing import NamedTuple, cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import authorize, authorize_idempotent
from ai_stp_api.slices.technology.service import (
    decision_view,
    finish_mutation,
    mutation_effect,
    project_technology_view,
    technology_team_view,
    technology_view,
)
from ai_stp_contracts.technology import (
    ProjectTechnologyView,
    TechnologyDecisionView,
    TechnologyMergePlanView,
    TechnologyMergeProjectEffect,
    TechnologyMergeRequest,
    TechnologyMergeResult,
    TechnologyMergeTeamEffect,
    TechnologyTeamView,
    TechnologyView,
    UsageFactView,
    normalize_technology_name,
)
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id
from ai_stp_platform.technology_models import (
    OrganizationTechnologyDecision,
    ProjectTechnologyRelation,
    Technology,
    TechnologyAlias,
    TechnologyClassification,
    TechnologyTeamResponsibility,
    TechnologyUsageFact,
)


class _Inputs(NamedTuple):
    source: TechnologyView
    target: TechnologyView
    projects: list[ProjectTechnologyView]
    teams: list[TechnologyTeamView]
    decisions: list[TechnologyDecisionView]


async def _technology_authority(
    db: AsyncSession,
    ctx: AuthContext,
    organization_id: str,
    source_id: str,
    target_id: str,
) -> None:
    for technology_id in (source_id, target_id):
        for permission in ("technology.read", "technology.merge", "technology_decision.read"):
            await authorize(
                db,
                ctx=ctx,
                organization_id=organization_id,
                permission=permission,
                scope_kind="technology",
                scope_id=technology_id,
            )


async def _project_authority(
    db: AsyncSession,
    ctx: AuthContext,
    organization_id: str,
    project_id: str,
    target_action: str,
) -> None:
    for permission in (
        "project.read",
        "project_technology.read",
        "project_technology.delete",
        f"project_technology.{target_action}",
    ):
        await authorize(
            db,
            ctx=ctx,
            organization_id=organization_id,
            permission=permission,
            scope_kind="project",
            scope_id=project_id,
        )


async def _team_authority(
    db: AsyncSession,
    ctx: AuthContext,
    organization_id: str,
    source_id: str,
    target_id: str,
    team_id: str,
    target_action: str,
) -> None:
    await authorize(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="team.read",
        scope_kind="team",
        scope_id=team_id,
    )
    for technology_id, action in ((source_id, "delete"), (target_id, target_action)):
        for permission in ("technology_team.read", f"technology_team.{action}"):
            await authorize(
                db,
                ctx=ctx,
                organization_id=organization_id,
                permission=permission,
                scope_kind="technology",
                scope_id=technology_id,
            )


def combined_fact(source: UsageFactView, target: UsageFactView | None) -> UsageFactView:
    """Compatible reviewed facts combine evidence, never governance or versions."""
    if target is None:
        return source
    if source.model_dump(exclude={"evidence"}) != target.model_dump(exclude={"evidence"}):
        raise ApiError(ErrorCategory.CONFLICT, "technology merge has conflicting usage facts")
    evidence = {
        canonize(cast(JsonValue, entry.model_dump(mode="json"))): entry
        for entry in [*target.evidence, *source.evidence]
    }
    if len(evidence) > 64:
        raise ApiError(ErrorCategory.CONFLICT, "technology merge evidence exceeds contract bounds")
    return target.model_copy(update={"evidence": list(evidence.values())})


async def _inputs(
    db: AsyncSession,
    ctx: AuthContext,
    organization_id: str,
    source_id: str,
    target_id: str,
) -> _Inputs:
    await _technology_authority(db, ctx, organization_id, source_id, target_id)
    source = await db.get(Technology, (organization_id, source_id))
    target = await db.get(Technology, (organization_id, target_id))
    if source is None or target is None:
        raise ApiError(ErrorCategory.PERMISSION, "technology merge endpoint is unavailable")
    if source_id == target_id or source.redirect_id or target.redirect_id:
        raise ApiError(
            ErrorCategory.CONFLICT, "technology merge requires distinct canonical endpoints"
        )
    projects = list(
        (
            await db.scalars(
                select(ProjectTechnologyRelation)
                .where(
                    ProjectTechnologyRelation.organization_id == organization_id,
                    ProjectTechnologyRelation.technology_id.in_([source_id, target_id]),
                )
                .order_by(
                    ProjectTechnologyRelation.project_id, ProjectTechnologyRelation.technology_id
                )
            )
        ).all()
    )
    source_projects = {
        row.project_id: row
        for row in projects
        if row.technology_id == source_id and row.state == "current"
    }
    projects = [row for row in projects if row.project_id in source_projects]
    target_projects = {row.project_id: row for row in projects if row.technology_id == target_id}
    for project_id in source_projects:
        target_pair = target_projects.get(project_id)
        await _project_authority(
            db, ctx, organization_id, project_id, "update" if target_pair else "create"
        )
        if target_pair and target_pair.state == "retired":
            raise ApiError(
                ErrorCategory.CONFLICT, "technology merge target pair is intentionally retired"
            )
        if target_pair is None and target.lifecycle != "active":
            raise ApiError(
                ErrorCategory.CONFLICT, "technology merge new usage requires active target"
            )
    project_views = [await project_technology_view(db, row) for row in projects]
    target_views = {row.project_id: row for row in project_views if row.technology_id == target_id}
    for row in project_views:
        if row.technology_id != source_id:
            continue
        target_view = target_views.get(row.project_id)
        target_facts = {fact.context: fact for fact in target_view.facts} if target_view else {}
        for fact in row.facts:
            combined_fact(fact, target_facts.get(fact.context))
    teams = list(
        (
            await db.scalars(
                select(TechnologyTeamResponsibility)
                .where(
                    TechnologyTeamResponsibility.organization_id == organization_id,
                    TechnologyTeamResponsibility.technology_id.in_([source_id, target_id]),
                )
                .order_by(
                    TechnologyTeamResponsibility.team_id, TechnologyTeamResponsibility.technology_id
                )
            )
        ).all()
    )
    source_teams = {
        row.team_id for row in teams if row.technology_id == source_id and row.state == "current"
    }
    teams = [row for row in teams if row.team_id in source_teams]
    target_teams = {row.team_id: row for row in teams if row.technology_id == target_id}
    for team_id in source_teams:
        target_pair = target_teams.get(team_id)
        await _team_authority(
            db,
            ctx,
            organization_id,
            source_id,
            target_id,
            team_id,
            "update" if target_pair else "create",
        )
        if target_pair and target_pair.state == "retired":
            raise ApiError(
                ErrorCategory.CONFLICT, "technology merge target responsibility is retired"
            )
    decisions: list[TechnologyDecisionView] = []
    for technology_id in (source_id, target_id):
        row = await db.get(OrganizationTechnologyDecision, (organization_id, technology_id))
        if row is not None:
            await authorize(
                db,
                ctx=ctx,
                organization_id=organization_id,
                permission="technology_decision.read",
                scope_kind="technology",
                scope_id=technology_id,
            )
            decisions.append(decision_view(row))
    decision_values = {
        row.technology_id: (row.lead_account_id, row.approved, row.adoption) for row in decisions
    }
    if decision_values.get(source_id, (None, False, "none")) != decision_values.get(
        target_id, (None, False, "none")
    ):
        raise ApiError(
            ErrorCategory.CONFLICT, "technology merge has conflicting organization decisions"
        )
    source_view, target_view = await technology_view(db, source), await technology_view(db, target)
    categories = set(source_view.category_ids) | set(target_view.category_ids)
    names = {
        normalize_technology_name(name)
        for name in [source_view.name, *source_view.aliases, *target_view.aliases]
    } - {normalize_technology_name(target_view.name)}
    if len(categories) > 32 or len(names) > 64:
        raise ApiError(ErrorCategory.CONFLICT, "technology merge metadata exceeds contract bounds")
    return _Inputs(
        source_view,
        target_view,
        project_views,
        [technology_team_view(row) for row in teams],
        decisions,
    )


def _plan(inputs: _Inputs) -> TechnologyMergePlanView:
    snapshot = {
        "kind": "technology_merge",
        "schema_version": 1,
        "organization_id": inputs.source.organization_id,
        "source": inputs.source.model_dump(mode="json"),
        "target": inputs.target.model_dump(mode="json"),
        "projects": [row.model_dump(mode="json") for row in inputs.projects],
        "teams": [row.model_dump(mode="json") for row in inputs.teams],
        "decisions": [row.model_dump(mode="json") for row in inputs.decisions],
    }
    return TechnologyMergePlanView(
        organization_id=inputs.source.organization_id,
        source=inputs.source,
        target=inputs.target,
        affected_project_count=len({row.project_id for row in inputs.projects}),
        affected_team_count=len({row.team_id for row in inputs.teams}),
        digest=digest_canonical("ai-stp:plan:v1", cast(JsonValue, snapshot)),
    )


async def read_merge_plan(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    source_id: str,
    target_id: str,
    request_id: str | None,
) -> TechnologyMergePlanView:
    inputs = await _inputs(db, ctx, organization_id, source_id, target_id)
    response = _plan(inputs)
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="technology.merge.plan.read",
        target_table="technology",
        target_id=source_id,
        request_id=request_id,
        reason="deliberate_merge_preview",
    )
    return response


async def _apply_projects(db: AsyncSession, inputs: _Inputs) -> list[TechnologyMergeProjectEffect]:
    organization_id = inputs.source.organization_id
    targets = {
        row.project_id: row
        for row in inputs.projects
        if row.technology_id == inputs.target.technology_id
    }
    effects: list[TechnologyMergeProjectEffect] = []
    for view in inputs.projects:
        if view.technology_id != inputs.source.technology_id:
            continue
        source = await db.get(ProjectTechnologyRelation, (organization_id, view.relation_id))
        assert source is not None
        target_view = targets.get(view.project_id)
        target = (
            await db.get(ProjectTechnologyRelation, (organization_id, target_view.relation_id))
            if target_view
            else None
        )
        if target is None:
            target = ProjectTechnologyRelation(
                organization_id=organization_id,
                id=new_id("relation"),
                project_id=view.project_id,
                technology_id=inputs.target.technology_id,
                state="current",
                revision=1,
            )
            db.add(target)
            await db.flush()
        else:
            target.revision += 1
        target_facts = {fact.context: fact for fact in target_view.facts} if target_view else {}
        for source_fact in view.facts:
            merged = combined_fact(source_fact, target_facts.get(source_fact.context))
            row = await db.get(TechnologyUsageFact, (organization_id, target.id, merged.context))
            if row is None:
                row = TechnologyUsageFact(
                    organization_id=organization_id,
                    relation_id=target.id,
                    context=merged.context,
                    review=merged.review,
                )
                db.add(row)
            row.review, row.version, row.version_kind, row.freshness = (
                merged.review,
                merged.version,
                merged.version_kind,
                merged.freshness,
            )
            row.evidence = [entry.model_dump(mode="json") for entry in merged.evidence]
        source.state = "retired"
        source.revision += 1
        effects.append(
            TechnologyMergeProjectEffect(
                project_id=view.project_id,
                source_relation_id=source.id,
                target_relation_id=target.id,
                target_action="update" if target_view else "create",
            )
        )
    return effects


async def _apply_teams(db: AsyncSession, inputs: _Inputs) -> list[TechnologyMergeTeamEffect]:
    organization_id = inputs.source.organization_id
    targets = {
        row.team_id: row for row in inputs.teams if row.technology_id == inputs.target.technology_id
    }
    effects: list[TechnologyMergeTeamEffect] = []
    for view in inputs.teams:
        if view.technology_id != inputs.source.technology_id:
            continue
        source = await db.get(TechnologyTeamResponsibility, (organization_id, view.relation_id))
        assert source is not None
        target_view = targets.get(view.team_id)
        target = (
            await db.get(TechnologyTeamResponsibility, (organization_id, target_view.relation_id))
            if target_view
            else None
        )
        if target is None:
            target = TechnologyTeamResponsibility(
                organization_id=organization_id,
                id=new_id("relation"),
                technology_id=inputs.target.technology_id,
                team_id=view.team_id,
                state="current",
                revision=1,
            )
            db.add(target)
        else:
            target.revision += 1
        source.state = "retired"
        source.revision += 1
        effects.append(
            TechnologyMergeTeamEffect(
                team_id=view.team_id,
                source_relation_id=source.id,
                target_relation_id=target.id,
                target_action="update" if target_view else "create",
            )
        )
    return effects


async def merge_technology(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    source_id: str,
    payload: TechnologyMergeRequest,
    request_id: str | None,
) -> TechnologyMergeResult:
    organization, receipt = await authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="technology.merge",
        scope_kind="technology",
        scope_id=source_id,
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="technology.merge",
        fingerprint=mutation_effect(payload, source_id),
        request_id=request_id,
    )
    await _technology_authority(db, ctx, organization_id, source_id, payload.target_id)
    if receipt is not None:
        result = TechnologyMergeResult.model_validate(receipt.response_body)
        for effect in result.project_effects:
            await _project_authority(
                db, ctx, organization_id, effect.project_id, effect.target_action
            )
        for effect in result.team_effects:
            await _team_authority(
                db,
                ctx,
                organization_id,
                source_id,
                payload.target_id,
                effect.team_id,
                effect.target_action,
            )
        return result
    inputs = await _inputs(db, ctx, organization_id, source_id, payload.target_id)
    if (
        inputs.source.revision != payload.expected_revision
        or inputs.target.revision != payload.target_expected_revision
    ):
        raise ApiError(ErrorCategory.CONFLICT, "technology merge revision changed")
    if _plan(inputs).digest != payload.plan_digest:
        raise ApiError(ErrorCategory.CONFLICT, "technology merge plan changed")
    source = await db.get(Technology, (organization_id, source_id))
    target = await db.get(Technology, (organization_id, payload.target_id))
    assert source is not None and target is not None
    before = {
        "source": inputs.source.model_dump(mode="json"),
        "target": inputs.target.model_dump(mode="json"),
        "projects": [row.model_dump(mode="json") for row in inputs.projects],
        "teams": [row.model_dump(mode="json") for row in inputs.teams],
    }
    projects = await _apply_projects(db, inputs)
    teams = await _apply_teams(db, inputs)
    for category_id in sorted(set(inputs.source.category_ids) - set(inputs.target.category_ids)):
        db.add(
            TechnologyClassification(
                organization_id=organization_id, technology_id=target.id, category_id=category_id
            )
        )
    aliases = list(
        (
            await db.scalars(
                select(TechnologyAlias).where(
                    TechnologyAlias.organization_id == organization_id,
                    TechnologyAlias.technology_id == source.id,
                )
            )
        ).all()
    )
    alias_values = [(row.normalized_name, row.name) for row in aliases]
    await db.execute(
        delete(TechnologyAlias).where(
            TechnologyAlias.organization_id == organization_id,
            TechnologyAlias.technology_id == source.id,
        )
    )
    await db.flush()
    for normalized, name in alias_values:
        db.add(
            TechnologyAlias(
                organization_id=organization_id,
                technology_id=target.id,
                normalized_name=normalized,
                name=name,
                canonical=False,
            )
        )
    if source.lifecycle != "archived":
        source.restore_lifecycle = source.lifecycle
    source.lifecycle, source.redirect_id = "archived", target.id
    source.revision += 1
    target.revision += 1
    organization.policy_revision += 1
    await db.flush()
    result = TechnologyMergeResult(
        source=await technology_view(db, source),
        target=await technology_view(db, target),
        project_effects=projects,
        team_effects=teams,
    )
    await finish_mutation(
        db,
        ctx=ctx,
        organization_id=organization_id,
        payload=payload,
        operation="technology.merge",
        target=source_id,
        response=result,
        before=before,
        request_id=request_id,
        reason="deliberate_technology_merge",
    )
    return result
