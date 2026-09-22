"""Typed transport for technology mappings and scan publication (issue #222).

Same contract the Web and the corporate surface consume: the platform owns
merge semantics, review preservation and absent marking; the CLI owns local
detection and never reimplements that precedence here.
"""

from ai_stp_cli.cloud.client import Endpoint, call, open_client
from ai_stp_contracts.technology import (
    TechnologyMappingView,
    TechnologyScanRequest,
    TechnologyScanResult,
)


def read_mapping(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    version: str,
) -> TechnologyMappingView:
    """Fetch one immutable organization mapping snapshot by exact version."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/corporate/organizations/{organization_id}/technology-mappings/{version}",
            TechnologyMappingView,
            attempts=endpoint.max_attempts,
        )


def publish_scan(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    project_id: str,
    request: TechnologyScanRequest,
) -> TechnologyScanResult:
    """Submit one local scan handoff for server-side merge."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/corporate/organizations/{organization_id}/projects/{project_id}/technology-scans",
            TechnologyScanResult,
            body=request,
            attempts=endpoint.max_attempts,
        )
