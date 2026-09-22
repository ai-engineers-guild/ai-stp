"""Installation heartbeat orchestration (t-heartbeat, GitHub #215).

Gathers the closed local fact set, builds the request contract, and drives
the authenticated transport. Nothing here touches the anonymous telemetry
collector, and nothing emits a runtime invocation event.
"""

from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from ai_stp_cli import heartbeat
from ai_stp_cli.cloud.client import Endpoint, call, open_client
from ai_stp_cli.cloud.session import Session
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.runtime import cli_version
from ai_stp_contracts.heartbeat import (
    InstallationHeartbeat,
    InstallationHeartbeatList,
    InstallationHeartbeatRequest,
    InstallationHeartbeatStatus,
)
from ai_stp_foundation.harnesses import HARNESS_IDS
from ai_stp_foundation.timestamps import format_timestamp, parse_timestamp


def collect_capabilities(extra: Iterable[str] = ()) -> list[str]:
    """Capability tokens: the heartbeat feature plus supported harnesses.

    `extra` entries are validated through the token alphabet - a value that
    would carry a path or arguments raises instead of shipping.
    """
    tokens = ["cli.heartbeat"]
    tokens.extend(f"harness.{harness}" for harness in sorted(HARNESS_IDS))
    for value in extra:
        token = heartbeat.capability_token(value)
        if token not in tokens:
            tokens.append(token)
    return tokens[: heartbeat.MAX_CAPABILITIES]


def build_report(
    session: Session,
    *,
    health_state: str = "active",
    last_sync_at: str | None = None,
    capabilities: Iterable[str] = (),
    clock: Callable[[], datetime] | None = None,
) -> InstallationHeartbeatRequest:
    """Assemble the closed heartbeat payload for the held session."""
    if health_state not in heartbeat.REPORTED_STATES:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a supplied value is not valid for this command",
            details={"option": "--state"},
        )
    if last_sync_at is not None:
        try:
            parse_timestamp(last_sync_at)
        except ValueError as error:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "a supplied value is not valid for this command",
                details={"option": "--last-sync-at"},
            ) from error
    checked = clock() if clock is not None else datetime.now(UTC)
    return InstallationHeartbeatRequest(
        account_id=session.account_id,
        device_id=session.device_id,
        cli_version=cli_version(),
        capabilities=collect_capabilities(capabilities),
        last_sync_at=last_sync_at,
        health_state=health_state,  # narrowed by the REPORTED_STATES check above
        checked_at=format_timestamp(checked),
    )


def send(
    endpoint: Endpoint,
    session: Session,
    organization_id: str,
    request: InstallationHeartbeatRequest,
) -> InstallationHeartbeat:
    """Write one heartbeat; the server coalesces replays and delayed beats."""
    with open_client(endpoint, access_token=session.access_token) as client:
        return call(
            client,
            "PUT",
            f"/corporate/organizations/{organization_id}/telemetry/heartbeat",
            InstallationHeartbeat,
            body=request,
            attempts=endpoint.max_attempts,
        )


def status(
    endpoint: Endpoint, session: Session, organization_id: str
) -> InstallationHeartbeatStatus:
    """Read this installation's evaluated health state."""
    with open_client(endpoint, access_token=session.access_token) as client:
        return call(
            client,
            "GET",
            f"/corporate/organizations/{organization_id}/telemetry/heartbeat",
            InstallationHeartbeatStatus,
            attempts=endpoint.max_attempts,
        )


def installations(
    endpoint: Endpoint,
    session: Session,
    organization_id: str,
    *,
    health_state: str | None = None,
) -> InstallationHeartbeatList:
    """List installation health visible to the caller's role."""
    query = {"health_state": health_state} if health_state else None
    with open_client(endpoint, access_token=session.access_token) as client:
        return call(
            client,
            "GET",
            f"/corporate/organizations/{organization_id}/telemetry/heartbeats",
            InstallationHeartbeatList,
            query=query,
            attempts=endpoint.max_attempts,
        )
