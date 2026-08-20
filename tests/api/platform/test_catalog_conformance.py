"""Run the shared catalog conformance cases against the seeded API (REQ-2112)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.api.platform.conftest import make_settings

from ai_stp_api.app import create_app
from ai_stp_contracts.fixtures import FixtureCase, load_cases
from ai_stp_contracts.http import API_BASE_PATH, REQUEST_ID_HEADER
from ai_stp_contracts.openapi import OPERATIONS
from ai_stp_platform.catalog_seed import load_first_party_seed

pytestmark = pytest.mark.platform

_CATALOG_OPS = frozenset(
    {
        "searchComponents",
        "readComponent",
        "readComponentVersion",
        "searchSetups",
        "readSetup",
        "readSetupVersion",
    }
)
_BY_ID = {operation.operation_id: operation for operation in OPERATIONS}


def _url(case: FixtureCase) -> str:
    operation = _BY_ID[case.operation_id]
    path = f"{API_BASE_PATH}{operation.path}"
    for name, value in case.request.path_params.items():
        path = path.replace("{" + name + "}", value)
    return path


def _query(case: FixtureCase) -> dict[str, str]:
    rendered: dict[str, str] = {}
    for name, value in case.request.query.items():
        rendered[name] = "true" if value is True else "false" if value is False else str(value)
    return rendered


async def _check_case(client: AsyncClient, case: FixtureCase) -> list[str]:
    operation = _BY_ID[case.operation_id]
    response = await client.request(
        operation.method.upper(),
        _url(case),
        params=_query(case),
        json=dict(case.request.body) if case.request.body is not None else None,
        headers=dict(case.request.headers),
    )
    findings: list[str] = []
    if response.status_code != case.status:
        findings.append(f"status {response.status_code}, contract says {case.status}")
    if REQUEST_ID_HEADER not in response.headers:
        findings.append(f"no {REQUEST_ID_HEADER} header")
    try:
        payload = cast(object, response.json())
    except json.JSONDecodeError:
        return [*findings, "body is not JSON"]
    if case.kind == "positive":
        if payload != dict(case.body or {}):
            findings.append(f"body differs from the contract example: {payload!r}")
        return findings
    code: object = None
    if isinstance(payload, dict):
        error = cast(dict[str, object], payload).get("error")
        if isinstance(error, dict):
            code = cast(dict[str, object], error).get("code")
    if code != case.error_code:
        findings.append(f"error code {code!r}, contract says {case.error_code!r}")
    return findings


@pytest_asyncio.fixture
async def seeded_async_client(
    migrated_database_url: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[AsyncClient]:
    log_dir = tmp_path_factory.mktemp("catalog-conf")
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


@pytest.mark.asyncio
async def test_catalog_conformance_cases(seeded_async_client: AsyncClient) -> None:
    cases = [
        case
        for case in load_cases()
        if case.operation_id in _CATALOG_OPS and case.kind in {"positive", "rejected_request"}
    ]
    assert cases, "expected catalog cases in the shared corpus"
    findings: list[str] = []
    for case in cases:
        for detail in await _check_case(seeded_async_client, case):
            findings.append(f"{case.case_id}: {detail}")
    assert findings == [], "\n".join(findings)
