"""Typed authenticated access-grant transport."""

from ai_stp_cli.cloud.client import Endpoint, call, open_client
from ai_stp_contracts.grants import (
    AccessGrantResponse,
    DirectGrantCreateRequest,
    GrantAcceptRequest,
    GrantInvitationCreateRequest,
    GrantInvitationResponse,
    GrantListResponse,
    GrantRevokeRequest,
    GrantRevokeResponse,
)


def invite(
    endpoint: Endpoint, access_token: str, request: GrantInvitationCreateRequest
) -> GrantInvitationResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            "/grants/invitations",
            GrantInvitationResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )


def direct(
    endpoint: Endpoint, access_token: str, request: DirectGrantCreateRequest
) -> AccessGrantResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            "/grants/direct",
            AccessGrantResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )


def list_all(endpoint: Endpoint, access_token: str) -> GrantListResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(client, "GET", "/grants", GrantListResponse, attempts=endpoint.max_attempts)


def accept(
    endpoint: Endpoint, access_token: str, invitation_id: str, request: GrantAcceptRequest
) -> AccessGrantResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/grants/invitations/{invitation_id}/accept",
            AccessGrantResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )


def revoke_invitation(
    endpoint: Endpoint, access_token: str, invitation_id: str, request: GrantRevokeRequest
) -> GrantRevokeResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/grants/invitations/{invitation_id}/revoke",
            GrantRevokeResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )


def revoke_grant(
    endpoint: Endpoint, access_token: str, grant_id: str, request: GrantRevokeRequest
) -> GrantRevokeResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/grants/{grant_id}/revoke",
            GrantRevokeResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )
