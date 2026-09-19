"""Typed transport for corporate catalog assignments (issue #205).

The effective-assignment read is the same generated contract the Web uses:
one route, one model, one resolution algorithm owned by the platform. The CLI
never reimplements scope precedence or `latest` selection locally.
"""

from ai_stp_cli.cloud.client import Endpoint, as_query, call, open_client
from ai_stp_contracts.corporate import (
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
