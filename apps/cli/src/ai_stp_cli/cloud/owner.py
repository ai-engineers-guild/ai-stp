"""Typed authenticated owner-workspace read transport."""

from ai_stp_cli.cloud.client import Endpoint, as_query, call, open_client
from ai_stp_contracts.owner import (
    OwnerObjectDetail,
    OwnerObjectListQuery,
    OwnerObjectListResponse,
    OwnerVersionDetail,
)


def list_objects(
    endpoint: Endpoint, access_token: str, query: OwnerObjectListQuery
) -> OwnerObjectListResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            "/owner/objects",
            OwnerObjectListResponse,
            query=as_query(query),
            attempts=endpoint.max_attempts,
        )


def object_detail(
    endpoint: Endpoint, access_token: str, object_kind: str, stable_id: str
) -> OwnerObjectDetail:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/owner/objects/{object_kind}/{stable_id}",
            OwnerObjectDetail,
            attempts=endpoint.max_attempts,
        )


def version_detail(
    endpoint: Endpoint,
    access_token: str,
    object_kind: str,
    stable_id: str,
    version: str,
) -> OwnerVersionDetail:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/owner/objects/{object_kind}/{stable_id}/versions/{version}",
            OwnerVersionDetail,
            attempts=endpoint.max_attempts,
        )
