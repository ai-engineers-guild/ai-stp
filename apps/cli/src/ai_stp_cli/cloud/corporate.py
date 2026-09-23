"""Typed transport for corporate catalog assignments (issues #205/#206/#214).

The effective-assignment read, bulk distribution, and install/update plan are
the same generated contracts the Web and CI use: one route, one model, one
resolution algorithm owned by the platform. The CLI never reimplements scope
precedence, `latest` selection, or plan classification locally.
"""

from ai_stp_cli.cloud.client import Endpoint, as_query, call, open_client
from ai_stp_contracts.corporate import (
    CorporateAssignmentPlan,
    CorporateAssignmentPlanRequest,
    CorporateDistributionRequest,
    CorporateDistributionResult,
    CorporateDistributionStateList,
    CorporateDistributionStateQuery,
    CorporateEffectiveAssignment,
    CorporateEffectiveAssignmentQuery,
)
from ai_stp_contracts.dashboard import CorporateCiCheckRequest, CorporateCiCheckView


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


def assignment_plan(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    request: CorporateAssignmentPlanRequest,
) -> CorporateAssignmentPlan:
    """Evaluate the deterministic install/update plan for one context (#214)."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/corporate/organizations/{organization_id}/catalog-assignments/plan",
            CorporateAssignmentPlan,
            body=request,
            attempts=endpoint.max_attempts,
        )


def report_ci_check(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    request: CorporateCiCheckRequest,
) -> CorporateCiCheckView:
    """Persist the closed verdict; local diagnostic details never cross the wire."""
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "PUT",
            f"/corporate/organizations/{organization_id}/dashboard/ci-check",
            CorporateCiCheckView,
            body=request,
            attempts=endpoint.max_attempts,
        )
