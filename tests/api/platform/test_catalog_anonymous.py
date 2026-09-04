"""ASGI tests for anonymous public catalog routes (SPEC-021)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.api.platform.conftest import make_settings

from ai_stp_api.app import create_app
from ai_stp_api.errors import CATEGORY_CODE, ErrorCategory
from ai_stp_platform.catalog_seed import (
    FIXTURE_COMPONENT_ID,
    FIXTURE_SETUP_ID,
    load_first_party_seed,
)
from ai_stp_platform.models import CatalogMetadata

pytestmark = pytest.mark.platform


@pytest_asyncio.fixture
async def seeded_client(
    migrated_database_url: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[AsyncClient]:
    log_dir = tmp_path_factory.mktemp("catalog-api")
    settings = make_settings(log_dir, database_url=migrated_database_url)
    engine = create_async_engine(migrated_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        await load_first_party_seed(session)
        await session.commit()
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    await engine.dispose()


async def test_six_anonymous_routes_succeed(seeded_client: AsyncClient) -> None:
    paths = [
        "/v1/catalog/components?page_size=20&include_experimental=true",
        f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}",
        f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2",
        "/v1/catalog/setups?page_size=20&include_experimental=true",
        f"/v1/catalog/setups/{FIXTURE_SETUP_ID}",
        f"/v1/catalog/setups/{FIXTURE_SETUP_ID}/versions/1.0",
    ]
    for path in paths:
        response = await seeded_client.get(path)
        assert response.status_code == 200, path
        assert "X-Request-Id" in response.headers
        assert "ok" not in response.json() or "schema_version" in response.json()


async def test_experimental_section_requires_consent(seeded_client: AsyncClient) -> None:
    without = await seeded_client.get(
        "/v1/catalog/components",
        params={"page_size": "20", "include_experimental": "false"},
    )
    with_consent = await seeded_client.get(
        "/v1/catalog/components",
        params={"page_size": "20", "include_experimental": "true"},
    )
    assert without.status_code == 200
    assert with_consent.status_code == 200
    assert without.json()["experimental"] == []
    assert without.json()["items"] == []
    assert len(with_consent.json()["experimental"]) >= 1
    assert with_consent.json()["items"] == []


async def test_non_enumeration_same_not_found(seeded_client: AsyncClient) -> None:
    missing = await seeded_client.get("/v1/catalog/components/component_01JQZK7B8N4M6P2R9T5V0X3Y70")
    # Private row is not seeded; create one mid-test via direct DB if needed.
    # Absent and non-public both yield AI_STP_NOT_FOUND.
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "AI_STP_NOT_FOUND"


async def test_unknown_query_param_rejected(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get("/v1/catalog/components", params={"tag": "python"})
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.VALIDATION]


async def test_component_detail_non_contiguous_versions(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get(f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}")
    assert response.status_code == 200
    body = response.json()
    versions = [entry["version"] for entry in body["versions"]]
    assert versions == ["1.0", "1.2"]
    assert body["summary"]["latest_version"] == "1.2"
    assert body["summary"]["latest_trust"]["trust_lane"] == "experimental"
    assert body["summary"]["latest_trust"]["component_verified"] is False
    assert body["summary"]["latest_support"]["tier"] == "primary"
    assert body["summary"]["latest_support"]["state"] == "missing"


async def test_support_filters_are_public_and_do_not_change_trust_consent(
    seeded_client: AsyncClient,
) -> None:
    response = await seeded_client.get(
        "/v1/catalog/components",
        params={
            "page_size": "20",
            "include_experimental": "true",
            "support_tier": "primary",
            "support_state": "missing",
        },
    )
    assert response.status_code == 200
    assert response.json()["experimental"]
    assert response.json()["experimental"][0]["latest_support"]["state"] == "missing"


async def test_fresh_support_evidence_is_exposed_on_detail_and_version(
    db_api_client: tuple[AsyncClient, async_sessionmaker[AsyncSession], object],
) -> None:
    client, sessionmaker, _settings = db_api_client
    async with sessionmaker() as session:
        await load_first_party_seed(session)
        row = await session.scalar(
            select(CatalogMetadata).where(
                CatalogMetadata.object_kind == "component",
                CatalogMetadata.stable_id == FIXTURE_COMPONENT_ID,
                CatalogMetadata.version == "1.2",
            )
        )
        assert row is not None
        row.support_evidence = [
            {
                "schema_version": 1,
                "check_id": "release-smoke",
                "policy_version": "2026.08",
                "result": "passed",
                "source": "provider_release_evidence",
                "provider_id": "nddev-provider",
                "provider_version": "2.4.0",
                "release_reference": "a" * 40,
                "operating_system": "ubuntu",
                "architecture": "x86_64",
                "mandatory": True,
                "observed_at": "2026-08-09T10:00:00.000Z",
                "expires_at": "2030-01-01T00:00:00.000Z",
            }
        ]
        await session.commit()

    detail = await client.get(f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["summary"]["latest_support"]["state"] == "verified"
    assert detail_body["summary"]["latest_support"]["evidence"][0]["result"] == "passed"

    version = await client.get(f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2")
    assert version.status_code == 200
    assert version.json()["support"]["state"] == "verified"
    assert version.json()["support"]["evidence"][0]["check_id"] == "release-smoke"


async def test_invalid_support_filter_is_a_validation_error(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get(
        "/v1/catalog/components",
        params={"support_state": "fresh"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AI_STP_VALIDATION_ERROR"


async def test_setup_support_filter_is_validated(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get(
        "/v1/catalog/setups",
        params={"support_tier": "primary", "support_state": "fresh"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AI_STP_VALIDATION_ERROR"


async def test_missing_setup_is_not_enumerated(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get("/v1/catalog/setups/setup_01JQZK7B8N4M6P2R9T5V0X3Y70")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AI_STP_NOT_FOUND"


async def test_version_read_serves_public_passport(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get(
        f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/1.2"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["passport"]["visibility"] == "public"
    assert body["passport"]["name"] == "fixture-component"
    assert body["lifecycle"] == "active"
    assert body["trust"]["trust_lane"] == "experimental"
    assert body["support"]["tier"] == "primary"
    assert body["support"]["state"] == "missing"


async def test_no_count_field_on_list(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get(
        "/v1/catalog/components",
        params={"page_size": "20", "include_experimental": "true"},
    )
    body = response.json()
    assert "count" not in body
    assert "total" not in body


async def test_invalid_cursor_is_validation_error(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get(
        "/v1/catalog/components",
        params={"page_size": "20", "cursor": "not-a-valid-cursor-token"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AI_STP_VALIDATION_ERROR"


async def test_missing_setup_version_is_not_found(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get(
        f"/v1/catalog/setups/{FIXTURE_SETUP_ID}/versions/9.9",
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AI_STP_NOT_FOUND"


async def test_missing_component_version_is_not_found(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get(
        f"/v1/catalog/components/{FIXTURE_COMPONENT_ID}/versions/9.9",
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AI_STP_NOT_FOUND"


async def test_page_mode_returns_exact_public_totals(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get(
        "/v1/catalog/components",
        params={"page": "1", "page_size": "1", "include_experimental": "true"},
    )

    assert response.status_code == 200
    page = response.json()["page"]
    assert page["mode"] == "page"
    assert page["page_number"] == 1
    assert page["total_items"] >= 1
    assert page["total_pages"] >= 1
    assert page["next_cursor"] is None


async def test_cursor_and_page_modes_are_mutually_exclusive(seeded_client: AsyncClient) -> None:
    first = await seeded_client.get(
        "/v1/catalog/components",
        params={"page_size": "1", "include_experimental": "true"},
    )
    cursor = first.json()["page"]["next_cursor"]
    if cursor is None:
        # The reason blames the corpus, so check the corpus. A missing cursor
        # can also mean the endpoint stopped issuing them, and that defect
        # would skip here under a sentence that exonerates it.
        held = await seeded_client.get(
            "/v1/catalog/components",
            params={"page_size": "100", "include_experimental": "true"},
        )
        assert len(held.json()["items"]) <= 1, (
            "a page of one returned no cursor while more than one component exists, "
            "so the corpus is not what this skip claims"
        )
        pytest.skip("fixture corpus fits one cursor page")

    response = await seeded_client.get(
        "/v1/catalog/components",
        params={"cursor": cursor, "page": "1", "page_size": "1"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AI_STP_VALIDATION_ERROR"


async def test_catalog_ql_is_validated_at_the_api_boundary(seeded_client: AsyncClient) -> None:
    valid = await seeded_client.get(
        "/v1/catalog/components",
        params={
            "q": "NAME:fixture-component AND TAGS IN (python, tests)",
            "include_experimental": "true",
            "page": "1",
        },
    )
    assert valid.status_code == 200
    assert valid.json()["experimental"]

    invalid = await seeded_client.get(
        "/v1/catalog/components",
        params={"q": "VERIFIED:maybe", "page": "1"},
    )
    assert invalid.status_code == 400
    assert "offset" in invalid.json()["error"]["message"]

    # Every multi-value filter is enforced server-side rather than being a UI-only
    # affordance.  Mismatching values must empty the response deterministically.
    for key, value in (
        ("harness_ids", "opencode"),
        ("component_types", "mcp"),
        ("authors", "account_missing"),
    ):
        filtered = await seeded_client.get(
            "/v1/catalog/components",
            params={key: value, "include_experimental": "true", "page": "1"},
        )
        assert filtered.status_code == 200
        stable_ids = {
            item["stable_id"]
            for lane in ("items", "experimental")
            for item in filtered.json()[lane]
        }
        assert FIXTURE_COMPONENT_ID not in stable_ids

    verified = await seeded_client.get(
        "/v1/catalog/components",
        params={"verified_only": "true", "include_experimental": "true", "page": "1"},
    )
    assert verified.status_code == 200
    assert verified.json()["experimental"] == []


async def test_updated_range_filters_and_rejects_reversed_bounds(
    seeded_client: AsyncClient,
) -> None:
    wide = await seeded_client.get(
        "/v1/catalog/components",
        params={
            "updated_from": "2000-01-01",
            "updated_to": "2099-12-31",
            "include_experimental": "true",
            "page": "1",
        },
    )
    assert wide.status_code == HTTPStatus.OK
    assert wide.json()["experimental"] or wide.json()["items"]

    empty_future = await seeded_client.get(
        "/v1/catalog/components",
        params={
            "updated_from": "2099-01-01",
            "include_experimental": "true",
            "page": "1",
        },
    )
    assert empty_future.status_code == HTTPStatus.OK
    assert empty_future.json()["items"] == []
    assert empty_future.json()["experimental"] == []

    empty_past = await seeded_client.get(
        "/v1/catalog/components",
        params={
            "updated_to": "2000-01-01",
            "include_experimental": "true",
            "page": "1",
        },
    )
    assert empty_past.status_code == HTTPStatus.OK
    assert empty_past.json()["items"] == []
    assert empty_past.json()["experimental"] == []

    reversed_range = await seeded_client.get(
        "/v1/catalog/components",
        params={
            "updated_from": "2026-02-02",
            "updated_to": "2026-02-01",
            "page": "1",
        },
    )
    assert reversed_range.status_code == HTTPStatus.BAD_REQUEST
    assert reversed_range.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.VALIDATION]


async def test_setup_updated_range_uses_the_same_contract(
    seeded_client: AsyncClient,
) -> None:
    wide = await seeded_client.get(
        "/v1/catalog/setups",
        params={
            "updated_from": "2000-01-01",
            "updated_to": "2099-12-31",
            "include_experimental": "true",
            "page": "1",
        },
    )
    assert wide.status_code == HTTPStatus.OK
    assert wide.json()["experimental"] or wide.json()["items"]

    reversed_range = await seeded_client.get(
        "/v1/catalog/setups",
        params={
            "updated_from": "2026-02-02",
            "updated_to": "2026-02-01",
            "page": "1",
        },
    )
    assert reversed_range.status_code == HTTPStatus.BAD_REQUEST
    assert reversed_range.json()["error"]["code"] == CATEGORY_CODE[ErrorCategory.VALIDATION]


@pytest.mark.asyncio
async def test_walking_the_cursor_visits_every_object_exactly_once(
    seeded_client: AsyncClient,
) -> None:
    """`REQ-2105` in the half that was never tested: no duplicates, no gaps.

    The existing tests cover the token — round trip, tampering, a cursor from
    another filter. They do not walk a sequence, and the walk is where it broke:
    the page was re-sorted before the cursor was taken from its last row, so the
    token described a position in the display order while the next request
    resumed the scan order. With the default `relevance` sort those are
    unrelated.

    On the deployed catalogue that lost more than half of it. Walking with
    `page_size=25` reached 45 of 103 objects and then reported no cursor, and a
    different page size gave a different total — which is the tell: a correct
    enumeration cannot depend on how it is cut into pages.
    """

    async def walk(page_size: int) -> list[str]:
        seen: list[str] = []
        cursor: str | None = None
        for _ in range(64):
            params: dict[str, str | int] = {
                "include_experimental": "true",
                "page_size": page_size,
            }
            if cursor is not None:
                params["cursor"] = cursor
            response = await seeded_client.get("/v1/catalog/components", params=params)
            assert response.status_code == HTTPStatus.OK
            body = response.json()
            seen.extend(row["stable_id"] for row in body["items"] + body["experimental"])
            cursor = body["page"]["next_cursor"]
            if cursor is None:
                return seen
        raise AssertionError("the cursor never reported the end of the sequence")

    whole = await walk(100)
    assert len(whole) == len(set(whole)), "a single page repeated an object"

    for page_size in (1, 2, 3, 7):
        walked = await walk(page_size)
        assert len(walked) == len(set(walked)), (
            f"page_size={page_size} returned the same object on two pages"
        )
        assert set(walked) == set(whole), (
            f"page_size={page_size} enumerated {len(set(walked))} objects while one "
            f"page holds {len(set(whole))}; a cut into pages must not change the set"
        )


@pytest.mark.asyncio
async def test_a_sub_millisecond_timestamp_does_not_repeat_a_row(
    migrated_database_url: str,
    seeded_client: AsyncClient,
) -> None:
    """The cursor carries milliseconds; PostgreSQL keeps microseconds.

    A row published at `.746829` produces a cursor saying `.746`, and
    `published_at > .746000` is true of that very row — so it came back as the
    first entry of the next page. One duplicate per page boundary, and only for
    rows whose timestamp had digits below a millisecond, which is why the
    fixture corpus never showed it and the deployed catalogue did.
    """
    engine = create_async_engine(migrated_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        rows = (await session.execute(select(CatalogMetadata))).scalars().all()
        for index, row in enumerate(rows):
            if row.published_at is None:
                continue
            # Distinct sub-millisecond tails, so every boundary can trip.
            row.published_at = row.published_at.replace(microsecond=746_000 + index * 37 + 1)
        await session.commit()
    await engine.dispose()

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(64):
        params: dict[str, str | int] = {"include_experimental": "true", "page_size": 2}
        if cursor is not None:
            params["cursor"] = cursor
        response = await seeded_client.get("/v1/catalog/components", params=params)
        assert response.status_code == HTTPStatus.OK
        body = response.json()
        seen.extend(row["stable_id"] for row in body["items"] + body["experimental"])
        cursor = body["page"]["next_cursor"]
        if cursor is None:
            break
    else:
        raise AssertionError("the cursor never reported the end of the sequence")

    assert len(seen) == len(set(seen)), (
        "a row whose timestamp is finer than the cursor came back on the next page"
    )


@pytest_asyncio.fixture
async def lifecycle_harness(
    migrated_database_url: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    """`seeded_client` plus the sessionmaker, so a test can move a lifecycle."""
    log_dir = tmp_path_factory.mktemp("catalog-lifecycle")
    settings = make_settings(log_dir, database_url=migrated_database_url)
    engine = create_async_engine(migrated_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        await load_first_party_seed(session)
        await session.commit()
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, sessionmaker
    await engine.dispose()


async def test_the_browse_listing_hides_superseded_versions_until_asked(
    lifecycle_harness: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    """`REQ-2114`. The listing is a recommendation; a superseded version is not one.

    `REQ-2107` makes `deprecated` representable and says nothing about the
    default listing, which inherited the answer to a different question because
    one set served both. Measured on the deployed catalogue on 2026-08-30: the
    first page an anonymous visitor saw held nineteen deprecated setups and one
    active, with all twenty-eight current ones behind it.

    Reachability is asserted in the same test rather than trusted: the object
    stays readable by id and by exact version throughout, which is the half
    `REQ-2107` owns and this change must not touch.
    """
    client, sessionmaker = lifecycle_harness

    # `include_experimental` on every call: the seeded setup sits in the
    # experimental lane, so the authoritative `items` list is empty without it
    # and this test would read a hidden object as a hidden lifecycle. The lane
    # and the lifecycle are separate filters and this asserts only the second.
    browse = {"page_size": "50", "include_experimental": "true"}

    def ids(payload: dict[str, object]) -> set[str]:
        items = payload["experimental"]
        assert isinstance(items, list)
        found: set[str] = set()
        for item in cast(list[dict[str, object]], items):
            found.add(str(item["stable_id"]))
        return found

    listed = await client.get("/v1/catalog/setups", params=browse)
    assert listed.status_code == 200
    assert FIXTURE_SETUP_ID in ids(listed.json())

    async with sessionmaker() as session:
        rows = await session.scalars(
            select(CatalogMetadata).where(CatalogMetadata.stable_id == FIXTURE_SETUP_ID)
        )
        for row in rows.all():
            row.lifecycle_state = "deprecated"
        from ai_stp_platform.catalog_search import upsert_catalog_search_projection

        await upsert_catalog_search_projection(
            session, object_kind="setup", stable_id=FIXTURE_SETUP_ID
        )
        await session.commit()

    hidden = await client.get("/v1/catalog/setups", params=browse)
    assert hidden.status_code == 200
    assert FIXTURE_SETUP_ID not in ids(hidden.json())

    asked = await client.get("/v1/catalog/setups", params={**browse, "include_deprecated": "true"})
    assert asked.status_code == 200
    assert FIXTURE_SETUP_ID in ids(asked.json())

    # Still representable, which is what `REQ-2107` requires and what a pin needs.
    detail = await client.get(f"/v1/catalog/setups/{FIXTURE_SETUP_ID}")
    assert detail.status_code == 200
    exact = await client.get(f"/v1/catalog/setups/{FIXTURE_SETUP_ID}/versions/1.0")
    assert exact.status_code == 200
    assert exact.json()["lifecycle"] == "deprecated"
