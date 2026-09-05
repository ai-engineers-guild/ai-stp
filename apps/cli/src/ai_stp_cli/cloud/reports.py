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
            "/requests",
            ReportCaseResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )


def list_all(endpoint: Endpoint, access_token: str) -> ReportCaseListResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client, "GET", "/requests", ReportCaseListResponse, attempts=endpoint.max_attempts
        )


def read(endpoint: Endpoint, access_token: str, case_id: str) -> ReportCaseResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/requests/{case_id}",
            ReportCaseResponse,
            attempts=endpoint.max_attempts,
        )
