"""Detector proposals and immutable mappings never replace reviewed manual facts."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import bootstrap, create_project
from ai_stp_api.slices.technology.detection import (
    publish_mapping,
    publish_scan,
    read_mapping,
    read_scan,
)
from ai_stp_api.slices.technology.service import (
    change_lifecycle,
    import_seed,
    write_project_technology,
)
from ai_stp_contracts.corporate import CorporateBootstrapRequest, CorporateProjectCreateRequest
from ai_stp_contracts.technology import (
    ProjectTechnologyWriteRequest,
    TechnologyLifecycleRequest,
    TechnologyMappingRequest,
    TechnologyScanRequest,
    TechnologySeedRequest,
)
from ai_stp_contracts.technology_seed import SEED_TECHNOLOGIES
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import Organization
from ai_stp_platform.technology_models import TechnologyCoordinateMapping, TechnologyScan


async def test_mapping_and_scan_replay_review_disagreement_and_scope(
    db_session: AsyncSession,
) -> None:
    account_id = new_id("account")
    db_session.add(Account(id=account_id, status="active"))
    await db_session.flush()
    ctx = AuthContext(account_id, "detection-test", None, "active", False, False)
    org = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Detection acceptance",
                superadmin_account_id=account_id,
                idempotency_key="detection-bootstrap-0001",
            ),
            request_id="detection-test",
        )
    ).organization_id
    await import_seed(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=TechnologySeedRequest(
            authorization_revision=1, idempotency_key="detection-seed-0001"
        ),
        request_id="detection-test",
    )
    technology_id = SEED_TECHNOLOGIES[0][0]
    await change_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org,
        technology_id=technology_id,
        payload=TechnologyLifecycleRequest(
            lifecycle="active",
            expected_revision=1,
            authorization_revision=2,
            idempotency_key="detection-approve-0001",
        ),
        request_id="detection-test",
    )
    project = await create_project(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=CorporateProjectCreateRequest(
            name="Explicit linked project",
            authorization_revision=3,
            idempotency_key="detection-project-0001",
        ),
        request_id="detection-test",
    )
    mapping_request = TechnologyMappingRequest.model_validate(
        {
            "authorization_revision": 4,
            "idempotency_key": "detection-mapping-0001",
            "entries": [
                {
                    "kind": "executable",
                    "coordinate": "bun",
                    "technology_id": technology_id,
                    "provenance": "reviewed-catalog-v1",
                }
            ],
        }
    )
    mapping = await publish_mapping(
        db_session,
        ctx=ctx,
        organization_id=org,
        version="v1",
        payload=mapping_request,
        request_id="detection-test",
    )
    assert (
        await read_mapping(
            db_session, ctx=ctx, organization_id=org, version="v1", request_id="detection-test"
        )
        == mapping
    )
    assert (
        await publish_mapping(
            db_session,
            ctx=ctx,
            organization_id=org,
            version="v1",
            payload=mapping_request,
            request_id="detection-test",
        )
        == mapping
    )
    changed = mapping_request.model_copy(
        update={
            "authorization_revision": 5,
            "idempotency_key": "detection-mapping-change-0001",
            "entries": [mapping_request.entries[0].model_copy(update={"coordinate": "other"})],
        }
    )
    with pytest.raises(ApiError, match="immutable"):
        await publish_mapping(
            db_session,
            ctx=ctx,
            organization_id=org,
            version="v1",
            payload=changed,
            request_id="detection-test",
        )
    assert (
        await db_session.scalar(select(func.count()).select_from(TechnologyCoordinateMapping)) == 1
    )

    async def scan(
        *, scope: str, complete: bool, version: str | None, revision: int, authorization: int
    ) -> TechnologyScanRequest:
        return TechnologyScanRequest.model_validate(
            {
                "authorization_revision": authorization,
                "expected_revision": revision,
                "idempotency_key": f"detection-scan-{revision}-0001",
                "handoff": {
                    "organization_id": org,
                    "project_id": project.project_id,
                    "scan_id": new_id("scan"),
                    "scope": scope,
                    "complete": complete,
                    "detector_version": "v1",
                    "mapping_version": "v1",
                    "observations": []
                    if version is None
                    else [
                        {
                            "technology_id": technology_id,
                            "fact": {
                                "context": "production",
                                "version": version,
                                "version_kind": "observed_version",
                                "evidence": [
                                    {
                                        "source": "observed",
                                        "path": "bun.lock",
                                        "observed_at": "2026-09-12T00:00:00.000Z",
                                        "detector_version": "v1",
                                        "mapping_version": "v1",
                                    }
                                ],
                            },
                        }
                    ],
                },
            }
        )

    request = await scan(
        scope="dependencies", complete=True, version="1.2.3", revision=1, authorization=5
    )
    proposed = await publish_scan(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project.project_id,
        payload=request,
        request_id="detection-test",
    )
    assert proposed.project_revision == 2
    assert proposed.usages[0].facts[0].review == "proposed"
    assert proposed.usages[0].facts[0].freshness == "current"
    assert (
        await publish_scan(
            db_session,
            ctx=ctx,
            organization_id=org,
            project_id=project.project_id,
            payload=request,
            request_id="detection-test",
        )
        == proposed
    )
    original = proposed.usages[0]
    confirmed = await write_project_technology(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project.project_id,
        payload=ProjectTechnologyWriteRequest.model_validate(
            {
                "technology_id": technology_id,
                "expected_revision": original.revision,
                "authorization_revision": 6,
                "idempotency_key": "detection-owner-confirm-0001",
                "fact": request.handoff.observations[0].fact.model_dump(mode="json"),
                "review": "confirmed",
            }
        ),
        request_id="detection-test",
    )
    disagreement = await publish_scan(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project.project_id,
        payload=await scan(
            scope="dependencies", complete=True, version="2.0.0", revision=2, authorization=7
        ),
        request_id="detection-test",
    )
    assert disagreement.disagreements[0].fact.version == "2.0.0"
    assert disagreement.usages[0].facts[0].version == "1.2.3"
    assert disagreement.usages[0].facts[0].evidence == confirmed.facts[0].evidence
    assert disagreement.usages[0].facts[0].review == "confirmed"
    assert disagreement.usages[0].facts[0].freshness == "stale"
    different_scope = await publish_scan(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project.project_id,
        payload=await scan(
            scope="languages", complete=True, version=None, revision=3, authorization=8
        ),
        request_id="detection-test",
    )
    assert different_scope.usages == []
    incomplete = await publish_scan(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project.project_id,
        payload=await scan(
            scope="dependencies", complete=False, version=None, revision=4, authorization=9
        ),
        request_id="detection-test",
    )
    assert incomplete.usages[0].facts[0].freshness == "unknown"
    absent = await publish_scan(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project.project_id,
        payload=await scan(
            scope="dependencies", complete=True, version=None, revision=5, authorization=10
        ),
        request_id="detection-test",
    )
    assert absent.usages[0].facts[0].freshness == "absent"
    assert absent.usages[0].facts[0].review == "confirmed"
    assert absent.usages[0].facts[0].evidence == confirmed.facts[0].evidence
    history = await read_scan(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project.project_id,
        scan_id=request.handoff.scan_id,
        request_id="detection-test",
    )
    assert history.result == proposed and history.handoff == request.handoff
    # Failed identity and unknown-endpoint publication leave all history and revisions untouched.
    bad = await scan(
        scope="dependencies", complete=True, version="3.0.0", revision=6, authorization=11
    )
    bad = bad.model_copy(
        update={"handoff": bad.handoff.model_copy(update={"project_id": new_id("operation")})}
    )
    with pytest.raises(ApiError, match="identity"):
        await publish_scan(
            db_session,
            ctx=ctx,
            organization_id=org,
            project_id=project.project_id,
            payload=bad,
            request_id="detection-test",
        )
    unknown = await scan(
        scope="dependencies", complete=True, version="3.0.0", revision=6, authorization=11
    )
    unknown = unknown.model_copy(
        update={
            "handoff": unknown.handoff.model_copy(
                update={
                    "observations": [
                        unknown.handoff.observations[0].model_copy(
                            update={"technology_id": new_id("technology")}
                        )
                    ]
                }
            )
        }
    )
    with pytest.raises(ApiError, match="unavailable"):
        await publish_scan(
            db_session,
            ctx=ctx,
            organization_id=org,
            project_id=project.project_id,
            payload=unknown,
            request_id="detection-test",
        )
    assert await db_session.scalar(select(func.count()).select_from(TechnologyScan)) == 5
    organization = await db_session.get(Organization, org)
    assert organization is not None and organization.policy_revision == 11
