"""Detector proposals and immutable mappings never replace reviewed manual facts."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import bootstrap, create_project
from ai_stp_api.slices.technology.detection import (
    list_mappings,
    publish_mapping,
    publish_scan,
    read_mapping,
    read_scan,
    read_unmapped,
    review_unmapped,
)
from ai_stp_api.slices.technology.service import (
    change_category_lifecycle,
    change_lifecycle,
    import_seed,
    write_category,
    write_project_technology,
)
from ai_stp_contracts.corporate import CorporateBootstrapRequest, CorporateProjectCreateRequest
from ai_stp_contracts.technology import (
    CategoryLifecycleRequest,
    CategoryWriteRequest,
    ProjectTechnologyWriteRequest,
    TechnologyLifecycleRequest,
    TechnologyMappingRequest,
    TechnologyScanRequest,
    TechnologySeedRequest,
    TechnologyUnmappedReviewRequest,
)
from ai_stp_contracts.technology_seed import SEED_COORDINATES_VERSION, SEED_TECHNOLOGIES
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.organization_models import Organization
from ai_stp_platform.technology_models import (
    TechnologyCoordinateMapping,
    TechnologyScan,
    TechnologyUnmappedCoordinate,
)


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


async def test_unmapped_coordinates_form_the_organizations_review_queue(
    db_session: AsyncSession,
) -> None:
    account_id = new_id("account")
    db_session.add(Account(id=account_id, status="active"))
    await db_session.flush()
    ctx = AuthContext(account_id, "unmapped-test", None, "active", False, False)
    org = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Unmapped acceptance",
                superadmin_account_id=account_id,
                idempotency_key="unmapped-bootstrap-0001",
            ),
            request_id="unmapped-test",
        )
    ).organization_id
    await import_seed(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=TechnologySeedRequest(
            authorization_revision=1, idempotency_key="unmapped-seed-0001"
        ),
        request_id="unmapped-test",
    )
    # Importing the seed also installs its coordinate snapshot, so a fresh
    # organization resolves scans without authoring a mapping first.
    seeded = await read_mapping(
        db_session,
        ctx=ctx,
        organization_id=org,
        version=SEED_COORDINATES_VERSION,
        request_id="unmapped-test",
    )
    assert seeded.entries
    first = await create_project(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=CorporateProjectCreateRequest(
            name="Queue project one",
            authorization_revision=2,
            idempotency_key="unmapped-project-one-0001",
        ),
        request_id="unmapped-test",
    )
    second = await create_project(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=CorporateProjectCreateRequest(
            name="Queue project two",
            authorization_revision=3,
            idempotency_key="unmapped-project-two-0001",
        ),
        request_id="unmapped-test",
    )

    async def scan(
        *,
        project_id: str,
        scope: str,
        coordinates: list[dict[str, str]],
        revision: int,
        authorization: int,
    ) -> None:
        await publish_scan(
            db_session,
            ctx=ctx,
            organization_id=org,
            project_id=project_id,
            payload=TechnologyScanRequest.model_validate(
                {
                    "authorization_revision": authorization,
                    "expected_revision": revision,
                    "idempotency_key": f"unmapped-scan-{authorization}-0001",
                    "handoff": {
                        "organization_id": org,
                        "project_id": project_id,
                        "scan_id": new_id("scan"),
                        "scope": scope,
                        "complete": True,
                        "detector_version": "v1",
                        "mapping_version": SEED_COORDINATES_VERSION,
                        "observations": [],
                        "unmapped_coordinates": coordinates,
                    },
                }
            ),
            request_id="unmapped-test",
        )

    await scan(
        project_id=first.project_id,
        scope="dependencies",
        coordinates=[
            {"kind": "package", "coordinate": "left-pad-x"},
            {"kind": "image", "coordinate": "quay.io/acme/widget"},
        ],
        revision=1,
        authorization=4,
    )
    view = await read_unmapped(db_session, ctx=ctx, organization_id=org, request_id="unmapped-test")
    assert view.organization_id == org
    assert [(entry.kind, entry.coordinate, entry.project_ids) for entry in view.coordinates] == [
        ("image", "quay.io/acme/widget", [first.project_id]),
        ("package", "left-pad-x", [first.project_id]),
    ]
    # The same coordinate from another project groups into one queue entry.
    await scan(
        project_id=second.project_id,
        scope="dependencies",
        coordinates=[{"kind": "package", "coordinate": "left-pad-x"}],
        revision=1,
        authorization=5,
    )
    view = await read_unmapped(db_session, ctx=ctx, organization_id=org, request_id="unmapped-test")
    left_pad = next(entry for entry in view.coordinates if entry.coordinate == "left-pad-x")
    assert left_pad.project_ids == sorted([first.project_id, second.project_id])
    # A different scope reporting the same coordinate is its own row — the two
    # scopes must not collide on identity.
    await scan(
        project_id=first.project_id,
        scope="container",
        coordinates=[{"kind": "image", "coordinate": "quay.io/acme/widget"}],
        revision=2,
        authorization=6,
    )
    # Rescanning a scope replaces only that scope's rows: the widget stays
    # queued through the container scope even after dependencies drops it.
    await scan(
        project_id=first.project_id,
        scope="dependencies",
        coordinates=[{"kind": "package", "coordinate": "left-pad-x"}],
        revision=3,
        authorization=7,
    )
    view = await read_unmapped(db_session, ctx=ctx, organization_id=org, request_id="unmapped-test")
    widget = next(entry for entry in view.coordinates if entry.coordinate == "quay.io/acme/widget")
    assert widget.project_ids == [first.project_id]
    await scan(
        project_id=first.project_id,
        scope="container",
        coordinates=[],
        revision=4,
        authorization=8,
    )
    view = await read_unmapped(db_session, ctx=ctx, organization_id=org, request_id="unmapped-test")
    assert [entry.coordinate for entry in view.coordinates] == ["left-pad-x"]
    assert (
        await db_session.scalar(select(func.count()).select_from(TechnologyUnmappedCoordinate)) == 2
    )


async def test_review_queue_candidates_and_base_version_mapping(
    db_session: AsyncSession,
) -> None:
    account_id = new_id("account")
    db_session.add(Account(id=account_id, status="active"))
    await db_session.flush()
    ctx = AuthContext(account_id, "review-test", None, "active", False, False)
    org = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Review acceptance",
                superadmin_account_id=account_id,
                idempotency_key="review-bootstrap-0001",
            ),
            request_id="review-test",
        )
    ).organization_id
    await import_seed(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=TechnologySeedRequest(authorization_revision=1, idempotency_key="review-seed-0001"),
        request_id="review-test",
    )
    technology_id = SEED_TECHNOLOGIES[0][0]
    project = await create_project(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=CorporateProjectCreateRequest(
            name="Review project",
            authorization_revision=2,
            idempotency_key="review-project-0001",
        ),
        request_id="review-test",
    )

    async def scan(coordinates: list[dict[str, str]], revision: int, authorization: int) -> None:
        await publish_scan(
            db_session,
            ctx=ctx,
            organization_id=org,
            project_id=project.project_id,
            payload=TechnologyScanRequest.model_validate(
                {
                    "authorization_revision": authorization,
                    "expected_revision": revision,
                    "idempotency_key": f"review-scan-{authorization}-0001",
                    "handoff": {
                        "organization_id": org,
                        "project_id": project.project_id,
                        "scan_id": new_id("scan"),
                        "scope": "dependencies",
                        "complete": True,
                        "detector_version": "v1",
                        "mapping_version": SEED_COORDINATES_VERSION,
                        "observations": [],
                        "unmapped_coordinates": coordinates,
                    },
                }
            ),
            request_id="review-test",
        )

    await scan([{"kind": "package", "coordinate": "dagster"}], revision=1, authorization=3)

    # A reviewer proposes the coordinate is the seed technology: the queue
    # entry gains a candidate while staying open.
    reviewed = await review_unmapped(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=TechnologyUnmappedReviewRequest(
            authorization_revision=4,
            idempotency_key="review-propose-0001",
            kind="package",
            coordinate="dagster",
            candidate_technology_id=technology_id,
        ),
        request_id="review-test",
    )
    assert reviewed.candidate_technology_id == technology_id
    assert reviewed.state == "open"
    view = await read_unmapped(db_session, ctx=ctx, organization_id=org, request_id="review-test")
    assert view.coordinates[0].candidate_technology_id == technology_id

    # A rescan replaces the project's rows but keeps the org-wide candidate.
    await scan([{"kind": "package", "coordinate": "dagster"}], revision=2, authorization=5)
    view = await read_unmapped(db_session, ctx=ctx, organization_id=org, request_id="review-test")
    assert view.coordinates[0].candidate_technology_id == technology_id

    # Reviewing a coordinate the queue does not hold is refused.
    with pytest.raises(ApiError, match="unmapped coordinate is unavailable"):
        await review_unmapped(
            db_session,
            ctx=ctx,
            organization_id=org,
            payload=TechnologyUnmappedReviewRequest(
                authorization_revision=5,
                idempotency_key="review-missing-0001",
                kind="package",
                coordinate="never-reported",
                candidate_technology_id=technology_id,
            ),
            request_id="review-test",
        )

    # Publishing a derived snapshot marks covered queue rows resolved and
    # lists every version.
    applied = await publish_mapping(
        db_session,
        ctx=ctx,
        organization_id=org,
        version="v2",
        payload=TechnologyMappingRequest.model_validate(
            {
                "authorization_revision": 6,
                "idempotency_key": "review-apply-0001",
                "base_version": SEED_COORDINATES_VERSION,
                "entries": [
                    {
                        "kind": "package",
                        "coordinate": "dagster",
                        "technology_id": technology_id,
                        "provenance": "reviewed-v2",
                    }
                ],
            }
        ),
        request_id="review-test",
    )
    assert "dagster" in {entry.coordinate for entry in applied.entries}
    assert len(applied.entries) > 1
    view = await read_unmapped(db_session, ctx=ctx, organization_id=org, request_id="review-test")
    entry = next(item for item in view.coordinates if item.coordinate == "dagster")
    assert entry.state == "resolved"
    assert entry.resolved_technology_id == technology_id

    versions = await list_mappings(
        db_session, ctx=ctx, organization_id=org, request_id="review-test"
    )
    assert [item.version for item in versions.items] == [SEED_COORDINATES_VERSION, "v2"]

    # An unknown base snapshot is refused.
    with pytest.raises(ApiError, match="base mapping snapshot is unavailable"):
        await publish_mapping(
            db_session,
            ctx=ctx,
            organization_id=org,
            version="v3",
            payload=TechnologyMappingRequest.model_validate(
                {
                    "authorization_revision": 7,
                    "idempotency_key": "review-apply-bad-0001",
                    "base_version": "v-missing",
                    "entries": [
                        {
                            "kind": "package",
                            "coordinate": "x",
                            "technology_id": technology_id,
                            "provenance": "reviewed-v3",
                        }
                    ],
                }
            ),
            request_id="review-test",
        )


async def test_category_draft_lifecycle(
    db_session: AsyncSession,
) -> None:
    account_id = new_id("account")
    db_session.add(Account(id=account_id, status="active"))
    await db_session.flush()
    ctx = AuthContext(account_id, "category-draft", None, "active", False, False)
    org = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Category draft acceptance",
                superadmin_account_id=account_id,
                idempotency_key="catdraft-bootstrap-0001",
            ),
            request_id="category-draft",
        )
    ).organization_id
    draft = await write_category(
        db_session,
        ctx=ctx,
        organization_id=org,
        category_id=None,
        payload=CategoryWriteRequest.model_validate(
            {
                "authorization_revision": 1,
                "expected_revision": 0,
                "idempotency_key": "catdraft-create-0001",
                "metadata": {"name": "ETL engines"},
                "state": "draft",
            }
        ),
        request_id="category-draft",
    )
    assert draft.state == "draft"
    published = await change_category_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org,
        category_id=draft.category_id,
        payload=CategoryLifecycleRequest.model_validate(
            {
                "authorization_revision": 2,
                "expected_revision": 1,
                "idempotency_key": "catdraft-activate-0001",
                "target": "active",
            }
        ),
        request_id="category-draft",
    )
    assert published.state == "active"
    demoted = await change_category_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org,
        category_id=draft.category_id,
        payload=CategoryLifecycleRequest.model_validate(
            {
                "authorization_revision": 3,
                "expected_revision": 2,
                "idempotency_key": "catdraft-demote-0001",
                "target": "draft",
            }
        ),
        request_id="category-draft",
    )
    assert demoted.state == "draft"
