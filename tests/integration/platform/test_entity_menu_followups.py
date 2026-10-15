"""Real persistence regressions for draft assignments, owners and contextual unlink."""

import uuid
from typing import Literal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration.platform.test_repository_scan import (
    _bootstrap_org,  # pyright: ignore[reportPrivateUsage]
)
from tests.support.catalog_seed import seed_corpus, upsert_seed_version

from ai_stp_api.errors import ApiError
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate import assignments, entity_profiles, service
from ai_stp_api.slices.entity_actions.service import read_menu
from ai_stp_contracts.corporate import (
    CorporateCatalogAssignmentRequest,
    CorporateMemberCreateRequest,
    CorporatePermissionGrantRequest,
)
from ai_stp_contracts.corporate_profiles import EntityProfileSubject, TechnologyOwnerRequest
from ai_stp_contracts.entity_actions import EntityActionSubject
from ai_stp_foundation.ids import new_id
from ai_stp_platform.catalog_search import search_catalog
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import (
    CorporateCatalogLifecycle,
    CorporateMutationReceipt,
    Organization,
)
from ai_stp_platform.technology_models import Technology


@pytest.mark.parametrize("lifecycle", ["draft", "active", "deprecated", "archived"])
async def test_technology_assignment_owner_and_unlink(
    db_session: AsyncSession, lifecycle: str
) -> None:
    ctx, org, _ = await _bootstrap_org(db_session)
    staff = await service.create_member(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=CorporateMemberCreateRequest(
            display_name="Staff",
            email="staff@example.test",
            role="staff",
            authorization_revision=1,
            idempotency_key=uuid.uuid4().hex,
        ),
        request_id=None,
    )
    organization = await db_session.get(Organization, org)
    assert organization is not None
    revision = organization.policy_revision
    kind, passport, published_at, digest = seed_corpus()[0]
    db_session.add(Account(id=str(passport["owner_id"]), status="active"))
    tech = Technology(
        organization_id=org,
        id=new_id("technology"),
        name="Assignment target",
        provenance="manual",
        lifecycle=lifecycle,
    )
    db_session.add(tech)
    await db_session.flush()
    metadata, _ = await upsert_seed_version(
        db_session,
        object_kind=kind,
        passport=passport,
        published_at_wire=published_at,
        passport_digest=digest,
    )
    payload = CorporateCatalogAssignmentRequest(
        subject_kind="technology",
        subject_id=tech.id,
        object_kind="component",
        stable_id=metadata.stable_id,
        selector="latest",
        authorization_revision=revision,
        idempotency_key=uuid.uuid4().hex,
        expected_revision=0,
    )
    if lifecycle == "archived":
        with pytest.raises(ApiError, match="assignment subject is unavailable"):
            await assignments.write_assignment(
                db_session, ctx=ctx, organization_id=org, payload=payload, request_id=None
            )
        return
    result = await assignments.write_assignment(
        db_session, ctx=ctx, organization_id=org, payload=payload, request_id=None
    )
    replay = await assignments.write_assignment(
        db_session, ctx=ctx, organization_id=org, payload=payload, request_id=None
    )
    assert replay == result and result.revision == 1
    organization.policy_revision += 1
    await db_session.flush()
    revision = organization.policy_revision
    refreshed_payload = payload.model_copy(update={"authorization_revision": revision})
    refreshed_replay = await assignments.write_assignment(
        db_session, ctx=ctx, organization_id=org, payload=refreshed_payload, request_id=None
    )
    assert refreshed_replay == result
    receipt = await db_session.get(CorporateMutationReceipt, (org, payload.idempotency_key))
    assert receipt is not None
    receipt.request_fingerprint = service.mutation_fingerprint(
        refreshed_payload.model_dump(mode="json", exclude={"idempotency_key"})
    )
    await db_session.flush()
    legacy_replay = await assignments.write_assignment(
        db_session, ctx=ctx, organization_id=org, payload=refreshed_payload, request_id=None
    )
    assert legacy_replay == result
    with pytest.raises(ApiError, match="idempotency"):
        await assignments.write_assignment(
            db_session,
            ctx=ctx,
            organization_id=org,
            payload=refreshed_payload.model_copy(update={"state": "retired"}),
            request_id=None,
        )
    subject = EntityActionSubject(
        kind="component",
        id=metadata.stable_id,
        organization_id=org,
        assignment_id=result.assignment_id,
    )
    menu = await read_menu(db_session, ctx=ctx, subject=subject)
    assert "unlink" in [action.id for action in menu.actions]
    assert "manage_access" in [action.id for action in menu.actions]
    staff_ctx = AuthContext(staff.account_id, "staff", None, "active", False, False)
    staff_menu = await read_menu(db_session, ctx=staff_ctx, subject=subject)
    assert "unlink" not in [action.id for action in staff_menu.actions]
    assert "manage_access" not in [action.id for action in staff_menu.actions]
    ordinary = await read_menu(
        db_session, ctx=ctx, subject=subject.model_copy(update={"assignment_id": None})
    )
    assert "unlink" not in [action.id for action in ordinary.actions]
    technology_subject = EntityActionSubject(kind="technology", id=tech.id, organization_id=org)
    owner_menu = await read_menu(db_session, ctx=ctx, subject=technology_subject)
    assert "change_owner" in [action.id for action in owner_menu.actions]
    if lifecycle == "draft":
        with pytest.raises(ApiError, match="entity access denied"):
            await read_menu(db_session, ctx=staff_ctx, subject=technology_subject)
    else:
        await service.create_permission_grant(
            db_session,
            ctx=ctx,
            organization_id=org,
            payload=CorporatePermissionGrantRequest(
                account_id=staff.account_id,
                permission="technology.read",
                scope_kind="technology",
                scope_id=tech.id,
                authorization_revision=revision,
                idempotency_key=uuid.uuid4().hex,
            ),
            request_id=None,
        )
        revision = organization.policy_revision
        member_menu = await read_menu(db_session, ctx=staff_ctx, subject=technology_subject)
        assert "change_owner" not in [action.id for action in member_menu.actions]
    if lifecycle != "draft":
        await service.create_permission_grant(
            db_session,
            ctx=ctx,
            organization_id=org,
            payload=CorporatePermissionGrantRequest(
                account_id=staff.account_id,
                permission="technology.update",
                scope_kind="technology",
                scope_id=tech.id,
                authorization_revision=revision,
                idempotency_key=uuid.uuid4().hex,
            ),
            request_id=None,
        )
        revision = organization.policy_revision
        editor_menu = await read_menu(db_session, ctx=staff_ctx, subject=technology_subject)
        assert "edit" in [action.id for action in editor_menu.actions]
        assert "change_owner" not in [action.id for action in editor_menu.actions]
    owner_payload = TechnologyOwnerRequest(
        owner_account_id=staff.account_id,
        expected_revision=tech.profile_revision or 0,
        authorization_revision=revision,
        idempotency_key=uuid.uuid4().hex,
    )
    with pytest.raises(ApiError, match="capability is forbidden"):
        await entity_profiles.write_profile(
            db_session,
            ctx=staff_ctx,
            organization_id=org,
            subject=EntityProfileSubject(subject_kind="technology", subject_id=tech.id),
            payload=owner_payload,
            request_id=None,
        )
    updated = await entity_profiles.write_profile(
        db_session,
        ctx=ctx,
        organization_id=org,
        subject=EntityProfileSubject(subject_kind="technology", subject_id=tech.id),
        payload=owner_payload,
        request_id=None,
    )
    assert updated.owner_account_id == staff.account_id
    organization.policy_revision += 1
    await db_session.flush()
    owner_replay = await entity_profiles.write_profile(
        db_session,
        ctx=ctx,
        organization_id=org,
        subject=EntityProfileSubject(subject_kind="technology", subject_id=tech.id),
        payload=owner_payload.model_copy(
            update={"authorization_revision": organization.policy_revision}
        ),
        request_id=None,
    )
    assert owner_replay == updated
    foreign = subject.model_copy(update={"id": new_id("component")})
    with pytest.raises(ApiError):
        await read_menu(db_session, ctx=ctx, subject=foreign)


