"""Typed authenticated transport for the private revision ledger."""

from ai_stp_cli.cloud.client import Endpoint, as_query, call, open_client
from ai_stp_contracts.sync import (
    SyncPullQuery,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
)


def push(endpoint: Endpoint, access_token: str, request: SyncPushRequest) -> SyncPushResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            "/sync/push",
            SyncPushResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )


def pull(endpoint: Endpoint, access_token: str, request: SyncPullQuery) -> SyncPullResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            "/sync/pull",
            SyncPullResponse,
            query=as_query(request),
            attempts=endpoint.max_attempts,
        )
