"""Typed transport for product context and explicit project links."""

from ai_stp_cli.cloud.client import Endpoint, call, open_client
from ai_stp_contracts.context import (
    ProjectLinkPlanRequest,
    ProjectLinkPlanResponse,
    ProjectLinkRequest,
    ProjectLinkResponse,
    ProjectSyncApplyRequest,
    ProjectSyncPlanRequest,
    ProjectSyncPlanResponse,
    ProjectUnlinkPlanRequest,
    ProjectUnlinkPlanResponse,
    ProjectUnlinkRequest,
)


def link_plan(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    request: ProjectLinkPlanRequest,
) -> ProjectLinkPlanResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/organizations/{organization_id}/project-link-plans",
            ProjectLinkPlanResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )


def link_plan_show(
    endpoint: Endpoint, access_token: str, organization_id: str, plan_id: str
) -> ProjectLinkPlanResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/organizations/{organization_id}/project-link-plans/{plan_id}",
            ProjectLinkPlanResponse,
            attempts=endpoint.max_attempts,
        )


def link(
    endpoint: Endpoint, access_token: str, organization_id: str, request: ProjectLinkRequest
) -> ProjectLinkResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            "/projects/links",
            ProjectLinkResponse,
            body=request,
            headers={"X-AI-STP-Organization-Id": organization_id},
            attempts=endpoint.max_attempts,
        )


def show(
    endpoint: Endpoint, access_token: str, organization_id: str, link_id: str
) -> ProjectLinkResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/projects/links/{link_id}",
            ProjectLinkResponse,
            headers={"X-AI-STP-Organization-Id": organization_id},
            attempts=endpoint.max_attempts,
        )


def unlink(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    link_id: str,
    request: ProjectUnlinkRequest,
) -> ProjectLinkResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "DELETE",
            f"/projects/links/{link_id}",
            ProjectLinkResponse,
            body=request,
            headers={"X-AI-STP-Organization-Id": organization_id},
            attempts=endpoint.max_attempts,
        )


def unlink_plan(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    request: ProjectUnlinkPlanRequest,
) -> ProjectUnlinkPlanResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/organizations/{organization_id}/project-unlink-plans",
            ProjectUnlinkPlanResponse,
            body=request,
            attempts=endpoint.max_attempts,
        )


def unlink_plan_show(
    endpoint: Endpoint, access_token: str, organization_id: str, plan_id: str
) -> ProjectUnlinkPlanResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "GET",
            f"/organizations/{organization_id}/project-unlink-plans/{plan_id}",
            ProjectUnlinkPlanResponse,
            attempts=endpoint.max_attempts,
        )


def sync_plan(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    link_id: str,
    request: ProjectSyncPlanRequest,
) -> ProjectSyncPlanResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/projects/links/{link_id}/sync-plans",
            ProjectSyncPlanResponse,
            body=request,
            headers={"X-AI-STP-Organization-Id": organization_id},
            attempts=endpoint.max_attempts,
        )


def sync_apply(
    endpoint: Endpoint,
    access_token: str,
    organization_id: str,
    link_id: str,
    plan_id: str,
    request: ProjectSyncApplyRequest,
) -> ProjectSyncPlanResponse:
    with open_client(endpoint, access_token=access_token) as client:
        return call(
            client,
            "POST",
            f"/projects/links/{link_id}/sync-plans/{plan_id}/apply",
            ProjectSyncPlanResponse,
            body=request,
            headers={"X-AI-STP-Organization-Id": organization_id},
            attempts=endpoint.max_attempts,
        )
