"""Finding interpretation survives rescans without rewriting original evidence."""

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_stp_api.session import AuthContext
from ai_stp_api.slices.corporate.service import bootstrap, create_project
from ai_stp_api.slices.technology.detection import (
    list_mappings,
    publish_scan,
    read_scan_detail,
    review_findings,
)
from ai_stp_api.slices.technology.service import import_seed
from ai_stp_contracts.corporate import CorporateBootstrapRequest, CorporateProjectCreateRequest
from ai_stp_contracts.technology import (
    TechnologyFindingReviewRequest,
    TechnologyScanRequest,
    TechnologySeedRequest,
)
from ai_stp_contracts.technology_seed import (
    SEED_CATEGORIES,
    SEED_COORDINATES_VERSION,
    SEED_TECHNOLOGIES,
)
from ai_stp_foundation.ids import new_id
from ai_stp_platform.models import Account
from ai_stp_platform.technology_models import (
    TechnologyClassification,
    TechnologyScan,
    TechnologyUsageFact,
)


async def test_review_updates_usage_preserves_history_and_survives_rescan(
    db_session: AsyncSession,
) -> None:
    account = new_id("account")
    db_session.add(Account(id=account, status="active"))
    await db_session.flush()
    ctx = AuthContext(account, "finding-review-test", None, "active", False, False)
    org = (
        await bootstrap(
            db_session,
            payload=CorporateBootstrapRequest(
                organization_name="Finding review acceptance",
                superadmin_account_id=account,
                idempotency_key="finding-review-bootstrap",
            ),
            request_id="finding-review-test",
        )
    ).organization_id
    await import_seed(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=TechnologySeedRequest(
            authorization_revision=1,
            idempotency_key="finding-review-seed",
        ),
        request_id="finding-review-test",
    )
    project = await create_project(
        db_session,
        ctx=ctx,
        organization_id=org,
        payload=CorporateProjectCreateRequest(
            name="Repository", authorization_revision=2, idempotency_key="finding-review-project"
        ),
        request_id="finding-review-test",
    )
    technology = SEED_TECHNOLOGIES[0][0]
    categories = set(
        await db_session.scalars(
            select(TechnologyClassification.category_id).where(
                TechnologyClassification.organization_id == org,
                TechnologyClassification.technology_id == technology,
            )
        )
    )
    category = next(row[0] for row in SEED_CATEGORIES if row[0] not in categories)
    db_session.add(
        TechnologyClassification(
            organization_id=org, technology_id=technology, category_id=category
        )
    )
    categories.add(category)
    await db_session.flush()
    scan_id = new_id("scan")

    def request(
        scan: str, mapping: str, version: str, revision: int, authorization: int, mapped: bool
    ) -> TechnologyScanRequest:
        evidence = [
            {
                "source": "declared",
                "path": "package.json",
                "reference": "dependencies.strange-package",
                "observed_at": "2026-10-08T00:00:00.000Z",
                "detector_version": "acceptance-v1",
                "mapping_version": mapping,
            }
        ]
        coordinate = {
            "kind": "package",
            "coordinate": "strange-package",
            "context": "production",
            "version": version,
            "version_kind": "declared_range",
            "evidence": evidence,
            "technology_id": technology if mapped else None,
        }
        return TechnologyScanRequest.model_validate(
            {
                "source": "local",
                "expected_revision": revision,
                "authorization_revision": authorization,
                "idempotency_key": f"publish-{scan}",
                "handoff": {
                    "organization_id": org,
                    "project_id": project.project_id,
                    "scan_id": scan,
                    "scope": "dependencies",
                    "complete": True,
                    "detector_version": "acceptance-v1",
                    "mapping_version": mapping,
                    "coordinates": [coordinate],
                    "observations": [
                        {
                            "technology_id": technology,
                            "fact": {
                                "context": "production",
                                "version": version,
                                "version_kind": "declared_range",
                                "evidence": evidence,
                            },
                        }
                    ]
                    if mapped
                    else [],
                    "unmapped_coordinates": []
                    if mapped
                    else [
                        {key: value for key, value in coordinate.items() if key != "technology_id"}
                    ],
                },
            }
        )

    await publish_scan(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project.project_id,
        payload=request(scan_id, SEED_COORDINATES_VERSION, "^1.0", 1, 3, False),
        request_id="test",
    )
    saved_scan = await db_session.get(TechnologyScan, (org, scan_id))
    assert saved_scan is not None
    original = deepcopy(saved_scan.handoff)
    decision = {
        "scan_id": scan_id,
        "kind": "package",
        "coordinate": "strange-package",
        "context": "production",
        "technology_id": technology,
        "category_id": category,
        "review": "confirmed",
        "expected_revision": 0,
        "comment": "Confirmed from repository evidence",
    }
    review = TechnologyFindingReviewRequest.model_validate(
        {
            "authorization_revision": 4,
            "idempotency_key": "finding-review-confirm",
            "items": [decision],
        }
    )
    result = await review_findings(
        db_session, ctx=ctx, organization_id=org, payload=review, request_id="test"
    )
    assert result.updated == 1
    assert (
        set(
            await db_session.scalars(
                select(TechnologyClassification.category_id).where(
                    TechnologyClassification.organization_id == org,
                    TechnologyClassification.technology_id == technology,
                )
            )
        )
        == categories
    )
    assert (
        await review_findings(
            db_session, ctx=ctx, organization_id=org, payload=review, request_id="replay"
        )
        == result
    )
    detail = await read_scan_detail(
        db_session, ctx=ctx, organization_id=org, scan_id=scan_id, request_id="test"
    )
    assert detail.findings[0].coordinate == "strange-package"
    assert detail.findings[0].state == "resolved"
    assert detail.findings[0].review_revision == 1
    assert detail.pending == 0
    fact = await db_session.scalar(
        select(TechnologyUsageFact).where(TechnologyUsageFact.organization_id == org)
    )
    assert fact is not None
    assert (fact.review, fact.version, fact.version_kind) == ("confirmed", "^1.0", "declared_range")
    mappings = await list_mappings(db_session, ctx=ctx, organization_id=org, request_id="test")
    assert mappings.items[-1].version.startswith("review-")
    next_scan = new_id("scan")
    await publish_scan(
        db_session,
        ctx=ctx,
        organization_id=org,
        project_id=project.project_id,
        payload=request(next_scan, mappings.items[-1].version, "^2.0", 3, 5, True),
        request_id="test",
    )
    assert (fact.review, fact.version) == ("confirmed", "^2.0")
    assert saved_scan.handoff == original
    rejection = TechnologyFindingReviewRequest.model_validate(
        {
            "authorization_revision": 6,
            "idempotency_key": "finding-review-reject",
            "items": [
                {
                    **decision,
                    "scan_id": next_scan,
                    "review": "rejected",
                    "comment": "Excluded from the application stack",
                }
            ],
        }
    )
    await review_findings(
        db_session, ctx=ctx, organization_id=org, payload=rejection, request_id="test"
    )
    assert fact.review == "rejected"
    detail = await read_scan_detail(
        db_session, ctx=ctx, organization_id=org, scan_id=next_scan, request_id="test"
    )
    assert detail.findings[0].state == "rejected"
    assert saved_scan.handoff == original
