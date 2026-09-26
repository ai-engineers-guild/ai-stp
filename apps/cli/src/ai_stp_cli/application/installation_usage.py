"""Deliver settled corporate installation facts from the existing local journal."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from contextlib import closing
from typing import cast

from ai_stp_cli.answer import Answer
from ai_stp_cli.cloud.client import Endpoint, call, open_client
from ai_stp_cli.cloud.session import Session
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, installation, journal, managed_diff, restored_provenance
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.installation_usage import (
    InstallationOperationBatch,
    InstallationOperationFact,
    InstallationOperationReceipt,
    InstalledComponent,
)


def _fact_components(
    connection: sqlite3.Connection, plan: installation.Plan
) -> tuple[list[InstalledComponent], bool, str, str]:
    """Exact bundle bindings when present, otherwise the setup passport list.

    A rollback contributes coordinates only through the recovered prior bundle.
    Standalone ``install --component`` members are bundle bindings, so a bundle
    that names them is the complete list even when the setup passport omits them.
    """
    digest = plan.bundle_artifact_digest
    setup_id = plan.setup_stable_id
    setup_version = plan.setup_version
    if plan.action == "rollback":
        recovered = restored_provenance.recovered_bundle(connection, plan.operation_id)
        if recovered is None:
            return [], False, "", ""
        digest = recovered.bundle_artifact_digest
        setup_id = setup_id or recovered.setup_stable_id
        setup_version = setup_version or recovered.setup_version
    loaded = _bundle_components(connection, digest) if digest else None
    if loaded is not None and loaded[4]:
        components, complete, bundle_setup, bundle_version, _has_bindings = loaded
        return components, complete, setup_id or bundle_setup, setup_version or bundle_version
    if plan.action == "rollback":
        return [], False, "", ""
    if loaded is not None and (loaded[2] or loaded[3]):
        setup_id = setup_id or loaded[2]
        setup_version = setup_version or loaded[3]
    components, complete = _components(connection, plan)
    return components, complete, setup_id, setup_version


def _bundle_components(
    connection: sqlite3.Connection, digest: str
) -> tuple[list[InstalledComponent], bool, str, str, bool] | None:
    try:
        archive = cache.stored_raw_artifact(digest)
        if archive is None:
            return None
        overview = managed_diff.bundle_overview(archive)
    except (CliFailure, OSError, ValueError):
        return None
    components: list[InstalledComponent] = []
    complete = True
    for binding in overview.components:
        passport = managed_diff.component_passport(connection, binding)
        try:
            if passport is None:
                raise ValueError("component passport unavailable")
            components.append(
                InstalledComponent(
                    kind=cast("str", passport.component_type),  # pyright: ignore[reportArgumentType]
                    stable_id=binding.stable_id,
                    version=binding.version,
                )
            )
        except ValueError:
            complete = False
    return (
        components,
        complete and bool(overview.components),
        overview.setup_stable_id,
        overview.setup_version,
        bool(overview.components),
    )


def _components(
    connection: sqlite3.Connection, plan: installation.Plan
) -> tuple[list[InstalledComponent], bool]:
    if not plan.setup_stable_id or not plan.setup_version:
        return [], False
    from ai_stp_cli.application.install import (
        _passport_document,  # pyright: ignore[reportPrivateUsage]
    )

    setup = _passport_document(connection, plan.setup_stable_id, plan.setup_version)
    if setup is None or not isinstance(setup.get("components"), list):
        return [], False
    refs = cast(list[object], setup["components"])
    components: list[InstalledComponent] = []
    complete = True
    for raw in refs:
        if not isinstance(raw, dict):
            complete = False
            continue
        ref = cast(dict[str, object], raw)
        stable_id = str(ref.get("stable_id") or "")
        version = str(ref.get("version") or "")
        document = None
        if stable_id and version:
            document = _passport_document(connection, stable_id, version)
        try:
            if document is None:
                raise ValueError("component passport unavailable")
            components.append(
                InstalledComponent(
                    kind=cast("str", document.get("component_type")),  # pyright: ignore[reportArgumentType]
                    stable_id=stable_id,
                    version=version,
                )
            )
        except ValueError:
            complete = False
    return components, complete and len(components) == len(refs)


def pending_facts(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    account_id: str,
    device_id: str,
    limit: int = 128,
) -> list[InstallationOperationFact]:
    """Read bounded undelivered terminal operations without inventing install events."""
    rows = connection.execute(
        "SELECT b.operation_id, b.project_id, b.scope FROM operation_corporate_binding b "
        "JOIN operation o ON o.operation_id = b.operation_id "
        "JOIN operation_plan p ON p.operation_id = b.operation_id "
        "WHERE b.organization_id = ? AND b.account_id = ? AND b.device_id = ? "
        "AND b.delivered_at IS NULL "
        "AND o.state IN ('verified','partial','rolled_back','failed','stale') "
        "AND p.action IN ('install','update','remove','rollback') "
        "ORDER BY b.created_at, b.operation_id LIMIT ?",
        (organization_id, account_id, device_id, limit),
    ).fetchall()
    result: list[InstallationOperationFact] = []
    for row in rows:
        operation_id = str(row["operation_id"])
        plan = installation._require(connection, operation_id)  # pyright: ignore[reportPrivateUsage]
        outcome = journal.get(connection, operation_id)
        if outcome is None:
            continue
        history = installation.events(connection, operation_id)
        occurred_at = history[-1].at if history else outcome.finished_at
        if not occurred_at:
            continue
        _, harness = installation.target_pair(plan.target_id)
        components, complete, setup_id, setup_version = _fact_components(connection, plan)
        result.append(
            InstallationOperationFact(
                operation_id=operation_id,
                organization_id=organization_id,
                employee_id=account_id,
                device_id=device_id,
                project_id=str(row["project_id"]),
                harness=harness,  # pyright: ignore[reportArgumentType]
                scope=str(row["scope"]),  # pyright: ignore[reportArgumentType]
                action=plan.action,  # pyright: ignore[reportArgumentType]
                result=cast("str", outcome.state),  # pyright: ignore[reportArgumentType]
                occurred_at=occurred_at,
                setup_stable_id=setup_id or None,
                setup_version=setup_version or None,
                components=components,
                components_complete=complete and outcome.state == "verified",
            )
        )
    return result


def sync(
    endpoint: Endpoint,
    session: Session,
    organization_id: str,
    *,
    timeout: float | None = None,
    attempts: int | None = None,
) -> InstallationOperationReceipt:
    """Send one batch; retain every rejected or unacknowledged operation."""
    with closing(open_registry(configured_path(), create=True)) as connection:
        facts = pending_facts(
            connection,
            organization_id=organization_id,
            account_id=session.account_id,
            device_id=session.device_id,
        )
        if not facts:
            return InstallationOperationReceipt()
        with open_client(endpoint, access_token=session.access_token, timeout=timeout) as client:
            receipt = call(
                client,
                "POST",
                f"/corporate/organizations/{organization_id}/telemetry/installation-operations",
                InstallationOperationReceipt,
                body=InstallationOperationBatch(operations=facts),
                attempts=endpoint.max_attempts if attempts is None else attempts,
            )
        sent_ids = {fact.operation_id for fact in facts}
        confirmed = set(receipt.accepted_ids) | set(receipt.duplicate_ids)
        rejected = set(receipt.rejected_ids)
        if confirmed & rejected or confirmed | rejected != sent_ids:
            raise ValueError("installation operation receipt does not match batch")
        for operation_id in confirmed:
            connection.execute(
                "UPDATE operation_corporate_binding SET delivered_at = CURRENT_TIMESTAMP "
                "WHERE operation_id = ? AND delivered_at IS NULL",
                (operation_id,),
            )
        connection.commit()
        return receipt


def sync_results(parameters: Mapping[str, object]) -> Answer[InstallationOperationReceipt]:
    from ai_stp_cli.application.auth import endpoint
    from ai_stp_cli.application.cloud_auth import required
    from ai_stp_cli.errors import CliFailure

    organization_id = str(parameters.get("organization") or "")
    if not organization_id:
        raise CliFailure("AI_STP_VALIDATION_ERROR", "--organization is required")
    return Answer(sync(endpoint(), required("corporate installation sync"), organization_id))
