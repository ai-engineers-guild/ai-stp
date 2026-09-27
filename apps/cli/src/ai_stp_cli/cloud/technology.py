"""Typed transport for technology mappings and scan publication (issue #222).

Same contract the Web and the corporate surface consume: the platform owns
merge semantics, review preservation and absent marking; the CLI owns local
detection and never reimplements that precedence here.
"""

from ai_stp_cli.cloud.client import Endpoint, call, open_client
from ai_stp_contracts.technology import (
    CategoryList,
    CategoryView,
    CategoryWriteRequest,
    TechnologyLifecycleRequest,
    TechnologyList,
    TechnologyMappingList,
    TechnologyMappingRequest,
    TechnologyMappingView,
    TechnologyScanRequest,
    TechnologyScanResult,
    TechnologyUnmappedEntry,
    TechnologyUnmappedReviewRequest,
    TechnologyUnmappedView,
    TechnologyView,
    TechnologyWriteRequest,
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


def publish_mapping(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    version: str,
    request: TechnologyMappingRequest,
) -> TechnologyMappingView:
    """Write one immutable coordinate→identity snapshot for the organization."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "PUT",
            f"/corporate/organizations/{organization_id}/technology-mappings/{version}",
            TechnologyMappingView,
            body=request,
            attempts=endpoint.max_attempts,
        )


def read_unmapped(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
) -> TechnologyUnmappedView:
    """Read the organization's queue of coordinates no mapping resolved."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/corporate/organizations/{organization_id}/technology-unmapped-coordinates",
            TechnologyUnmappedView,
            attempts=endpoint.max_attempts,
        )


def review_unmapped(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    request: TechnologyUnmappedReviewRequest,
) -> TechnologyUnmappedEntry:
    """Propose or clear the candidate technology for one queued coordinate."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "PATCH",
            f"/corporate/organizations/{organization_id}/technology-unmapped-coordinates",
            TechnologyUnmappedEntry,
            body=request,
            attempts=endpoint.max_attempts,
        )


def list_mappings(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
) -> TechnologyMappingList:
    """List every immutable mapping snapshot the organization published."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/corporate/organizations/{organization_id}/technology-mappings",
            TechnologyMappingList,
            attempts=endpoint.max_attempts,
        )


def list_technologies(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
) -> TechnologyList:
    """Read the organization's technology registry — the widest page."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/corporate/organizations/{organization_id}/technologies",
            TechnologyList,
            query={"limit": "256"},
            attempts=endpoint.max_attempts,
        )


def list_categories(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
) -> CategoryList:
    """Read the organization's technology categories."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/corporate/organizations/{organization_id}/technology-categories",
            CategoryList,
            attempts=endpoint.max_attempts,
        )


def write_technology(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    request: TechnologyWriteRequest,
    technology_id: str | None = None,
) -> TechnologyView:
    """Create or update one technology record."""
    with open_client(endpoint, access_token=access_token) as client:
        suffix = f"/{technology_id}" if technology_id is not None else ""
        return call(
            client,
            "POST" if technology_id is None else "PUT",
            f"/corporate/organizations/{organization_id}/technologies{suffix}",
            TechnologyView,
            body=request,
            attempts=endpoint.max_attempts,
        )


def change_technology_lifecycle(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    technology_id: str,
    request: TechnologyLifecycleRequest,
) -> TechnologyView:
    """Move one technology between draft, active, deprecated and archived."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "PATCH",
            f"/corporate/organizations/{organization_id}/technologies/{technology_id}/lifecycle",
            TechnologyView,
            body=request,
            attempts=endpoint.max_attempts,
        )


def write_category(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    request: CategoryWriteRequest,
) -> CategoryView:
    """Create one technology category."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/corporate/organizations/{organization_id}/technology-categories",
            CategoryView,
            body=request,
            attempts=endpoint.max_attempts,
        )
