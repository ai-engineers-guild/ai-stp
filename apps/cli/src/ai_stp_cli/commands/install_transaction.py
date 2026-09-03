"""Public orchestration of one setup across several provider-owned roots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import cast

from ai_stp_cli.answer import Answer
from ai_stp_cli.commands import install
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import installation, journal, multi_root
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_cli.local.multi_root_orchestrator import Coordinator
from ai_stp_cli.local.passports import moment
from ai_stp_contracts.machine_help import MultiRootChildView, MultiRootTransactionView
from ai_stp_foundation.digests import digest_canonical

_TRUST_PARAMETERS = (
    "provider-manifest",
    "provider-build-attestation",
    "provider-attestation-bundle",
    "unverified-provider",
    "provider-release-recovery",
)


def plan(parameters: Mapping[str, object]) -> Answer[MultiRootTransactionView]:
    """Purely plan every named scope before recording one aggregate decision."""
    setup = _required(parameters, "setup")
    project = _required(parameters, "project")
    provider = str(parameters.get("provider") or "")
    targets = _scope_targets(parameters)
    children: list[multi_root.Child] = []
    planned_ids: list[str] = []
    try:
        for scope, target in targets:
            child_parameters: dict[str, object] = {
                "setup": setup,
                "project": project,
                "provider": provider,
                "protocol-version": 3,
                "target": str(target),
                "scope": scope,
                "action": "install",
            }
            _copy_trust(parameters, child_parameters)
            view = install.plan(child_parameters).payload
            planned_ids.append(view.operation_id)
            target_digest = digest_canonical(
                multi_root.TRANSACTION_DOMAIN,
                {"scope": scope, "target": str(target)},
            )
            target_token = f"{scope}:{target_digest}"
            children.append(
                multi_root.Child(
                    cast(multi_root.Scope, scope),
                    view.operation_id,
                    target_token,
                    view.plan_digest,
                    view.state,
                    view.backup_ref,
                )
            )
    except Exception:
        _cancel_unowned(planned_ids)
        raise

    with closing(open_registry(configured_path(), create=True)) as connection:
        first = installation.plan(connection, children[0].operation_id)
        transaction = Coordinator(connection).plan(
            setup_stable_id=first.setup_stable_id,
            setup_version=first.setup_version,
            harness_id=installation.target_pair(first.target_id)[1],
            children=tuple(children),
            idempotency_key=digest_canonical(
                multi_root.TRANSACTION_DOMAIN,
                {
                    "setup": setup,
                    "project": project,
                    "children": [
                        {
                            "scope": child.scope,
                            "target_id": child.target_id,
                            "plan_digest": child.plan_digest,
                        }
                        for child in children
                    ],
                },
            ),
            at=moment(),
        )
        return Answer(_view(transaction))


def approve(parameters: Mapping[str, object]) -> Answer[MultiRootTransactionView]:
    """Approve the aggregate digest and all child plan digests atomically."""
    transaction_id = _required(parameters, "transaction")
    digest = _required(parameters, "transaction-digest")
    with closing(open_registry(configured_path(), create=True)) as connection:
        held = Coordinator(connection).approve(transaction_id, expected_digest=digest, at=moment())
        return Answer(_view(held))


def apply(parameters: Mapping[str, object]) -> Answer[MultiRootTransactionView]:
    """Apply every child in order or compensate every possible effect."""
    transaction_id = _required(parameters, "transaction")
    provider = str(parameters.get("provider") or "")
    with closing(open_registry(configured_path(), create=True)) as connection:
        coordinator = Coordinator(connection)
        held = coordinator.begin(transaction_id, at=moment())
        for child in held.children:
            try:
                with install.transaction_child_access():
                    result = install.apply(
                        {"operation": child.operation_id, "provider": provider}
                    ).payload
                coordinator.observe_child(transaction_id, child.operation_id, at=moment())
                if result.state != installation.STATE_VERIFIED:
                    return Answer(
                        _compensate(
                            coordinator,
                            transaction_id,
                            provider=provider,
                            parameters=parameters,
                        )
                    )
            except Exception:
                coordinator.observe_child(transaction_id, child.operation_id, at=moment())
                return Answer(
                    _compensate(
                        coordinator,
                        transaction_id,
                        provider=provider,
                        parameters=parameters,
                    )
                )
        return Answer(_view(coordinator.finish_verified(transaction_id, at=moment())))


def recover(parameters: Mapping[str, object]) -> Answer[MultiRootTransactionView]:
    """Settle unknown child results, then finish success or reverse compensation."""
    transaction_id = _required(parameters, "transaction")
    provider = str(parameters.get("provider") or "")
    with closing(open_registry(configured_path(), create=True)) as connection:
        coordinator = Coordinator(connection)
        held = multi_root.get(connection, transaction_id)
        if held.state == "applying":
            for child in held.children:
                current = journal.get(connection, child.operation_id)
                if current is not None and current.state in {
                    installation.STATE_APPLYING,
                    installation.STATE_APPLIED_UNVERIFIED,
                }:
                    try:
                        with install.transaction_child_access():
                            install.resume({"operation": child.operation_id, "provider": provider})
                    except CliFailure:
                        pass
                coordinator.observe_child(transaction_id, child.operation_id, at=moment())
            held = multi_root.get(connection, transaction_id)
            if all(child.state == installation.STATE_VERIFIED for child in held.children):
                return Answer(_view(coordinator.finish_verified(transaction_id, at=moment())))
        return Answer(
            _compensate(
                coordinator,
                transaction_id,
                provider=provider,
                parameters=parameters,
            )
        )


def status(parameters: Mapping[str, object]) -> Answer[MultiRootTransactionView]:
    """Read one aggregate transaction without invoking a provider."""
    transaction_id = _required(parameters, "transaction")
    with closing(open_readonly(configured_path())) as connection:
        return Answer(_view(multi_root.get(connection, transaction_id)))


def _compensate(
    coordinator: Coordinator,
    transaction_id: str,
    *,
    provider: str,
    parameters: Mapping[str, object],
) -> MultiRootTransactionView:
    held = multi_root.get(coordinator.connection, transaction_id)
    if held.state != "compensating":
        held = coordinator.begin_compensation(transaction_id, at=moment())
    for child in reversed(held.children):
        current = journal.get(coordinator.connection, child.operation_id)
        if current is None:
            return _recovery_required(coordinator, transaction_id, "a child journal is unavailable")
        if current.state in {
            installation.STATE_PLANNED,
            installation.STATE_APPROVED,
            installation.STATE_FAILED,
            installation.STATE_STALE,
            installation.STATE_CANCELLED,
            installation.STATE_ROLLED_BACK,
        }:
            coordinator.observe_child(transaction_id, child.operation_id, at=moment())
            continue
        if current.state in {
            installation.STATE_APPLYING,
            installation.STATE_APPLIED_UNVERIFIED,
        }:
            try:
                with install.transaction_child_access():
                    install.resume({"operation": child.operation_id, "provider": provider})
            except CliFailure:
                pass
            coordinator.observe_child(transaction_id, child.operation_id, at=moment())
            current = journal.get(coordinator.connection, child.operation_id)
        backup_ref = installation.backup_reference(coordinator.connection, child.operation_id)
        if current is None or current.state == installation.STATE_PARTIAL or not backup_ref:
            return _recovery_required(
                coordinator,
                transaction_id,
                "a possibly changed child has no verified recovery path",
            )
        if current.state != installation.STATE_VERIFIED:
            continue
        original = installation.plan(coordinator.connection, child.operation_id)
        project, harness = installation.target_pair(original.target_id)
        rollback_parameters: dict[str, object] = {
            "project": project,
            "harness": harness,
            "provider": provider,
            "protocol-version": 3,
            "target": original.provider_target,
            "scope": child.scope,
            "action": "rollback",
            "backup-ref": backup_ref,
        }
        _copy_trust(parameters, rollback_parameters)
        try:
            rollback = install.plan(rollback_parameters).payload
            install.approve(
                {"operation": rollback.operation_id, "plan-digest": rollback.plan_digest}
            )
            restored = install.apply(
                {"operation": rollback.operation_id, "provider": provider}
            ).payload
        except CliFailure:
            return _recovery_required(
                coordinator, transaction_id, "provider compensation did not verify"
            )
        if restored.state != installation.STATE_VERIFIED:
            return _recovery_required(
                coordinator, transaction_id, "provider compensation did not verify"
            )
        coordinator.record_compensated(
            transaction_id, child.operation_id, backup_ref=backup_ref, at=moment()
        )
    return _view(coordinator.finish_rolled_back(transaction_id, at=moment()))


def _recovery_required(
    coordinator: Coordinator, transaction_id: str, reason: str
) -> MultiRootTransactionView:
    return _view(
        coordinator.require_recovery(
            transaction_id,
            at=moment(),
            reason=reason,
        )
    )


def _scope_targets(parameters: Mapping[str, object]) -> tuple[tuple[str, Path], ...]:
    raw = parameters.get("scope-target")
    values: Sequence[object] = (
        cast(Sequence[object], raw)
        if isinstance(raw, list | tuple)
        else (() if raw is None else (raw,))
    )
    found: list[tuple[str, Path]] = []
    for item in values:
        scope, separator, target = str(item).partition("=")
        path = Path(target).expanduser()
        if (
            not separator
            or scope not in multi_root.SCOPE_ORDER
            or not path.is_absolute()
            or path.is_symlink()
            or not path.is_dir()
        ):
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "scope-target must be a supported scope and existing absolute directory",
            )
        found.append((scope, path.resolve()))
    if len(found) < 2:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "multi-root planning requires at least two scope-target values",
        )
    if len({scope for scope, _path in found}) != len(found):
        raise CliFailure("AI_STP_VALIDATION_ERROR", "scope-target repeats a scope")
    return tuple(
        sorted(found, key=lambda item: multi_root.SCOPE_ORDER[cast(multi_root.Scope, item[0])])
    )


def _copy_trust(source: Mapping[str, object], target: dict[str, object]) -> None:
    for name in _TRUST_PARAMETERS:
        if name in source:
            target[name] = source[name]


def _cancel_unowned(operation_ids: list[str]) -> None:
    if not configured_path().exists():
        return
    with closing(open_registry(configured_path(), create=True)) as connection:
        for operation_id in operation_ids:
            current = journal.get(connection, operation_id)
            if current is not None and current.state == installation.STATE_PLANNED:
                installation.cancel(
                    connection,
                    operation_id,
                    at=moment(),
                    reason="multi-root planning did not complete",
                )


def _view(value: multi_root.MultiRootTransaction) -> MultiRootTransactionView:
    active = value.state not in multi_root.TERMINAL
    next_actions = (
        [
            "install transaction approve "
            f"--transaction {value.transaction_id} "
            f"--transaction-digest {value.digest} --json"
        ]
        if value.state == "planned" and value.approved_digest is None
        else (
            [
                "install transaction recover "
                f"--transaction {value.transaction_id} "
                "--provider <executable> --json"
            ]
            if value.state == "recovery_required"
            else []
        )
    )
    return MultiRootTransactionView(
        transaction_id=value.transaction_id,
        transaction_digest=value.digest,
        setup_stable_id=value.setup_stable_id,
        setup_version=value.setup_version,
        harness_id=value.harness_id,  # type: ignore[arg-type]
        state=value.state,
        approved=value.approved_digest == value.digest,
        children=[
            MultiRootChildView(
                scope=child.scope,
                operation_id=child.operation_id,
                target_id=child.target_id,
                plan_digest=child.plan_digest,
                state=child.state,
                backup_ref=child.backup_ref,
            )
            for child in value.children
        ],
        next_actions=next_actions if active else [],
    )


def _required(parameters: Mapping[str, object], name: str) -> str:
    value = str(parameters.get(name) or "")
    if not value:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a required multi-root transaction parameter is missing",
            details={"parameter": name},
        )
    return value
