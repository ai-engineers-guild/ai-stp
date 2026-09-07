"""Public orchestration of one setup across several provider-owned roots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from ai_stp_cli.answer import Answer
from ai_stp_cli.commands import install
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, installation, journal, multi_root, preserved_setups
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry
from ai_stp_cli.local.multi_root_orchestrator import Coordinator
from ai_stp_cli.local.passports import moment
from ai_stp_cli.provider import operation_v3, protocol_v3
from ai_stp_contracts.machine_help import MultiRootChildView, MultiRootTransactionView
from ai_stp_foundation.digests import digest_canonical
from ai_stp_foundation.ids import new_id

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
    with closing(open_registry(configured_path(), create=True)) as connection:
        for _scope, target in targets:
            held = multi_root.overlapping_reservation(
                connection, multi_root.resource_prefix_digests(target)
            )
            if held is not None:
                raise CliFailure(
                    "AI_STP_CONFLICT",
                    "scope-target values name overlapping physical roots",
                    details={"transaction_id": held},
                )
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
            children.append(
                multi_root.Child(
                    cast(multi_root.Scope, scope),
                    view.operation_id,
                    multi_root.resource_identity(target),
                    view.plan_digest,
                    view.state,
                    view.backup_ref,
                    resource_prefixes=multi_root.resource_prefix_digests(target),
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


def compose_environment(parameters: Mapping[str, object]) -> Answer[MultiRootTransactionView]:
    """Bind existing harness plans and their exact native footprints without effects."""
    operations = _repeated_strings(parameters.get("operation"))
    if not 2 <= len(operations) <= 21 or len(set(operations)) != len(operations):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "name two to twenty-one distinct child operations"
        )
    with closing(open_registry(configured_path())) as connection:
        children: list[multi_root.Child] = []
        for operation_id in operations:
            held = installation.plan(connection, str(operation_id))
            path = cache.stored_provider_plan(held.provider_plan_digest)
            if held.provider_protocol_version != 3 or path is None:
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED", "the exact native provider plan is unavailable"
                )
            planned = operation_v3.load_plan(path, held.provider_plan_digest)
            try:
                operation = protocol_v3.Operation(str(planned.artifact.get("operation")))
            except ValueError as error:
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED", "the provider plan names no native operation"
                ) from error
            if operation in operation_v3.SOFTWARE_OPERATIONS:
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED", "program lifecycles are planned separately"
                )
            operation_v3.require_native_capture(
                planned.artifact, operation=operation, capture_mode="complete_native"
            )
            native = planned.artifact["native_capture"]
            assert isinstance(native, dict)
            roots = native["roots"]
            assert isinstance(roots, list)
            scope = str(planned.artifact.get("target_scope") or "global")
            if scope not in multi_root.SCOPE_ORDER:
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED", "the provider plan names an unsupported scope"
                )
            _, harness = installation.target_pair(held.target_id)
            target = Path(held.provider_target)
            native_base = target.parent if native.get("base_root") == "parent" else target
            identity = digest_canonical(
                multi_root.TRANSACTION_DOMAIN,
                {
                    "resource": multi_root.resource_identity(target),
                    "harness": harness,
                    "scope": scope,
                },
            )
            children.append(
                multi_root.Child(
                    scope,
                    held.operation_id,
                    identity,
                    held.digest,
                    resource_chains=tuple(
                        multi_root.resource_prefix_digests(native_base / str(root))
                        for root in roots
                    ),
                )
            )
        ordered = sorted(children, key=lambda child: child.operation_id)
        result = Coordinator(connection).plan(
            setup_stable_id="",
            setup_version="",
            harness_id="",
            children=tuple(children),
            transaction_kind="environment",
            at=moment(),
            idempotency_key=digest_canonical(
                multi_root.TRANSACTION_DOMAIN,
                {
                    "environment": [
                        {"operation_id": child.operation_id, "plan_digest": child.plan_digest}
                        for child in ordered
                    ],
                },
            ),
        )
        return Answer(_view(result))


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
        before = multi_root.get(connection, transaction_id)
        if before.state == "verified":
            return Answer(_view(before))
        providers = _child_providers(before, parameters)
        held = coordinator.begin(transaction_id, at=moment())
        for child in held.children:
            try:
                with install.transaction_child_access():
                    result = install.apply(
                        {"operation": child.operation_id, "provider": providers[child.harness_id]}
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
        if held.state in multi_root.TERMINAL:
            return Answer(_view(held))
        providers = _child_providers(held, parameters)
        if held.state == "applying":
            for child in held.children:
                current = journal.get(connection, child.operation_id)
                if current is not None and current.state in {
                    installation.STATE_APPLYING,
                    installation.STATE_APPLIED_UNVERIFIED,
                }:
                    try:
                        with install.transaction_child_access():
                            install.resume(
                                {
                                    "operation": child.operation_id,
                                    "provider": providers[child.harness_id],
                                }
                            )
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


def cancel(parameters: Mapping[str, object]) -> Answer[MultiRootTransactionView]:
    """Abandon an unapplied multi-root plan and release every reserved target."""
    transaction_id = _required(parameters, "transaction")
    with closing(open_registry(configured_path(), create=True)) as connection:
        held = Coordinator(connection).cancel(
            transaction_id,
            at=moment(),
            reason=str(parameters.get("reason") or "cancelled by the agent"),
        )
        return Answer(_view(held))


def _compensate(
    coordinator: Coordinator,
    transaction_id: str,
    *,
    provider: str,
    parameters: Mapping[str, object],
) -> MultiRootTransactionView:
    held = multi_root.get(coordinator.connection, transaction_id)
    providers = _child_providers(held, parameters)
    if held.state != "compensating":
        held = coordinator.begin_compensation(transaction_id, at=moment())
    for child in reversed(held.children):
        provider = providers[child.harness_id]
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
        if current is not None and (
            current.state
            in {
                installation.STATE_APPLYING,
                installation.STATE_APPLIED_UNVERIFIED,
                installation.STATE_PARTIAL,
            }
            or (
                held.transaction_kind == "environment"
                and current.state == installation.STATE_VERIFIED
            )
        ):
            try:
                with install.transaction_child_access():
                    install.recover_preserved(
                        {"operation": child.operation_id, "provider": provider},
                        settle_provider=True,
                    )
                saved = preserved_setups.for_operation(coordinator.connection, child.operation_id)
                backup_ref = None if saved is None else saved.backup_ref
            except CliFailure:
                return _recovery_required(
                    coordinator,
                    transaction_id,
                    "a possibly changed child has no verified recovery path",
                )
        if current is None or not backup_ref:
            return _recovery_required(
                coordinator,
                transaction_id,
                "a possibly changed child has no verified recovery path",
            )
        if current.state not in {
            installation.STATE_VERIFIED,
            installation.STATE_APPLYING,
            installation.STATE_APPLIED_UNVERIFIED,
            installation.STATE_PARTIAL,
        }:
            continue
        original = installation.plan(coordinator.connection, child.operation_id)
        undo_id = _ensure_compensation_undo(
            coordinator,
            transaction_id,
            child,
            original,
            backup_ref=backup_ref,
            provider=provider,
            parameters=parameters,
        )
        if undo_id is None:
            return _recovery_required(
                coordinator, transaction_id, "provider compensation did not verify"
            )
        try:
            with install.transaction_child_access():
                current_undo = journal.get(coordinator.connection, undo_id)
                if current_undo is not None and current_undo.state in {
                    installation.STATE_APPLYING,
                    installation.STATE_APPLIED_UNVERIFIED,
                    installation.STATE_PARTIAL,
                }:
                    restored = install.resume({"operation": undo_id, "provider": provider}).payload
                elif current_undo is not None and current_undo.state == installation.STATE_VERIFIED:
                    restored = current_undo
                else:
                    restored = install.apply({"operation": undo_id, "provider": provider}).payload
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


def _ensure_compensation_undo(
    coordinator: Coordinator,
    transaction_id: str,
    child: multi_root.Child,
    original: installation.Plan,
    *,
    backup_ref: str,
    provider: str,
    parameters: Mapping[str, object],
) -> str | None:
    """Bind one undo operation id before any rollback effect, and reuse it."""
    undo_id = child.undo_operation_id
    if undo_id is None:
        undo_id = new_id("operation")
        coordinator.record_undo(
            transaction_id,
            child.operation_id,
            undo_operation_id=undo_id,
            at=moment(),
        )
    try:
        held = installation.plan(coordinator.connection, undo_id)
    except CliFailure:
        held = None
    if held is None:
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
            "operation-id": undo_id,
        }
        _copy_trust(parameters, rollback_parameters)
        with TemporaryDirectory(prefix="ai-stp-compensation-") as directory:
            if original.provider_release_manifest:
                manifest = Path(directory) / "provider-manifest.json"
                manifest.write_text(original.provider_release_manifest, encoding="utf-8")
                rollback_parameters["provider-manifest"] = str(manifest)
                rollback_parameters.pop("unverified-provider", None)
            elif original.provider_release_trust == "unverified":
                rollback_parameters["unverified-provider"] = True
            try:
                rollback = install.plan(rollback_parameters).payload
            except CliFailure:
                return None
        if rollback.operation_id != undo_id:
            undo_id = rollback.operation_id
            coordinator.record_undo(
                transaction_id,
                child.operation_id,
                undo_operation_id=undo_id,
                at=moment(),
            )
        digest = rollback.plan_digest
    else:
        digest = held.digest
    current_undo = journal.get(coordinator.connection, undo_id)
    if current_undo is None or current_undo.state == installation.STATE_PLANNED:
        try:
            install.approve({"operation": undo_id, "plan-digest": digest})
        except CliFailure:
            return None
    return undo_id


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


def _child_providers(
    held: multi_root.MultiRootTransaction,
    parameters: Mapping[str, object],
) -> dict[str, str]:
    names = _repeated_strings(parameters.get("provider-for"))
    found: dict[str, str] = {}
    harnesses = {child.harness_id for child in held.children}
    for name in names:
        harness, separator, path = str(name).partition("=")
        if not separator or not path or harness not in harnesses or harness in found:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR", "provider-for must name each harness at most once"
            )
        found[harness] = path
    fallback = str(parameters.get("provider") or "")
    if held.transaction_kind == "environment" and fallback:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR", "use provider-for to select separate harness providers"
        )
    return {harness: found.get(harness, fallback) for harness in harnesses}


def _repeated_strings(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, Sequence):
        raise CliFailure("AI_STP_VALIDATION_ERROR", "a repeated option must contain strings")
    result: list[str] = []
    for item in cast(Sequence[object], value):
        if not isinstance(item, str):
            raise CliFailure("AI_STP_VALIDATION_ERROR", "a repeated option must contain strings")
        result.append(item)
    return tuple(result)


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
            or not path.exists()
            or not path.is_dir()
        ):
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "scope-target must be a supported scope and existing absolute directory",
            )
        resolved = multi_root.canonical_resource(path)
        if not resolved.is_dir():
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "scope-target must be a supported scope and existing absolute directory",
            )
        for held_scope, held_path in found:
            if _paths_overlap(held_path, resolved):
                raise CliFailure(
                    "AI_STP_CONFLICT",
                    "scope-target values name overlapping physical roots",
                    details={"scope": scope, "other_scope": held_scope},
                )
        found.append((scope, resolved))
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


def _paths_overlap(left: Path, right: Path) -> bool:
    first, second = multi_root.canonical_resource(left), multi_root.canonical_resource(right)
    return first == second or first in second.parents or second in first.parents


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
    next_actions: list[str] = []
    if value.state == "planned" and value.approved_digest is None:
        next_actions.append(
            "install transaction approve "
            f"--transaction {value.transaction_id} "
            f"--transaction-digest {value.digest} --json"
        )
    if value.state == "planned":
        next_actions.append(
            f"install transaction cancel --transaction {value.transaction_id} --json"
        )
    if value.state == "recovery_required":
        next_actions.append(
            "install transaction recover "
            f"--transaction {value.transaction_id} "
            "--provider <executable> --json"
        )
    return MultiRootTransactionView(
        transaction_id=value.transaction_id,
        transaction_digest=value.digest,
        transaction_kind=value.transaction_kind,
        setup_stable_id=value.setup_stable_id or None,
        setup_version=value.setup_version or None,
        harness_id=value.harness_id or None,  # type: ignore[arg-type]
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
                harness_id=child.harness_id,  # type: ignore[arg-type]
                setup_stable_id=child.setup_stable_id or None,
                setup_version=child.setup_version or None,
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
