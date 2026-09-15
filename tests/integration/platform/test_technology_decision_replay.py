"""Approval changes retain their original extra authorization requirement on replay."""

from typing import cast

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError, ErrorCategory
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import bootstrap
from ai_stp_api.slices.technology.service import (
    import_seed,
    mutation_effect,
    write_technology_decision,
)
from ai_stp_contracts.corporate import CorporateBootstrapRequest
from ai_stp_contracts.technology import TechnologyDecisionRequest, TechnologySeedRequest
from ai_stp_contracts.technology_seed import SEED_TECHNOLOGIES
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateMutationReceipt,
    CorporateRolePermission,
    Organization,
)
from ai_stp_platform.technology_models import OrganizationTechnologyDecision, Technology


async def test_replay_reauthorizes_approval_and_revocation_but_not_independent_adoption(
    db_session: AsyncSession,
) -> None:
    account_id = new_id("account")
    db_session.add(Account(id=account_id, status="active"))
    await db_session.flush()
    ctx = AuthContext(account_id, "decision-replay", None, "active", False, False)
    org = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Approval replay",
                superadmin_account_id=account_id,
                idempotency_key="approval-bootstrap-0001",
            ),
            request_id="approval-replay",
        )
    ).organization_id
    await import_seed(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=TechnologySeedRequest(
            authorization_revision=1, idempotency_key="approval-seed-0001"
        ),
        request_id="approval-replay",
    )
    tech = SEED_TECHNOLOGIES[0][0]
    requests = [
        TechnologyDecisionRequest(
            expected_revision=revision,
            authorization_revision=revision + 2,
            idempotency_key=f"approval-decision-{revision}-0001",
            approved=revision == 0,
            adoption="trial" if revision == 2 else "none",
        )
        for revision in range(3)
    ]
    responses = [
        await write_technology_decision(
            db_session,
            ctx=ctx,
            organization_id=org,
            technology_id=tech,
            payload=request,
            request_id="approval-replay",
        )
        for request in requests
    ]
    assert [response.revision for response in responses] == [1, 2, 3]
    receipts = list(
        (
            await db_session.scalars(
                select(CorporateMutationReceipt)
                .where(
                    CorporateMutationReceipt.organization_id == org,
                    CorporateMutationReceipt.operation == "technology.decision.update",
                )
                .order_by(CorporateMutationReceipt.idempotency_key)
            )
        ).all()
    )
    assert [
        cast(dict[str, bool], receipt.response_body["_mutation_effect"])["approval_changed"]
        for receipt in receipts
    ] == [True, True, False]
    await db_session.execute(
        delete(CorporateRolePermission).where(
            CorporateRolePermission.organization_id == org,
            CorporateRolePermission.permission == "technology.approve",
        )
    )
    organization = await db_session.get(Organization, org)
    assert organization is not None
    organization.policy_revision += 1
    await db_session.flush()
    for request in requests[:2]:
        with pytest.raises(ApiError) as denied:
            await write_technology_decision(
                db_session,
                ctx=ctx,
                organization_id=org,
                technology_id=tech,
                payload=request,
                request_id="approval-replay-denied",
            )
        assert denied.value.category == ErrorCategory.PERMISSION
    replayed = await write_technology_decision(
        db_session,
        ctx=ctx,
        organization_id=org,
        technology_id=tech,
        payload=requests[2],
        request_id="adoption-replay",
    )
    assert replayed == responses[2]
    assert "_mutation_effect" not in replayed.model_dump()
    legacy_request = requests[2].model_copy(
        update={"idempotency_key": "approval-legacy-trial-0001"}
    )
    db_session.add(
        CorporateMutationReceipt(
            organization_id=org,
            idempotency_key=legacy_request.idempotency_key,
            operation="technology.decision.update",
            request_fingerprint=mutation_effect(legacy_request, tech),
            response_body=responses[2].model_dump(mode="json"),
        )
    )
    await db_session.flush()
    with pytest.raises(ApiError) as legacy_denied:
        await write_technology_decision(
            db_session,
            ctx=ctx,
            organization_id=org,
            technology_id=tech,
            payload=legacy_request,
            request_id="legacy-adoption-replay",
        )
    assert legacy_denied.value.category == ErrorCategory.PERMISSION
    db_session.add(
        CorporateRolePermission(
            organization_id=org, role="superadmin", permission="technology.approve"
        )
    )
    organization.policy_revision += 1
    await db_session.flush()
    for request, response in zip(requests, responses, strict=True):
        assert (
            await write_technology_decision(
                db_session,
                ctx=ctx,
                organization_id=org,
                technology_id=tech,
                payload=request,
                request_id="authorized-approval-replay",
            )
            == response
        )
    technology = await db_session.get(Technology, (org, tech))
    assert technology is not None
    technology.lifecycle = "archived"
    await db_session.flush()
    clear_request = TechnologyDecisionRequest(
        expected_revision=3,
        authorization_revision=organization.policy_revision,
        idempotency_key="approval-clear-archived-0001",
        approved=False,
        adoption="none",
    )
    cleared = await write_technology_decision(
        db_session,
        ctx=ctx,
        organization_id=org,
        technology_id=tech,
        payload=clear_request,
        request_id="clear-archived-decision",
        remove=True,
    )
    assert cleared.revision == 4
    assert cleared.adoption == "none"
    retained = await db_session.get(OrganizationTechnologyDecision, (org, tech))
    assert retained is not None and retained.revision == 4
    assert (
        await write_technology_decision(
            db_session,
            ctx=ctx,
            organization_id=org,
            technology_id=tech,
            payload=clear_request,
            request_id="clear-archived-replay",
            remove=True,
        )
        == cleared
    )
    with pytest.raises(ApiError) as missing_decision:
        await write_technology_decision(
            db_session,
            ctx=ctx,
            organization_id=org,
            technology_id=SEED_TECHNOLOGIES[1][0],
            payload=clear_request.model_copy(
                update={
                    "expected_revision": 0,
                    "authorization_revision": organization.policy_revision,
                    "idempotency_key": "approval-clear-missing-0001",
                }
            ),
            request_id="clear-missing-decision",
            remove=True,
        )
    assert missing_decision.value.category == ErrorCategory.CONFLICT
