"""Retained employee competences never create usage or authorization bindings."""

from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.audit import emit_audit
from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import service as corporate
from ai_stp_api.slices.technology import service
from ai_stp_contracts.technology import (
    EmployeeTechnologyList,
    EmployeeTechnologyRequest,
    EmployeeTechnologyView,
    RelationshipListQuery,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.technology_models import EmployeeTechnology


async def write_competence(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    payload: EmployeeTechnologyRequest,
    request_id: str | None,
) -> EmployeeTechnologyView:
    fingerprint = corporate.mutation_fingerprint(
        payload.model_dump(mode="json", exclude={"idempotency_key"})
    )
    _, receipt = await corporate.authorize_idempotent(
        db,
        ctx=ctx,
        organization_id=organization_id,
        permission="member.manage",
        authorization_revision=payload.authorization_revision,
        idempotency_key=payload.idempotency_key,
        operation="employee_technology.write",
        fingerprint=fingerprint,
        request_id=request_id,
    )
    member = await corporate.read_member(
        db,
        ctx=ctx,
        organization_id=organization_id,
        account_id=payload.account_id,
        request_id=request_id,
    )
    technology = await service.read_technology(
        db,
        ctx=ctx,
        organization_id=organization_id,
        technology_id=payload.technology_id,
        request_id=request_id,
    )
    if payload.state == "current" and (
        member.state != "active" or technology.lifecycle == "archived" or technology.redirect_id
    ):
        raise ApiError(ErrorCategory.PERMISSION, "competence subject is unavailable")
    if receipt is not None:
        return EmployeeTechnologyView.model_validate(receipt.response_body)
    row = await db.scalar(
        select(EmployeeTechnology)
        .where(
            EmployeeTechnology.organization_id == organization_id,
            EmployeeTechnology.account_id == payload.account_id,
            EmployeeTechnology.technology_id == payload.technology_id,
        )
        .with_for_update()
    )
    if (row.revision if row else 0) != payload.expected_revision:
        raise ApiError(ErrorCategory.PRECONDITION, "competence revision is stale")
    if row is None:
        row = EmployeeTechnology(
            organization_id=organization_id,
            id=new_id("relation"),
            account_id=payload.account_id,
            technology_id=payload.technology_id,
            state=payload.state,
            revision=1,
        )
        db.add(row)
    else:
        row.state = payload.state
        row.revision += 1
    await db.flush()
    response = EmployeeTechnologyView(
        organization_id=organization_id,
        relation_id=row.id,
        account_id=row.account_id,
        technology_id=row.technology_id,
        state=payload.state,
        revision=row.revision,
    )
    await corporate.store_mutation_receipt(
        db,
        organization_id=organization_id,
        key=payload.idempotency_key,
        operation="employee_technology.write",
        fingerprint=fingerprint,
        response=response,
    )
    await emit_audit(
        db,
        actor_account_id=ctx.account_id,
        organization_id=organization_id,
        action="employee_technology.write",
        target_table="employee_technology",
        target_id=row.id,
        request_id=request_id,
    )
    return response


async def list_competences(
    db: AsyncSession,
    *,
    ctx: AuthContext,
    organization_id: str,
    account_id: str | None,
    technology_id: str | None,
    query: RelationshipListQuery,
    request_id: str | None,
) -> EmployeeTechnologyList:
    if (account_id is None) == (technology_id is None):
        raise ApiError(ErrorCategory.VALIDATION, "exactly one competence anchor is required")
    if account_id is not None:
        await corporate.read_member(
            db,
            ctx=ctx,
            organization_id=organization_id,
            account_id=account_id,
            request_id=request_id,
        )
    if technology_id is not None:
        await service.read_technology(
            db,
            ctx=ctx,
            organization_id=organization_id,
            technology_id=technology_id,
            request_id=request_id,
        )
    statement = select(EmployeeTechnology).where(
        EmployeeTechnology.organization_id == organization_id
    )
    statement = (
        statement.where(EmployeeTechnology.account_id == account_id)
        if account_id
        else statement.where(EmployeeTechnology.technology_id == technology_id)
    )
    if not query.include_history:
        statement = statement.where(EmployeeTechnology.state == "current")
    rows = (await db.scalars(statement.order_by(EmployeeTechnology.id))).all()
    items = [
        EmployeeTechnologyView(
            organization_id=row.organization_id,
            relation_id=row.id,
            account_id=row.account_id,
            technology_id=row.technology_id,
            state=cast(Literal["current", "retired"], row.state),
            revision=row.revision,
        )
        for row in rows
    ]
    return EmployeeTechnologyList(
        items=items[query.offset : query.offset + query.limit], total=len(items)
    )
