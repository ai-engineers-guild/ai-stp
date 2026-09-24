"""Installation heartbeat orchestration (t-heartbeat, GitHub #215).

Gathers the closed local fact set, builds the request contract, and drives
the authenticated transport. Nothing here touches the anonymous telemetry
collector, and nothing emits a runtime invocation event.
"""

import sqlite3
import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import closing, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from ai_stp_cli import config, heartbeat
from ai_stp_cli.cloud.client import Endpoint, call, open_client
from ai_stp_cli.cloud.session import Session
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import harnesses as harness_detection
from ai_stp_cli.local import provider_installations
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_cli.runtime import cli_version
from ai_stp_contracts.heartbeat import (
    DEFAULT_HEARTBEAT_RETRY_BASE_SECONDS,
    DEFAULT_HEARTBEAT_RETRY_MAX_SECONDS,
    InstallationHeartbeat,
    InstallationHeartbeatList,
    InstallationHeartbeatPolicy,
    InstallationHeartbeatRequest,
    InstallationHeartbeatStatus,
    InstallationHeartbeatSubscription,
)
from ai_stp_foundation.timestamps import format_timestamp, parse_timestamp

AUTO_TIMEOUT_SECONDS: Final = 2.0


def collect_capabilities(extra: Iterable[str] = (), *, base: list[str] | None = None) -> list[str]:
    """Report local harness/provider facts with validated caller additions."""
    tokens = base
    if tokens is None:
        tokens, _state = _local_heartbeat_facts()
    return _with_extra(tokens, extra)


def _with_extra(tokens: list[str], extra: Iterable[str]) -> list[str]:
    result = list(tokens)
    for value in extra:
        token = heartbeat.capability_token(value)
        if token not in result:
            result.append(token)
    return result[: heartbeat.MAX_CAPABILITIES]


def _local_heartbeat_facts() -> tuple[list[str], str]:
    """Inspect installed harness/provider facts once for one outgoing report."""
    installed = harness_detection.present_installations(harness_detection.detect_all())
    providers = _provider_versions(installed)
    tokens = ["cli.heartbeat"]
    for item in installed:
        token = f"harness.{item.harness_id}"
        versions = {
            entry.normalized_version for entry in item.installations if entry.normalized_version
        }
        if len(versions) == 1:
            token += f"@{next(iter(versions))}"
        tokens.append(heartbeat.capability_token(token))
        if version := providers.get(item.harness_id):
            with suppress(ValueError):
                tokens.append(heartbeat.capability_token(f"provider.{item.harness_id}@{version}"))
    return tokens, _local_reported_state(installed, providers)


def _provider_versions(installed: Iterable[harness_detection.Found]) -> dict[str, str]:
    """Resolve providers for observed harnesses without running provider code."""
    rows = tuple(installed)
    if not rows:
        return {}
    try:
        configured = {
            item.path: str(item.value)
            for item in config.effective_config().values
            if item.path.startswith("provider.paths.")
        }
    except CliFailure:
        configured = {}
    try:
        registry = configured_path()
    except CliFailure:
        return {}
    try:
        connection = open_readonly(registry) if registry.exists() else None
    except (CliFailure, OSError, sqlite3.Error):
        connection = None
    try:
        versions: dict[str, str] = {}
        for item in rows:
            harness_id = item.harness_id
            try:
                found = provider_installations.resolve(
                    connection,
                    harness_id,
                    configured=configured.get(f"provider.paths.{harness_id}", ""),
                )
            except (CliFailure, OSError, sqlite3.Error):
                continue
            if found.path:
                identity = provider_installations.manifest_identity(Path(found.path))
                if identity is not None:
                    versions[harness_id] = identity.provider_version
        return versions
    finally:
        if connection is not None:
            connection.close()


def _local_reported_state(
    installed: Iterable[harness_detection.Found], provider_versions: Mapping[str, str]
) -> str:
    """Summarize provider evidence without claiming support for absent harnesses."""
    rows = tuple(installed)
    if not rows or len(provider_versions) == len(rows):
        return "active"
    if provider_versions:
        return "partial"
    return "failing"


def last_successful_sync_at(account_id: str) -> str | None:
    """Read the local sync cursor timestamp; absent history remains null."""
    try:
        registry = configured_path()
    except CliFailure:
        return None
    if not registry.is_file():
        return None
    try:
        with closing(open_readonly(registry)) as connection:
            row = connection.execute(
                "SELECT updated_at FROM sync_cursor WHERE account_id = ?", (account_id,)
            ).fetchone()
    except (CliFailure, sqlite3.Error):
        return None
    return None if row is None else str(row["updated_at"])


def build_report(
    session: Session,
    *,
    health_state: str | None = None,
    last_sync_at: str | None = None,
    capabilities: Iterable[str] = (),
    clock: Callable[[], datetime] | None = None,
) -> InstallationHeartbeatRequest:
    """Assemble the closed heartbeat payload for the held session."""
    local_capabilities, local_state = _local_heartbeat_facts()
    reported_state = health_state or local_state
    last_sync_at = last_sync_at or last_successful_sync_at(session.account_id)
    if reported_state not in heartbeat.REPORTED_STATES:
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
        capabilities=collect_capabilities(capabilities, base=local_capabilities),
        last_sync_at=last_sync_at,
        health_state=reported_state,  # narrowed by the REPORTED_STATES check above
        checked_at=format_timestamp(checked),
    )


