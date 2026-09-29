"""Typed authenticated reporter transport."""

from ai_stp_cli.cloud.client import Endpoint, call, open_client
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.http import PageInfo
from ai_stp_contracts.reports import (
    ReportCaseCreateRequest,
    ReportCaseListResponse,
    ReportCaseResponse,
)


def create(
    endpoint: Endpoint, access_token: str, request: ReportCaseCreateRequest
) -> ReportCaseResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            "/requests",
            ReportCaseResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )


def list_all(endpoint: Endpoint, access_token: str) -> ReportCaseListResponse:
    """Drain every page; a first-page slice would silently hide older cases."""
    items: list[ReportCaseResponse] = []
    page_info: PageInfo | None = None
    cursor: str | None = None
    with open_client(endpoint, access_token=access_token) as client:
        for _ in range(100):
            page = call(
                client,
                "GET",
                "/requests",
                ReportCaseListResponse,
                query=None if cursor is None else {"cursor": cursor},
                attempts=endpoint.max_attempts,
            )
            items.extend(page.items)
            page_info = page.page
            cursor = page.page.next_cursor
            if cursor is None:
                break
        else:
            raise CliFailure(
                "AI_STP_PROTOCOL_VIOLATION",
                "report list pagination never terminated",
            )
    assert page_info is not None  # the loop always ran at least once
    return ReportCaseListResponse(schema_version=1, items=items, page=page_info)


def read(endpoint: Endpoint, access_token: str, case_id: str) -> ReportCaseResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/requests/{case_id}",
            ReportCaseResponse,
            attempts=endpoint.max_attempts,
        )
