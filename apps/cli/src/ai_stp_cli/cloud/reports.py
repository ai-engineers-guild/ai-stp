"""Typed authenticated reporter transport."""

from ai_stp_cli.cloud.client import Endpoint, call, open_client
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
            "/reports",
            ReportCaseResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )


def list_all(endpoint: Endpoint, access_token: str) -> ReportCaseListResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client, "GET", "/reports", ReportCaseListResponse, attempts=endpoint.max_attempts
        )