def send(
    endpoint: Endpoint,
    session: Session,
    organization_id: str,
    request: InstallationHeartbeatRequest,
    *,
    attempts: int | None = None,
    timeout: float | None = None,
) -> InstallationHeartbeat:
    """Write one heartbeat; the server coalesces replays and delayed beats."""
    with open_client(endpoint, access_token=session.access_token, timeout=timeout) as client:
        return call(
            client,
            "PUT",
            f"/corporate/organizations/{organization_id}/telemetry/heartbeat",
            InstallationHeartbeat,
            body=request,
            attempts=endpoint.max_attempts if attempts is None else attempts,
        )


def policy(
    endpoint: Endpoint,
    session: Session,
    organization_id: str,
    *,
    attempts: int | None = None,
    timeout: float | None = None,
) -> InstallationHeartbeatPolicy:
    """Read the organization-owned heartbeat cadence and enablement."""
    with open_client(endpoint, access_token=session.access_token, timeout=timeout) as client:
        return call(
            client,
            "GET",
            f"/corporate/organizations/{organization_id}/telemetry/heartbeat/policy",
            InstallationHeartbeatPolicy,
            attempts=endpoint.max_attempts if attempts is None else attempts,
        )


def enable_subscription(
    organization_id: str,
    *,
    account_id: str,
    device_id: str,
    now: datetime | None = None,
) -> InstallationHeartbeatSubscription:
    """Persist explicit local opt-in; repeated enable is idempotent."""
    moment = format_timestamp(now or datetime.now(UTC))
    with closing(open_registry(configured_path(), create=True)) as connection:
        connection.execute(
            "INSERT INTO heartbeat_subscription "
            "(organization_id, account_id, device_id, next_attempt_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (organization_id) DO UPDATE SET "
            "account_id = excluded.account_id, device_id = excluded.device_id, "
            "next_attempt_at = excluded.next_attempt_at, attempts = 0, "
            "last_attempt_at = NULL, last_success_at = NULL, attempt_token = NULL "
            "WHERE account_id != excluded.account_id OR device_id != excluded.device_id",
            (organization_id, account_id, device_id, moment),
        )
    return subscription_status(organization_id)


def disable_subscription(organization_id: str) -> InstallationHeartbeatSubscription:
    """Remove local opt-in and its retry metadata without making a network call."""
    registry = configured_path()
    if registry.exists():
        with closing(open_registry(registry, create=False)) as connection:
            connection.execute(
                "DELETE FROM heartbeat_subscription WHERE organization_id = ?",
                (organization_id,),
            )
    return InstallationHeartbeatSubscription(organization_id=organization_id, enabled=False)


def subscription_status(organization_id: str) -> InstallationHeartbeatSubscription:
    """Read the local automatic-reporting schedule for one organization."""
    registry = configured_path()
    if not registry.exists():
        from ai_stp_cli.application import heartbeat_schedule

        return InstallationHeartbeatSubscription(
            organization_id=organization_id,
            enabled=False,
            scheduler_registered=heartbeat_schedule.present(organization_id),
        )
    with closing(open_registry(registry, create=False)) as connection:
        row = connection.execute(
            "SELECT next_attempt_at, last_attempt_at, last_success_at "
            "FROM heartbeat_subscription WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()
    from ai_stp_cli.application import heartbeat_schedule

    return InstallationHeartbeatSubscription(
        organization_id=organization_id,
        enabled=row is not None,
        next_attempt_at=None if row is None else str(row["next_attempt_at"]),
        last_attempt_at=None if row is None else row["last_attempt_at"],
        last_success_at=None if row is None else row["last_success_at"],
        scheduler_registered=heartbeat_schedule.present(organization_id),
    )


def _schedule_connection() -> sqlite3.Connection | None:
    """Open existing local state with a short wait; scheduled sends must fail open."""
    registry = configured_path()
    if not registry.is_file():
        return None
    connection = sqlite3.connect(registry, timeout=0.05, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=50")
    return connection


def _claim_due_subscription(
    now: datetime, *, organization_id: str | None = None
) -> tuple[str, str, str, str] | None:
    try:
        connection = _schedule_connection()
    except Exception:
        return None
    if connection is None:
        return None
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT organization_id, account_id, device_id "
            "FROM heartbeat_subscription "
            "WHERE next_attempt_at <= ? AND (? IS NULL OR organization_id = ?) "
            "ORDER BY next_attempt_at, organization_id LIMIT 1",
            (format_timestamp(now), organization_id, organization_id),
        ).fetchone()
        if row is None:
            connection.execute("COMMIT")
            return None
        organization_id = str(row["organization_id"])
        token = uuid.uuid4().hex
        connection.execute(
            "UPDATE heartbeat_subscription SET attempt_token = ?, next_attempt_at = ? "
            "WHERE organization_id = ?",
            (token, format_timestamp(now + timedelta(seconds=120)), organization_id),
        )
        connection.execute("COMMIT")
        return (
            organization_id,
            str(row["account_id"]),
            str(row["device_id"]),
            token,
        )
    except sqlite3.Error:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        return None
    finally:
        connection.close()


def _forget_claimed_subscription(organization_id: str, token: str) -> None:
    """Require explicit opt-in again after the held account or device changes."""
    try:
        connection = _schedule_connection()
    except Exception:
        return
    if connection is None:
        return
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM heartbeat_subscription WHERE organization_id = ? AND attempt_token = ?",
            (organization_id, token),
        )
        connection.execute("COMMIT")
    except sqlite3.Error:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
    finally:
        connection.close()