async def test_public_catalog_is_discoverable_before_assignment(db_session: AsyncSession) -> None:
    ctx, org, _ = await _bootstrap_org(db_session)
    kind, passport, published_at, digest = seed_corpus()[0]
    db_session.add(Account(id=str(passport["owner_id"]), status="active"))
    await db_session.flush()
    metadata, _ = await upsert_seed_version(
        db_session,
        object_kind=kind,
        passport=passport,
        published_at_wire=published_at,
        passport_digest=digest,
    )

    async def search(assignment: Literal["direct"] | None = None):
        return await search_catalog(
            db_session,
            object_kind=kind,
            q=None,
            tags=[],
            harness_id=None,
            component_type=None,
            harness_ids=[],
            component_types=[],
            authors=[],
            sort="updated",
            sort_direction="desc",
            support_tier=None,
            support_state=None,
            service_domain=None,
            country_code=None,
            service_domains=[],
            country_codes=[],
            include_experimental=True,
            include_deprecated=False,
            page_size=20,
            page_number=1,
            after=None,
            query_expression=None,
            updated_from=None,
            updated_to=None,
            corporate_organization_id=org,
            corporate_assignment=assignment,
            corporate_account_id=ctx.account_id if assignment else None,
        )

    hits = await search()
    assert [row.metadata.stable_id for row in hits.rows] == [metadata.stable_id]
    filtered = await search("direct")
    assert filtered.rows == []
    db_session.add(
        CorporateCatalogLifecycle(
            organization_id=org,
            object_kind=kind,
            stable_id=metadata.stable_id,
            version=metadata.version,
            state="hidden",
            revision=1,
        )
    )
    await db_session.flush()
    hidden = await search()
    assert hidden.rows == []
