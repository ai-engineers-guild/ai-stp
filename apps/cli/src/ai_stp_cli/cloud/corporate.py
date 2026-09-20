"""Typed transport for corporate catalog assignments (issue #205).

The effective-assignment read is the same generated contract the Web uses:
one route, one model, one resolution algorithm owned by the platform. The CLI
never reimplements scope precedence or `latest` selection locally.
"""

from ai_stp_cli.cloud.client import Endpoint, as_query, call, open_client
from ai_stp_contracts.corporate import (
    CorporateDistributionRequest,
    CorporateDistributionResult,
    CorporateDistributionStateList,
    CorporateDistributionStateQuery,
    CorporateEffectiveAssignment,
    CorporateEffectiveAssignmentQuery,
)


def effective_assignment(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    request: CorporateEffectiveAssignmentQuery,
) -> CorporateEffectiveAssignment:
    """Resolve the winning assignment for one employee and one catalog line."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/corporate/organizations/{organization_id}/catalog-assignments/effective",
            CorporateEffectiveAssignment,
            query=as_query(request),
            attempts=endpoint.max_attempts,
        )


def distribute_assignment(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    request: CorporateDistributionRequest,
) -> CorporateDistributionResult:
    """Preview or apply one bulk assign/revoke distribution (issue #206)."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/corporate/organizations/{organization_id}/catalog-assignments/distribution",
            CorporateDistributionResult,
            body=request,
            attempts=endpoint.max_attempts,
        )


def assignment_distribution(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    request: CorporateDistributionStateQuery,
) -> CorporateDistributionStateList:
    """Read the latest per-target distribution state for one source assignment."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/corporate/organizations/{organization_id}/catalog-assignments/distribution",
            CorporateDistributionStateList,
            query=as_query(request),
            attempts=endpoint.max_attempts,
        )