def _finish_attempt(
    organization_id: str,
    token: str,
    *,
    now: datetime,
    interval_seconds: int | None = None,
    defer_seconds: int | None = None,
    retry_base_seconds: int | None = None,
    retry_max_seconds: int | None = None,
) -> None:
    try:
        connection = _schedule_connection()
    except Exception:
        return
    if connection is None:
        return
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT attempts FROM heartbeat_subscription "
            "WHERE organization_id = ? AND attempt_token = ?",
            (organization_id, token),
        ).fetchone()
        if row is None:
            connection.execute("COMMIT")
            return
        if interval_seconds is not None:
            next_attempt = now + timedelta(seconds=interval_seconds)
            connection.execute(
                "UPDATE heartbeat_subscription SET attempts = 0, last_attempt_at = ?, "
                "last_success_at = ?, next_attempt_at = ?, attempt_token = NULL "
                "WHERE organization_id = ? AND attempt_token = ?",
                (
                    format_timestamp(now),
                    format_timestamp(now),
                    format_timestamp(next_attempt),
                    organization_id,
                    token,
                ),
            )
        elif defer_seconds is not None:
            connection.execute(
                "UPDATE heartbeat_subscription SET last_attempt_at = ?, next_attempt_at = ?, "
                "attempt_token = NULL WHERE organization_id = ? AND attempt_token = ?",
                (
                    format_timestamp(now),
                    format_timestamp(now + timedelta(seconds=defer_seconds)),
                    organization_id,
                    token,
                ),
            )
        else:
            attempts = int(row["attempts"]) + 1
            base = retry_base_seconds or DEFAULT_HEARTBEAT_RETRY_BASE_SECONDS
            maximum = retry_max_seconds or DEFAULT_HEARTBEAT_RETRY_MAX_SECONDS
            delay = min(maximum, base * 2 ** min(attempts - 1, 20))
            connection.execute(
                "UPDATE heartbeat_subscription SET attempts = ?, last_attempt_at = ?, "
                "next_attempt_at = ?, attempt_token = NULL "
                "WHERE organization_id = ? AND attempt_token = ?",
                (
                    attempts,
                    format_timestamp(now),
                    format_timestamp(now + timedelta(seconds=delay)),
                    organization_id,
                    token,
                ),
            )
        connection.execute("COMMIT")
    except sqlite3.Error:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
    finally:
        connection.close()


def maybe_send_due(*, now: datetime | None = None, organization_id: str | None = None) -> None:
    """Attempt one due opt-in heartbeat after a successful ordinary invocation."""
    moment = now or datetime.now(UTC)
    try:
        claimed = _claim_due_subscription(moment, organization_id=organization_id)
    except Exception:
        return
    if claimed is None:
        return
    organization_id, account_id, device_id, token = claimed
    retry_base = DEFAULT_HEARTBEAT_RETRY_BASE_SECONDS
    retry_max = DEFAULT_HEARTBEAT_RETRY_MAX_SECONDS
    interval_seconds: int | None = None
    try:
        from ai_stp_cli.application.auth import endpoint as cloud_endpoint
        from ai_stp_cli.application.cloud_auth import required

        session = required("automatic installation heartbeat")
        if session.account_id != account_id or session.device_id != device_id:
            _forget_claimed_subscription(organization_id, token)
            return
        target = cloud_endpoint()
        current_policy = policy(
            target,
            session,
            organization_id,
            attempts=1,
            timeout=AUTO_TIMEOUT_SECONDS,
        )
        retry_base = current_policy.retry_base_seconds
        retry_max = current_policy.retry_max_seconds
        if not current_policy.enabled:
            _finish_attempt(
                organization_id,
                token,
                now=moment,
                defer_seconds=current_policy.interval_seconds,
            )
            return
        interval_seconds = current_policy.interval_seconds
        report = build_report(session)
        send(
            target,
            session,
            organization_id,
            report,
            attempts=1,
            timeout=AUTO_TIMEOUT_SECONDS,
        )
    except Exception:
        _finish_attempt(
            organization_id,
            token,
            now=moment,
            retry_base_seconds=retry_base,
            retry_max_seconds=retry_max,
        )
        return
    _finish_attempt(
        organization_id,
        token,
        now=moment,
        interval_seconds=interval_seconds,
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
