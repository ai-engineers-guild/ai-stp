"""Report journeys: the real `/v1/requests` surface.

Replaces the `/v1`-mock transport journey in `tests/unit/test_cli_reports.py`.
Any authenticated account may file a request — the case records the object
coordinates rather than requiring a catalog row — so a fresh account exercises
create, list, read, and the server's own idempotent replay. What stays in the
unit file is local-only behavior: preview durability in SQLite, the digest
gate, diagnostics fail-closed scanning, and the registry declaration.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from tests.api.cli.conftest import WebApprover

from ai_stp_cli.cloud import reports as transport
from ai_stp_cli.cloud.client import Endpoint
from ai_stp_contracts.reports import ReportCaseCreateRequest

DIGEST = "sha256:" + "b" * 64


def _request() -> ReportCaseCreateRequest:
    return ReportCaseCreateRequest(
        object_kind="component",
        stable_id="component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
        version="1.0",
        content_digest=DIGEST,
        validation_snapshot_ids=[],
        idempotency_key="report-intent-012345",
    )


def test_create_list_and_read_the_real_case(
    cli_endpoint: Endpoint, web_approver: Callable[[], WebApprover]
) -> None:
    reporter = web_approver()

    created = transport.create(cli_endpoint, reporter.token, _request())
    assert created.state == "submitted"
    assert created.case_id

    listed = transport.list_all(cli_endpoint, reporter.token)
    assert any(item.case_id == created.case_id for item in listed.items)

    read = transport.read(cli_endpoint, reporter.token, created.case_id)
    assert read.case_id == created.case_id
    assert read.stable_id == "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z"


def test_replaying_the_intent_returns_the_same_case(
    cli_endpoint: Endpoint, web_approver: Callable[[], WebApprover]
) -> None:
    """Server-side idempotency: the retry must not open a second case."""
    reporter = web_approver()

    first = transport.create(cli_endpoint, reporter.token, _request())
    replayed = transport.create(cli_endpoint, reporter.token, _request())

    assert replayed.case_id == first.case_id
    listed = transport.list_all(cli_endpoint, reporter.token)
    assert sum(item.case_id == first.case_id for item in listed.items) == 1


def test_another_account_cannot_read_the_case(
    cli_endpoint: Endpoint, web_approver: Callable[[], WebApprover]
) -> None:
    reporter = web_approver()
    outsider = web_approver()

    created = transport.create(cli_endpoint, reporter.token, _request())

    listed = transport.list_all(cli_endpoint, outsider.token)
    assert all(item.case_id != created.case_id for item in listed.items)

    from ai_stp_cli.errors import CliFailure

    with pytest.raises(CliFailure) as raised:
        transport.read(cli_endpoint, outsider.token, created.case_id)
    assert raised.value.code == "AI_STP_NOT_FOUND"
