"""Detector proposals and immutable mappings never replace reviewed manual facts."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.errors import ApiError
from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import bootstrap, create_project
from ai_stp_api.slices.technology.detection import (
    launch_scans,
    list_mappings,
    list_scans,
    publish_mapping,
    publish_scan,
    read_mapping,
    read_scan,
    read_scan_detail,
    read_unmapped,
    review_unmapped,
)
from ai_stp_api.slices.technology.service import (
    change_area_lifecycle,
    change_category_lifecycle,
    change_lifecycle,
    import_seed,
    list_areas,
    read_area,
    write_area,
    write_category,
    write_project_technology,
)
from ai_stp_contracts.corporate import CorporateBootstrapRequest, CorporateProjectCreateRequest
from ai_stp_contracts.technology import (
    AreaLifecycleRequest,
    AreaWriteRequest,
    CategoryLifecycleRequest,
    CategoryWriteRequest,
    ProjectTechnologyWriteRequest,
    TechnologyLifecycleRequest,
    TechnologyMappingRequest,
    TechnologyScanLaunchRequest,
    TechnologyScanRequest,
    TechnologySeedRequest,
    TechnologyUnmappedReviewRequest,
)
from ai_stp_contracts.technology_seed import SEED_COORDINATES_VERSION, SEED_TECHNOLOGIES
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account, Device
from ai_stp_platform.organization_models import Organization, ProjectIdentity, ProjectLink
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
    seeded_mappings = await db_session.scalar(
        select(func.count()).select_from(TechnologyCoordinateMapping)
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
        await db_session.scalar(select(func.count()).select_from(TechnologyCoordinateMapping))
        == (seeded_mappings or 0) + 1
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
                authorization_revision=6,
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


async def test_scan_journal_launch_and_detail(
    db_session: AsyncSession,
) -> None:
    """The journal lists published scans; launch rejects unlinked projects."""
    account_id = new_id("account")
    db_session.add(Account(id=account_id, status="active"))
    await db_session.flush()
    ctx = AuthContext(account_id, "journal-test", None, "active", False, False)
    org = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Scan journal acceptance",
                superadmin_account_id=account_id,
                idempotency_key="journal-bootstrap-0001",
            ),
            request_id="journal-test",
        )
    ).organization_id
    await import_seed(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=TechnologySeedRequest(
            authorization_revision=1, idempotency_key="journal-seed-0001"
        ),
        request_id="journal-test",
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
            idempotency_key="journal-approve-0001",
        ),
        request_id="journal-test",
    )
    first = await create_project(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=CorporateProjectCreateRequest(
            name="Scanned project",
            authorization_revision=3,
            idempotency_key="journal-project-0001",
        ),
        request_id="journal-test",
    )
    second = await create_project(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=CorporateProjectCreateRequest(
            name="Unscanned project",
            authorization_revision=4,
            idempotency_key="journal-project-0002",
        ),
        request_id="journal-test",
    )
    third = await create_project(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=CorporateProjectCreateRequest(
            name="GitHub scanned project",
            authorization_revision=5,
            idempotency_key="journal-project-0003",
        ),
        request_id="journal-test",
    )
    scan_request = TechnologyScanRequest.model_validate(
        {
            "authorization_revision": 6,
            "expected_revision": 1,
            "idempotency_key": "journal-scan-0001",
            "source": "local",
            "handoff": {
                "organization_id": org,
                "project_id": first.project_id,
                "scan_id": new_id("scan"),
                "scope": "dependencies",
                "complete": True,
                "detector_version": "v1",
                "mapping_version": SEED_COORDINATES_VERSION,
                "observations": [
                    {
                        "technology_id": technology_id,
                        "fact": {
                            "context": "production",
                            "version": "1.2.3",
                            "version_kind": "observed_version",
                            "evidence": [
                                {
                                    "source": "observed",
                                    "path": "requirements.lock",
                                    "observed_at": "2026-09-12T00:00:00.000Z",
                                    "detector_version": "v1",
                                    "mapping_version": SEED_COORDINATES_VERSION,
                                }
                            ],
                        },
                    }
                ],
                "unmapped_coordinates": [
                    {
                        "kind": "package",
                        "coordinate": "pip:unknown-widget",
                        "context": "production",
                        "version": "0.9.0",
                        "evidence": [
                            {
                                "source": "declared",
                                "path": "requirements.txt",
                                "observed_at": "2026-09-12T00:00:00.000Z",
                                "detector_version": "v1",
                                "mapping_version": SEED_COORDINATES_VERSION,
                            }
                        ],
                    }
                ],
            },
        }
    )
    published = await publish_scan(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=first.project_id,
        payload=scan_request,
        request_id="journal-test",
    )

    journal = await list_scans(db_session, ctx=ctx, organization_id=org, request_id="journal-test")
    assert journal.total == 1
    entry = journal.items[0]
    assert entry.scan_id == published.scan_id
    assert entry.project_id == first.project_id
    assert entry.project_name == "Scanned project"
    assert entry.source == "local"
    assert entry.status == "succeeded"
    assert entry.found == 1
    assert entry.pending == 1

    filtered = await list_scans(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=second.project_id,
        request_id="journal-test",
    )
    assert filtered.total == 0

    detail = await read_scan_detail(
        db_session,
        ctx=ctx,
        organization_id=org,
        scan_id=published.scan_id,
        request_id="journal-test",
    )
    assert detail.project_id == first.project_id
    assert detail.source == "local"
    assert detail.status == "succeeded"
    assert detail.found == 1
    assert detail.pending == 1
    assert detail.detector_version == "v1"
    assert detail.mapping_version == SEED_COORDINATES_VERSION
    assert detail.complete is True
    states = {finding.coordinate: finding for finding in detail.findings}
    resolved = states[technology_id]
    assert resolved.state == "resolved"
    assert resolved.technology_id == technology_id
    assert resolved.version == "1.2.3"
    assert resolved.version_kind == "observed_version"
    assert resolved.evidence[0].path == "requirements.lock"
    opened = states["pip:unknown-widget"]
    assert opened.state == "open"
    assert opened.kind == "package"
    assert opened.technology_id is None
    assert opened.evidence[0].path == "requirements.txt"

    # A candidate review shows up in the scan detail without changing history.
    await review_unmapped(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=TechnologyUnmappedReviewRequest.model_validate(
            {
                "authorization_revision": 7,
                "idempotency_key": "journal-review-0001",
                "kind": "package",
                "coordinate": "pip:unknown-widget",
                "candidate_technology_id": technology_id,
            }
        ),
        request_id="journal-test",
    )
    detail = await read_scan_detail(
        db_session,
        ctx=ctx,
        organization_id=org,
        scan_id=published.scan_id,
        request_id="journal-test",
    )
    opened = {finding.coordinate: finding for finding in detail.findings}["pip:unknown-widget"]
    assert opened.state == "candidate"
    assert opened.candidate_technology_id == technology_id

    # A linked GitLab project queues a scan job; an unlinked one is rejected.
    device_id = new_id("device")
    db_session.add(Device(id=device_id, account_id=account_id, public_key="journal-device"))
    provider_id = new_id("provider_project")
    db_session.add(
        ProjectIdentity(
            id=provider_id,
            organization_id=org,
            namespace="provider",
            external_key=f"gitlab:{provider_id}",
            display_name="group/service",
            provider_kind="gitlab",
            state="active",
        )
    )
    await db_session.flush()
    db_session.add(
        ProjectLink(
            id=new_id("project_link"),
            plan_id=new_id("link_plan"),
            plan_digest="sha256:" + "a" * 64,
            organization_id=org,
            actor_account_id=account_id,
            device_id=device_id,
            local_project_id=new_id("project"),
            remote_project_id=second.project_id,
            provider_project_id=provider_id,
            state="linked",
            local_revision="local1",
            remote_revision="remote1",
            provider_revision="provider1",
            create_idempotency_key="journal-link-0001",
        )
    )
    github_provider_id = new_id("provider_project")
    db_session.add(
        ProjectIdentity(
            id=github_provider_id,
            organization_id=org,
            namespace="provider",
            external_key=f"github:{github_provider_id}",
            display_name="org/service",
            provider_kind="github",
            state="active",
        )
    )
    await db_session.flush()
    db_session.add(
        ProjectLink(
            id=new_id("project_link"),
            plan_id=new_id("link_plan"),
            plan_digest="sha256:" + "b" * 64,
            organization_id=org,
            actor_account_id=account_id,
            device_id=device_id,
            local_project_id=new_id("project"),
            remote_project_id=third.project_id,
            provider_project_id=github_provider_id,
            state="linked",
            local_revision="local1",
            remote_revision="remote1",
            provider_revision="provider1",
            create_idempotency_key="journal-link-0002",
        )
    )
    await db_session.flush()

    launch = await launch_scans(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=TechnologyScanLaunchRequest.model_validate(
            {
                "authorization_revision": 8,
                "idempotency_key": "journal-launch-0001",
                "project_ids": [first.project_id, second.project_id, third.project_id],
            }
        ),
        request_id="journal-test",
    )
    assert len(launch.items) == 3
    by_project = {item.project_id: item for item in launch.items}
    rejected = by_project[first.project_id]
    assert rejected.state == "rejected"
    assert "repository" in (rejected.detail or "")
    queued = by_project[second.project_id]
    assert queued.state == "queued"
    assert queued.scan_id is not None and queued.job_id is not None
    github_queued = by_project[third.project_id]
    assert github_queued.state == "queued"
    assert github_queued.scan_id is not None and github_queued.job_id is not None

    journal = await list_scans(db_session, ctx=ctx, organization_id=org, request_id="journal-test")
    assert journal.total == 3
    queued_row = {item.scan_id: item for item in journal.items}[queued.scan_id]
    assert queued_row.status == "queued"
    assert queued_row.source == "gitlab"
    assert queued_row.project_id == second.project_id
    assert queued_row.found == 0
    github_row = {item.scan_id: item for item in journal.items}[github_queued.scan_id]
    assert github_row.status == "queued"
    assert github_row.source == "github"
    assert github_row.project_id == third.project_id

    queued_detail = await read_scan_detail(
        db_session,
        ctx=ctx,
        organization_id=org,
        scan_id=queued.scan_id,
        request_id="journal-test",
    )
    assert queued_detail.status == "queued"
    assert queued_detail.findings == []

    filtered = await list_scans(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=second.project_id,
        request_id="journal-test",
    )
    assert [item.scan_id for item in filtered.items] == [queued.scan_id]

    # A replayed launch returns the stored receipt instead of new jobs.
    replay = await launch_scans(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=TechnologyScanLaunchRequest.model_validate(
            {
                "authorization_revision": 8,
                "idempotency_key": "journal-launch-0001",
                "project_ids": [first.project_id, second.project_id, third.project_id],
            }
        ),
        request_id="journal-test",
    )
    assert replay == launch


async def test_technology_area_lifecycle_and_category_binding(
    db_session: AsyncSession,
) -> None:
    """Areas carry draft→active→archived states and guard bound categories."""
    account_id = new_id("account")
    db_session.add(Account(id=account_id, status="active"))
    await db_session.flush()
    ctx = AuthContext(account_id, "area-test", None, "active", False, False)
    org = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Area acceptance",
                superadmin_account_id=account_id,
                idempotency_key="area-bootstrap-0001",
            ),
            request_id="area-test",
        )
    ).organization_id
    area = await write_area(
        db_session,
        ctx=ctx,
        organization_id=org,
        area_id=None,
        payload=AreaWriteRequest.model_validate(
            {
                "authorization_revision": 1,
                "expected_revision": 0,
                "idempotency_key": "area-create-0001",
                "metadata": {"name": "Data platform"},
                "state": "draft",
            }
        ),
        request_id="area-test",
    )
    assert area.state == "draft"
    activated = await change_area_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org,
        area_id=area.area_id,
        payload=AreaLifecycleRequest.model_validate(
            {
                "authorization_revision": 2,
                "expected_revision": 1,
                "idempotency_key": "area-activate-0001",
                "target": "active",
            }
        ),
        request_id="area-test",
    )
    assert activated.state == "active"

    bound = await write_category(
        db_session,
        ctx=ctx,
        organization_id=org,
        category_id=None,
        payload=CategoryWriteRequest.model_validate(
            {
                "authorization_revision": 3,
                "expected_revision": 0,
                "idempotency_key": "area-category-0001",
                "metadata": {"name": "Query engines"},
                "area_id": area.area_id,
            }
        ),
        request_id="area-test",
    )
    assert bound.area_id == area.area_id

    # An update without area_id preserves the binding.
    renamed = await write_category(
        db_session,
        ctx=ctx,
        organization_id=org,
        category_id=bound.category_id,
        payload=CategoryWriteRequest.model_validate(
            {
                "authorization_revision": 4,
                "expected_revision": 1,
                "idempotency_key": "area-category-0002",
                "metadata": {"name": "Query engine"},
            }
        ),
        request_id="area-test",
    )
    assert renamed.name == "Query engine"
    assert renamed.area_id == area.area_id

    # The area cannot be archived while a category is bound to it.
    with pytest.raises(ApiError, match="bound categories"):
        await change_area_lifecycle(
            db_session,
            ctx=ctx,
            organization_id=org,
            area_id=area.area_id,
            payload=AreaLifecycleRequest.model_validate(
                {
                    "authorization_revision": 5,
                    "expected_revision": 2,
                    "idempotency_key": "area-archive-0001",
                    "target": "archived",
                }
            ),
            request_id="area-test",
        )

    # An explicit null unbinds; the area then archives cleanly.
    unbound = await write_category(
        db_session,
        ctx=ctx,
        organization_id=org,
        category_id=bound.category_id,
        payload=CategoryWriteRequest.model_validate(
            {
                "authorization_revision": 5,
                "expected_revision": 2,
                "idempotency_key": "area-category-0003",
                "metadata": {"name": "Query engine"},
                "area_id": None,
            }
        ),
        request_id="area-test",
    )
    assert unbound.area_id is None
    archived = await change_area_lifecycle(
        db_session,
        ctx=ctx,
        organization_id=org,
        area_id=area.area_id,
        payload=AreaLifecycleRequest.model_validate(
            {
                "authorization_revision": 6,
                "expected_revision": 2,
                "idempotency_key": "area-archive-0002",
                "target": "archived",
            }
        ),
        request_id="area-test",
    )
    assert archived.state == "archived"

    # An archived area refuses new category bindings.
    with pytest.raises(ApiError, match="technology area is unavailable"):
        await write_category(
            db_session,
            ctx=ctx,
            organization_id=org,
            category_id=bound.category_id,
            payload=CategoryWriteRequest.model_validate(
                {
                    "authorization_revision": 7,
                    "expected_revision": 3,
                    "idempotency_key": "area-category-0004",
                    "metadata": {"name": "Query engine"},
                    "area_id": area.area_id,
                }
            ),
            request_id="area-test",
        )
    assert (
        await read_area(
            db_session,
            ctx=ctx,
            organization_id=org,
            area_id=area.area_id,
            request_id="area-test",
        )
    ).state == "archived"
    assert (
        await list_areas(db_session, ctx=ctx, organization_id=org, request_id="area-test")
    ).items[0].area_id == area.area_id
