"""Installation heartbeat orchestration (t-heartbeat, GitHub #215).

Gathers the closed local fact set, builds the request contract, and drives
the authenticated transport. Nothing here touches the anonymous telemetry
collector, and nothing emits a runtime invocation event.
"""

import base64
import sqlite3
import uuid
from collections.abc import Callable, Iterable, Mapping
from contextlib import closing, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from ai_stp_cli import config, heartbeat, identity
from ai_stp_cli.cloud import session as cloud_session
from ai_stp_cli.cloud.client import Endpoint, call, open_client
from ai_stp_cli.cloud.session import Session
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import harnesses as harness_detection
from ai_stp_cli.local import provider_installations
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_cli.runtime import cli_version
from ai_stp_cli.secrets import open_store
from ai_stp_contracts.auth import DeviceRefreshRequest, DeviceTokenResponse, device_refresh_message
from ai_stp_contracts.heartbeat import (
    DEFAULT_HEARTBEAT_RETRY_BASE_SECONDS,
    DEFAULT_HEARTBEAT_RETRY_MAX_SECONDS,
    InstallationHeartbeat,
    InstallationHeartbeatList,
    InstallationHeartbeatPolicy,
    InstallationHeartbeatRequest,
    InstallationHeartbeatStatus,
    InstallationHeartbeatSubscription,
    heartbeat_signature_message,
)
from ai_stp_foundation.timestamps import format_timestamp, parse_timestamp

AUTO_TIMEOUT_SECONDS: Final = 2.0


