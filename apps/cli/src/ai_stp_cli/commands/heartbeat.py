"""`heartbeat` commands - report or read installation health (#215)."""

from collections.abc import Mapping

from ai_stp_cli.answer import Answer
from ai_stp_cli.application import heartbeat
from ai_stp_cli.commands import cloud_auth
from ai_stp_cli.commands.auth import endpoint
from ai_stp_cli.errors import CliFailure
from ai_stp_contracts.heartbeat import (
    InstallationHeartbeat,
    InstallationHeartbeatList,
    InstallationHeartbeatStatus,
    InstallationHeartbeatSubscription,
)


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = str(parameters.get(name) or "")
    if not value:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required option was not supplied",
            details={"option": f"--{name}"},
        )
    return value


def send(parameters: Mapping[str, object]) -> Answer[InstallationHeartbeat]:
    """Write this installation's heartbeat for one organization.

    Replays and delayed beats coalesce server-side; offline failure is a
    typed transport failure the caller retries on its own schedule.
    """
    held = cloud_auth.required("installation heartbeat")
    report = heartbeat.build_report(
        held,
        health_state=str(parameters.get("state") or "") or None,
        last_sync_at=str(parameters.get("last-sync-at") or "") or None,
    )
    return Answer(heartbeat.send(endpoint(), held, _required(parameters, "organization"), report))


def enable(parameters: Mapping[str, object]) -> Answer[InstallationHeartbeatSubscription]:
    """Opt this CLI installation into automatic heartbeats for one organization."""
    held = cloud_auth.required("automatic installation heartbeat")
    organization_id = _required(parameters, "organization")
    policy = heartbeat.policy(endpoint(), held, organization_id)
    if not policy.enabled:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the organization has disabled installation heartbeat reporting",
        )
    from ai_stp_cli.application import heartbeat_schedule

    heartbeat_schedule.install(organization_id)
    return Answer(
        heartbeat.enable_subscription(
            organization_id,
            account_id=held.account_id,
            device_id=held.device_id,
        )
    )


def disable(parameters: Mapping[str, object]) -> Answer[InstallationHeartbeatSubscription]:
    """Opt this CLI installation out without contacting the organization."""
    organization_id = _required(parameters, "organization")
    heartbeat.disable_subscription(organization_id)
    from ai_stp_cli.application import heartbeat_schedule

    heartbeat_schedule.remove(organization_id)
    return Answer(heartbeat.subscription_status(organization_id))


def tick(parameters: Mapping[str, object]) -> Answer[InstallationHeartbeatSubscription]:
    """Run one scheduled due check for this local organization subscription."""
    organization_id = _required(parameters, "organization")
    heartbeat.maybe_send_due(organization_id=organization_id)
    return Answer(heartbeat.subscription_status(organization_id))


def local_status(parameters: Mapping[str, object]) -> Answer[InstallationHeartbeatSubscription]:
    """Read local opt-in, scheduler registration, and recent attempt times."""
    return Answer(heartbeat.subscription_status(_required(parameters, "organization")))


def status(parameters: Mapping[str, object]) -> Answer[InstallationHeartbeatStatus]:
    """Read this installation's evaluated health state."""
    held = cloud_auth.required("installation heartbeat status")
    return Answer(heartbeat.status(endpoint(), held, _required(parameters, "organization")))


def installations(parameters: Mapping[str, object]) -> Answer[InstallationHeartbeatList]:
    """List installation health visible to the caller's role."""
    held = cloud_auth.required("installation heartbeat list")
    health_state = str(parameters.get("health") or "") or None
    return Answer(
        heartbeat.installations(
            endpoint(),
            held,
            _required(parameters, "organization"),
            health_state=health_state,
        )
    )