def _scheduled_session(target: Endpoint) -> Session:
    """Renew an enrolled device's session before a background credential expires."""
    store, _warning = open_store()
    held = cloud_session.load(store)
    if held is None or held.revoked:
        raise CliFailure("AI_STP_AUTH_REQUIRED", "the enrolled device must sign in again")
    if parse_timestamp(held.expires_at) > datetime.now(UTC) + timedelta(hours=12):
        return held
    signer, _warning = identity.load_or_create()
    if signer.device_id != held.device_id:
        raise CliFailure("AI_STP_DEVICE_REVOKED", "the enrolled device key has changed")
    unsigned = DeviceRefreshRequest(
        device_id=held.device_id,
        checked_at=format_timestamp(datetime.now(UTC)),
        signature="A" * 86,
    )
    signature = (
        base64.urlsafe_b64encode(signer.sign(device_refresh_message(unsigned)))
        .rstrip(b"=")
        .decode("ascii")
    )
    with open_client(
        target, access_token=held.refresh_token, timeout=AUTO_TIMEOUT_SECONDS
    ) as client:
        renewed = call(
            client,
            "POST",
            "/auth/device/refresh",
            DeviceTokenResponse,
            body=unsigned.model_copy(update={"signature": signature}),
            attempts=2,
        )
    if renewed.account_id != held.account_id or renewed.device_id != held.device_id:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "renewal changed the enrolled device")
    updated = Session(
        account_id=held.account_id,
        device_id=held.device_id,
        access_token=renewed.access_token,
        refresh_token=renewed.refresh_token,
        expires_at=cloud_session.expiry(renewed.expires_in),
    )
    cloud_session.save(store, updated)
    return updated


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
    probe_harnesses: bool = True,
    clock: Callable[[], datetime] | None = None,
) -> InstallationHeartbeatRequest:
    """Assemble the closed heartbeat payload for the held session."""
    local_capabilities, local_state = (
        _local_heartbeat_facts() if probe_harnesses else (["cli.heartbeat"], "active")
    )
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
        signature="A" * 86,  # replaced by send() before transport
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
    signer, _warning = identity.load_or_create()
    if signer.device_id != session.device_id:
        raise CliFailure("AI_STP_DEVICE_REVOKED", "the held device cannot sign this heartbeat")
    unsigned = request.model_copy(update={"signature": ""})
    signature = (
        base64.urlsafe_b64encode(
            signer.sign(heartbeat_signature_message(organization_id, unsigned))
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    signed = request.model_copy(update={"signature": signature})
    with open_client(endpoint, access_token=session.access_token, timeout=timeout) as client:
        return call(
            client,
            "PUT",
            f"/corporate/organizations/{organization_id}/telemetry/heartbeat",
            InstallationHeartbeat,
            body=signed,
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
    interval_seconds: int | None = None,
    now: datetime | None = None,
) -> InstallationHeartbeatSubscription:
    """Persist explicit local opt-in; repeated enable is idempotent."""
    moment = format_timestamp(now or datetime.now(UTC))
    with closing(open_registry(configured_path(), create=True)) as connection:
        connection.execute(
            "INSERT INTO heartbeat_subscription "
            "(organization_id, account_id, device_id, next_attempt_at, scheduler_interval_seconds) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (organization_id) DO UPDATE SET "
            "account_id = excluded.account_id, device_id = excluded.device_id, "
            "next_attempt_at = excluded.next_attempt_at, "
            "scheduler_interval_seconds = excluded.scheduler_interval_seconds, attempts = 0, "
            "last_attempt_at = NULL, last_success_at = NULL, attempt_token = NULL "
            "WHERE account_id != excluded.account_id OR device_id != excluded.device_id",
            (organization_id, account_id, device_id, moment, interval_seconds),
        )
        connection.execute(
            "UPDATE heartbeat_subscription SET scheduler_interval_seconds = ? "
            "WHERE organization_id = ?",
            (interval_seconds, organization_id),
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
    now: datetime, *, organization_id: str | None = None, scheduled: bool = False
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
            "WHERE (? = 1 OR next_attempt_at <= ?) AND (? IS NULL OR organization_id = ?) "
            "ORDER BY next_attempt_at, organization_id LIMIT 1",
            (int(scheduled), format_timestamp(now), organization_id, organization_id),
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


def maybe_send_due(
    *, now: datetime | None = None, organization_id: str | None = None, scheduled: bool = False
) -> None:
    """Attempt one due opt-in heartbeat after a successful ordinary invocation."""
    moment = now or datetime.now(UTC)
    try:
        claimed = _claim_due_subscription(
            moment, organization_id=organization_id, scheduled=scheduled
        )
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

        target = cloud_endpoint()
        session = (
            _scheduled_session(target)
            if scheduled
            else required("automatic installation heartbeat")
        )
        if session.account_id != account_id or session.device_id != device_id:
            _forget_claimed_subscription(organization_id, token)
            return
        current_policy = policy(
            target,
            session,
            organization_id,
            attempts=2 if scheduled else 1,
            timeout=AUTO_TIMEOUT_SECONDS,
        )
        retry_base = current_policy.retry_base_seconds
        retry_max = current_policy.retry_max_seconds
        if scheduled:
            with suppress(Exception):
                _update_scheduler_interval(organization_id, current_policy.interval_seconds)
        if not current_policy.enabled:
            _finish_attempt(
                organization_id,
                token,
                now=moment,
                defer_seconds=current_policy.interval_seconds,
            )
            return
        interval_seconds = current_policy.interval_seconds
        report = build_report(session, probe_harnesses=False)
        send(
            target,
            session,
            organization_id,
            report,
            attempts=2 if scheduled else 1,
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


def _update_scheduler_interval(organization_id: str, interval_seconds: int) -> None:
    """Repair the recurring OS task only when the server interval changes."""
    connection = _schedule_connection()
    if connection is None:
        return
    try:
        row = connection.execute(
            "SELECT scheduler_interval_seconds FROM heartbeat_subscription "
            "WHERE organization_id = ?",
            (organization_id,),
        ).fetchone()
        if row is None or row[0] == interval_seconds:
            return
        from ai_stp_cli.application import heartbeat_schedule

        installed = heartbeat_schedule.install(
            organization_id, interval_seconds, defer_mac_reload=True
        )
        if not installed:
            return
        connection.execute(
            "UPDATE heartbeat_subscription SET scheduler_interval_seconds = ? "
            "WHERE organization_id = ?",
            (interval_seconds, organization_id),
        )
    finally:
        connection.close()


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
