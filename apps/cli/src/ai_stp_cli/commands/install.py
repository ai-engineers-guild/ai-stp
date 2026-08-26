"""`ai-stp install` — the operation surface over the installation machine (`#173`).

One command per step the contract makes separate: plan, approve, apply, the two
ways of looking at what happened, and the one that finishes a check a lost
process never made. They are separate because each is a different decision, and
a single command that did them all would take the user's approval for a plan
they had not seen.

**`ai_stp` never writes the target.** Every effect goes through the provider
executable named by the caller, started under the frozen boundary of
`provider.protocol`. This module records what happened and refuses to record
what cannot have happened; it does not touch a harness configuration.

**A provider result is mapped, never trusted verbatim.** `protocol.operation_state`
refuses a state it does not know rather than writing it into the journal, because
the one thing an operation log must not do is claim to know what happened when it
does not.
"""

import os
import platform
import re
import sqlite3
import subprocess
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Final, cast

from ai_stp_cli import config, telemetry
from ai_stp_cli.answer import Answer
from ai_stp_cli.commands import select as select_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import (
    bundle,
    cache,
    harnesses,
    installation,
    journal,
    managed_diff,
    project_passport,
    provider_releases,
    revisions,
    selection,
    targets,
    versions,
)
from ai_stp_cli.local.database import configured_path, open_readonly, open_registry, transaction
from ai_stp_cli.local.passports import moment, owner
from ai_stp_cli.paths import redact_home
from ai_stp_cli.provider import (
    build_attestation,
    bundle_protocol,
    conformance,
    invocation,
    operation_v3,
    protocol,
    protocol_v2,
    protocol_v3,
    release,
)
from ai_stp_cli.provider import (
    status as provider_status,
)
from ai_stp_cli.runtime import cli_version
from ai_stp_contracts.machine_help import (
    InstallationStatus,
    InstallationStep,
    InstallationView,
    ManagedPathChange,
    RecoveryView,
    RollbackTarget,
    TargetBackup,
    TargetBackups,
    TargetDiff,
    TargetSurvey,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.timestamps import format_timestamp, parse_timestamp
from ai_stp_passports.versions import ENV_NAME_PATTERN


@dataclass(frozen=True)
class _ReleaseEvidence:
    manifest: release.ReleaseManifest | None
    trust: str = "unverified"
    evidence: str = ""


#: How long a plan stays applicable. Short, because a plan is a statement about
#: a target as it was: the longer it lives, the more likely it describes
#: something that has moved.
PLAN_TTL_SECONDS: int = 900

#: The two states an operation can be left in when the process running it dies:
#: the provider was called, and nobody has looked since. Everything else has
#: already settled, and resuming a settled operation would rewrite an answer.
_UNFINISHED: Final[frozenset[str]] = frozenset(
    {installation.STATE_APPLYING, installation.STATE_APPLIED_UNVERIFIED}
)

#: The passport contract owns the syntax. Reusing it here prevents a status
#: override from accepting a value that the persisted passport would refuse.
_ENV_NAME: Final[re.Pattern[str]] = re.compile(ENV_NAME_PATTERN)


def _prepared_setup_source(
    connection: sqlite3.Connection, reference: str, project: str
) -> selection.Proposal:
    """Represent one immutable prepared SetupVersion as an installation source.

    This creates no second install route and no durable proposal.  It merely
    adapts the already-finalized exact graph to the same internal source shape
    used by a newly confirmed composition; protocol-v3 compilation below then
    calls the same ``compile_setup_version_bundle`` function for both.
    """
    stable_id, separator, version = reference.rpartition("@")
    if not separator or not stable_id or not version:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a prepared setup is named as <stable_id>@<X.Y>",
            details={"setup": reference},
        )
    recorded = versions.held(connection, stable_id, version)
    if recorded is None:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "the exact prepared SetupVersion is not held by this registry",
            details={"stable_id": stable_id, "version": version},
        )
    stored = revisions.get(connection, recorded.revision_id)
    if stored is None or stored.stable_id != stable_id or stored.envelope.kind != "setup":
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the prepared setup version does not resolve to one setup passport",
            details={"stable_id": stable_id, "version": version},
        )
    document = cast(dict[str, JsonValue], stored.envelope.model_dump(mode="json"))
    harness_id = str(document.get("harness_id") or "")
    raw_components = document.get("components")
    facts = document.get("facts")
    if not harness_id or not isinstance(raw_components, list) or not raw_components:
        raise CliFailure(
            "AI_STP_CONFLICT",
            "the prepared setup passport has no complete harness/component identity",
            details={"stable_id": stable_id, "version": version},
        )
    project_id = ""
    snapshot = ""
    if isinstance(facts, dict):
        project_id = _fact_text(facts.get("project_id"))
        snapshot = _fact_text(facts.get("snapshot"))
    members: list[selection.Member] = []
    for item in raw_components:
        if not isinstance(item, dict):
            raise CliFailure(
                "AI_STP_CONFLICT",
                "the prepared setup contains a malformed exact component reference",
            )
        members.append(
            selection.Member(
                stable_id=str(item.get("stable_id") or ""),
                version=str(item.get("version") or ""),
                passport_digest=str(item.get("passport_digest") or ""),
                lane="prepared_exact_graph",
                lane_reason="stored immutable SetupVersion selected explicitly",
            )
        )
    if project:
        context = select_command.context_for_project(connection, harness_id, Path(project))
        project_id = context.project_id
        snapshot = context.snapshot(tuple(members))
    if not project_id or not snapshot:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this catalogue setup needs an explicit local project context",
            details={"stable_id": stable_id, "version": version},
            next_actions=[
                "project passport --root <path> --json",
                f"install plan --setup {reference} --project <path> ...",
            ],
        )
    return selection.Proposal(
        proposal_id=f"prepared:{stable_id}@{version}",
        project_id=project_id,
        harness_id=harness_id,
        snapshot=snapshot,
        members=tuple(members),
        created_at=stored.created_at,
        expires_at="9999-12-31T23:59:59.999Z",
        confirmed_stable_id=stable_id,
        confirmed_version=version,
    )


def _fact_text(value: JsonValue | None) -> str:
    if not isinstance(value, dict):
        return ""
    held = value.get("value")
    return held if isinstance(held, str) else ""


@dataclass(frozen=True)
class _Pair:
    """The project and harness an operation binds to.

    Named separately from the proposal because `backup` and `rollback` have one
    without having the other: they bind to a target, not to a setup graph.
    """

    project_id: str
    harness_id: str


def plan(parameters: Mapping[str, object]) -> Answer[InstallationView]:
    """Compute an immutable plan. Has no effect of its own (`REQ-805`).

    The target's current state is read from the provider rather than assumed,
    and recorded in the plan. That reading is what `apply` compares against
    under the lock, so a target that moves between the two is caught instead of
    being written over.
    """
    executable = _executable(parameters)
    proposal_id = str(parameters.get("proposal") or "")
    prepared_ref = str(parameters.get("setup") or "")
    action = str(parameters.get("action") or "install")
    # `backup` and `rollback` do not install a graph, so naming a source for
    # them meant naming one the operation would not use. It forced the current
    # or a past version into an operation that binds to a `BackupRef` and a
    # target instead — and made a deliberate restore unreachable for anybody
    # who had not kept the source around (`REQ-1207`-`REQ-1210`).
    #
    # `install` and `update` keep the rule: those two do install a graph, and
    # exactly one source is what says which.
    if action in _SOURCELESS_ACTIONS:
        if proposal_id and prepared_ref:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "name at most one confirmed proposal or prepared exact SetupVersion",
                details={"action": action},
            )
        if not proposal_id and not prepared_ref:
            _required(parameters, "project")
            _required(parameters, "harness")
    elif bool(proposal_id) == bool(prepared_ref):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "name exactly one confirmed proposal or prepared exact SetupVersion",
            next_actions=[
                "install plan --proposal <id> ...",
                "install plan --setup <id>@<X.Y> ...",
            ],
        )

    def work(connection: sqlite3.Connection) -> InstallationView:
        named_source = bool(proposal_id or prepared_ref)
        held = (
            (
                _prepared_setup_source(
                    connection, prepared_ref, str(parameters.get("project") or "")
                )
                if prepared_ref
                else selection.held(connection, proposal_id)
            )
            if named_source
            else None
        )
        if named_source and (held is None or held.confirmed_version is None):
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "only a confirmed composition or immutable prepared SetupVersion can be installed",
                details={"proposal_id": proposal_id, "setup": prepared_ref},
                next_actions=[f"select confirm --proposal {proposal_id} --json"],
            )
        pair = (
            _Pair(held.project_id, held.harness_id)
            if held is not None
            else _Pair(_required(parameters, "project"), _required(parameters, "harness"))
        )
        target = f"{pair.project_id}:{pair.harness_id}"
        release_recovery = bool(parameters.get("provider-release-recovery", False))
        release_evidence = _trusted_manifest(
            connection,
            parameters,
            executable,
            recovery_requested=release_recovery,
        )
        trusted_release = release_evidence.manifest
        protocol_version = _protocol_version(parameters, trusted_release)
        _release_required(parameters, protocol_version, trusted_release)
        if prepared_ref and protocol_version != protocol_v3.VERSION:
            raise CliFailure(
                "AI_STP_SCHEMA_UNSUPPORTED",
                "prepared SetupVersion installation requires provider protocol v3",
                details={"protocol_version": str(protocol_version)},
            )
        provider_target = _provider_target(parameters, target, protocol_version)
        invoke = invocation.provider_invoker(
            executable,
            provider_target,
            protocol_version,
            unisolated_reason=_unisolated_reason(trusted_release, parameters),
        )
        info = _object(invoke("provider-info", ()))
        _speaks(info, protocol_version)
        provider_version = str(info.get("provider_version", ""))
        if not provider_version:
            raise CliFailure(
                "AI_STP_SCHEMA_UNSUPPORTED",
                "the provider does not report its version",
            )
        if trusted_release is not None and provider_version != trusted_release.provider_version:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the provider process reports a version different from its signed manifest",
                details={
                    "reported": provider_version,
                    "manifest": trusted_release.provider_version,
                },
            )
        release_manifest = (
            "" if trusted_release is None else release.serialize_manifest(trusted_release)
        )
        if protocol_version == protocol_v3.VERSION:
            return _plan_v3(
                connection,
                parameters=parameters,
                executable=executable,
                pair=pair,
                proposal=held,
                action=action,
                provider_target=provider_target,
                info=info,
                invoke=invoke,
                provider_version=provider_version,
                release_manifest=release_manifest,
                release_recovery=release_recovery,
                release_trust=release_evidence.trust,
                release_evidence=release_evidence.evidence,
                trusted_release=trusted_release,
            )
        if held is None:
            # Reachable only by asking for `backup` or `rollback` without a
            # source under protocol v1, where the plan is a compiled bundle and
            # a bundle needs a graph. Refused by name rather than failing later
            # on an attribute nobody chose to leave empty.
            raise CliFailure(
                "AI_STP_SCHEMA_UNSUPPORTED",
                "this action without a named setup requires provider protocol v3",
                details={"action": action, "protocol_version": str(protocol_version)},
                next_actions=["install plan --protocol-version 3 ..."],
            )
        _supports_bundle(info, held.harness_id, bundle.BUNDLE_FORMAT)
        compiled = select_command.compile_harness_bundle(connection, proposal_id, held.harness_id)
        bundle_path = cache.store_raw_artifact_bytes(compiled.archive, compiled.artifact_digest)
        bound_bundle = bundle_protocol.binding(
            bundle_path,
            bundle_format=bundle.BUNDLE_FORMAT,
            bundle_digest=compiled.digest,
            artifact_digest=compiled.artifact_digest,
            bundle_size=len(compiled.archive),
        )
        expected_target_digest = _target_digest(invoke)
        bundle_protocol.require_validated(
            _object(invoke("validate-bundle", bound_bundle.common_arguments())),
            bound_bundle,
        )
        provider_plan = bundle_protocol.require_plan(
            _object(invoke("plan-bundle", bound_bundle.plan_arguments(expected_target_digest))),
            bound_bundle,
            expected_target_digest,
        )

        at = moment()
        recorded = installation.propose(
            connection,
            action=action,
            author=owner().account_id,
            target_id=target,
            expected_target_digest=expected_target_digest,
            provider_version=provider_version,
            provider_protocol_version=protocol_version,
            provider_target=provider_target,
            provider_release_manifest=release_manifest,
            provider_release_recovery=release_recovery,
            provider_release_trust=release_evidence.trust,
            provider_release_evidence=release_evidence.evidence,
            bundle_format=bound_bundle.bundle_format,
            bundle_digest=bound_bundle.bundle_digest,
            bundle_artifact_digest=bound_bundle.artifact_digest,
            bundle_size=bound_bundle.bundle_size,
            provider_plan_digest=provider_plan.digest,
            effects=provider_plan.effects,
            recovery_action="restore the provider backup",
            # One plan per composition and target: asking twice returns the plan
            # already made rather than a second one describing the same work.
            idempotency_key=(
                f"{proposal_id}:{target}:{action}:"
                f"{protocol_version}:{provider_version}:{provider_target}:"
                f"{'' if trusted_release is None else release.manifest_identity(trusted_release)}:"
                f"{release_recovery}:{bound_bundle.bundle_format}:{bound_bundle.bundle_digest}:"
                f"{bound_bundle.artifact_digest}:{bound_bundle.bundle_size}:"
                f"{provider_plan.digest}"
            ),
            at=at,
            expires_at=_plus(at, PLAN_TTL_SECONDS),
            # Which setup version this operation installs. The operation log is
            # where `target status` reads the installed version from, so a plan
            # that left this out would verify successfully and still leave the
            # target reading `pending_install` forever.
            setup_stable_id=held.confirmed_stable_id or "",
            setup_version=held.confirmed_version or "",
        )
        return _view(connection, recorded)

    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(work(connection))


def _plan_v3(
    connection: sqlite3.Connection,
    *,
    parameters: Mapping[str, object],
    executable: str,
    pair: _Pair,
    proposal: selection.Proposal | None,
    action: str,
    provider_target: str,
    info: dict[str, JsonValue],
    invoke: conformance.Invoker,
    provider_version: str,
    release_manifest: str,
    release_recovery: bool,
    release_trust: str,
    release_evidence: str,
    trusted_release: release.ReleaseManifest | None,
) -> InstallationView:
    """Plan the existing installation state machine through protocol v3."""
    capabilities = _v3_capabilities(info, pair.harness_id, bundle.BUNDLE_FORMAT)
    operation = _v3_operation(action)
    try:
        capabilities.require(operation)
    except protocol_v3.UnsupportedOperation as error:
        raise CliFailure(
            "AI_STP_SCHEMA_UNSUPPORTED",
            "the provider does not support the requested native operation",
            details={"operation": error.operation.value, "reason": error.reason.value},
        ) from error
    permission_profile = str(parameters.get("permission-profile") or "") or None
    if (
        permission_profile is not None
        and permission_profile not in capabilities.permission_profiles
    ):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the requested permission profile is not declared by the provider",
            details={"permission_profile": permission_profile},
        )
    backup_ref = str(parameters.get("backup-ref") or "") or None
    if operation is protocol_v3.Operation.RESTORE and backup_ref is None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "rollback requires the exact provider-owned BackupRef",
            next_actions=["install plan --action rollback --backup-ref <ref> --json"],
        )

    compiled: bundle.Bundle | None = None
    bound_bundle: bundle_protocol.Binding | None = None
    if operation in {protocol_v3.Operation.INSTALL, protocol_v3.Operation.REPLACE}:
        if (
            proposal is None
            or proposal.confirmed_stable_id is None
            or proposal.confirmed_version is None
        ):
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the installation source has no immutable SetupVersion identity",
            )
        compiled = select_command.compile_setup_version_bundle(
            connection,
            proposal.confirmed_stable_id,
            proposal.confirmed_version,
            expected_harness=pair.harness_id,
        )
        _v3_profile_accepts(capabilities, compiled)
        bundle_path = cache.store_raw_artifact_bytes(compiled.archive, compiled.artifact_digest)
        bound_bundle = bundle_protocol.binding(
            bundle_path,
            bundle_format=bundle.BUNDLE_FORMAT,
            bundle_digest=compiled.digest,
            artifact_digest=compiled.artifact_digest,
            bundle_size=len(compiled.archive),
        )
        bundle_protocol.require_validated(
            _object(invoke("validate-bundle", bound_bundle.common_arguments())),
            bound_bundle,
        )

    expected_target_digest = _target_digest(invoke)
    release_digest = (
        trusted_release.artifact_digest
        if trusted_release is not None
        else release.artifact_identity(Path(executable))[0]
    )
    at = moment()
    expires_at = _plus(at, PLAN_TTL_SECONDS)
    idempotency_key = ":".join(
        (
            # A restore is made unique by the copy it binds to, not by a
            # source it does not have; the key already carries `backup_ref`
            # and the target digest below.
            "" if proposal is None else proposal.proposal_id,
            f"{pair.project_id}:{pair.harness_id}",
            action,
            str(protocol_v3.VERSION),
            provider_version,
            provider_target,
            release_digest,
            str(release_recovery),
            capabilities.projection.digest,
            expected_target_digest,
            "" if bound_bundle is None else bound_bundle.bundle_digest,
            "" if bound_bundle is None else bound_bundle.artifact_digest,
            backup_ref or "",
            permission_profile or "",
        )
    )
    existing = installation.active_for_idempotency(connection, idempotency_key)
    if existing is not None:
        return _view(connection, existing)

    operation_id = new_id("operation")
    arguments = operation_v3.plan_operation_arguments(
        operation=operation,
        release_digest=release_digest,
        operation_id=operation_id,
        expires_at=expires_at,
        backup_ref=backup_ref,
        permission_profile=permission_profile,
        bundle=bound_bundle,
    )
    provider_plan = operation_v3.require_plan(
        _object(invoke("plan-operation", arguments)),
        capabilities=capabilities,
        release_digest=release_digest,
        operation_id=operation_id,
        operation=operation,
        target=Path(provider_target),
        expected_target_digest=expected_target_digest,
        bundle=bound_bundle,
        backup_ref=backup_ref,
        permission_profile=permission_profile,
        expires_at=expires_at,
    )
    cache.store_provider_plan(provider_plan.artifact, provider_plan.digest)
    recorded = installation.propose(
        connection,
        action=action,
        author=owner().account_id,
        target_id=f"{pair.project_id}:{pair.harness_id}",
        expected_target_digest=expected_target_digest,
        provider_version=provider_version,
        provider_protocol_version=protocol_v3.VERSION,
        provider_target=provider_target,
        provider_release_manifest=release_manifest,
        provider_release_recovery=release_recovery,
        provider_release_trust=release_trust,
        provider_release_evidence=release_evidence,
        bundle_format="" if bound_bundle is None else bound_bundle.bundle_format,
        bundle_digest="" if bound_bundle is None else bound_bundle.bundle_digest,
        bundle_artifact_digest="" if bound_bundle is None else bound_bundle.artifact_digest,
        bundle_size=0 if bound_bundle is None else bound_bundle.bundle_size,
        provider_plan_digest=provider_plan.digest,
        effects=provider_plan.effects,
        recovery_action="restore the provider backup",
        idempotency_key=idempotency_key,
        at=at,
        expires_at=expires_at,
        setup_stable_id="" if proposal is None else (proposal.confirmed_stable_id or ""),
        setup_version="" if proposal is None else (proposal.confirmed_version or ""),
        operation_id=operation_id,
    )
    return _view(connection, recorded)


def approve(parameters: Mapping[str, object]) -> Answer[InstallationView]:
    """Record the user's decision against one exact plan digest.

    The digest is the confirmation. `operation.md` binds an approval to an exact
    hash and says it does not carry to a new plan, so this takes the value the
    user saw rather than a flag meaning "whatever is in front of me".
    """
    operation_id = _operation(parameters)
    digest = str(parameters.get("plan-digest") or "")
    if not digest:
        raise CliFailure(
            "AI_STP_USER_DECISION_REQUIRED",
            "this plan is approved by its exact digest, which the plan answer carries",
            details={"operation_id": operation_id},
            next_actions=["install plan --proposal <id> --provider <path>"],
        )

    with closing(open_registry(configured_path(), create=True)) as connection:
        installation.approve(connection, operation_id, plan_digest=digest, at=moment())
        return Answer(_view(connection, installation._require(connection, operation_id)))  # pyright: ignore[reportPrivateUsage]


def apply(parameters: Mapping[str, object]) -> Answer[InstallationView]:
    """Carry out one approved plan through the provider, and record what happened.

    The order is the contract's: take the lock, re-check the target inside it,
    let the provider act, record `applied_unverified` *before* looking, then
    verify. A caller that reads only the final state still learns the truth,
    because every step is durable before the next one starts.

    An interrupted provider call is recorded as `partial`, never as a failure:
    a call that timed out does not prove nothing happened.
    """
    executable = _executable(parameters)
    operation_id = _operation(parameters)

    def work(connection: sqlite3.Connection) -> InstallationView:
        held = installation._require(connection, operation_id)  # pyright: ignore[reportPrivateUsage]
        trusted_release = _verify_bound_release(connection, held, executable)
        invoke = invocation.provider_invoker(
            executable,
            held.provider_target or held.target_id,
            held.provider_protocol_version,
            unisolated_reason=_unisolated_reason(trusted_release, parameters),
        )
        bound_bundle = (
            _bound_bundle_v3(held)
            if held.provider_protocol_version == protocol_v3.VERSION
            else _bound_bundle(held)
        )
        info = _object(invoke("provider-info", ()))
        _speaks(info, held.provider_protocol_version)
        if held.provider_protocol_version == protocol_v3.VERSION:
            return _apply_v3(
                connection,
                held=held,
                invoke=invoke,
                info=info,
                bound_bundle=bound_bundle,
                trusted_release=trusted_release,
                executable=executable,
            )
        assert bound_bundle is not None
        _supports_bundle(info, held.target_id.rsplit(":", 1)[-1], held.bundle_format)

        installation.begin(
            connection,
            operation_id,
            observed_target_digest=_target_digest(invoke),
            at=moment(),
        )
        try:
            answer = _object(
                invoke(
                    "apply-bundle",
                    bound_bundle.apply_arguments(
                        held.expected_target_digest, held.provider_plan_digest
                    ),
                )
            )
            bundle_protocol.require_applied(
                answer,
                bound_bundle,
                held.expected_target_digest,
                held.provider_plan_digest,
            )
        except BaseException as error:
            # The call may or may not have taken effect, and nothing here can
            # tell. `partial` is the honest answer and the only safe one.
            installation.interrupted(
                connection,
                operation_id,
                at=moment(),
                reason=f"the provider call did not complete: {type(error).__name__}",
            )
            code = (
                "AI_STP_TIMEOUT_UNCONFIRMED"
                if isinstance(error, (TimeoutError, subprocess.TimeoutExpired))
                else "AI_STP_PARTIAL_OPERATION"
            )
            raise CliFailure(
                code,
                "the provider call did not return verifiable evidence, "
                "so the target may have changed",
                details={"operation_id": operation_id},
                next_actions=[f"install recover --operation {operation_id} --json"],
            ) from error

        reported = str(answer.get("state", ""))
        mapped = _mapped(connection, operation_id, reported)

        # What the provider says happened decides which state is honest. A
        # refused bundle changed nothing, and recording `applied_unverified`
        # for it would claim an effect that never occurred — which is exactly
        # the claim this whole machine exists to avoid making.
        if mapped == installation.STATE_FAILED:
            installation.fail(
                connection, operation_id, at=moment(), reason=f"the provider refused: {reported}"
            )
            return _view(connection, held)
        if mapped == installation.STATE_STALE:
            installation.stale(
                connection,
                operation_id,
                at=moment(),
                reason="the provider locked the target and refused a stale plan",
            )
            return _view(connection, held)
        if mapped == installation.STATE_ROLLED_BACK:
            installation.roll_back(
                connection,
                operation_id,
                at=moment(),
                reason="the provider undid its own change",
            )
            return _view(connection, held)
        if mapped == installation.STATE_PARTIAL:
            installation.interrupted(
                connection, operation_id, at=moment(), reason=f"the provider reported {reported}"
            )
            return _view(connection, held)

        installation.applied(
            connection,
            operation_id,
            at=moment(),
            backup_ref=str(answer.get("backup_ref", "")) or None,
        )
        _verify(
            connection,
            operation_id,
            mapped,
            reported,
            observed_target_digest=_target_digest(invoke),
            plan=held,
            trusted_release=trusted_release,
        )
        return _view(connection, held)

    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(work(connection))


def _apply_v3(
    connection: sqlite3.Connection,
    *,
    held: installation.Plan,
    invoke: conformance.Invoker,
    info: dict[str, JsonValue],
    bound_bundle: bundle_protocol.Binding | None,
    trusted_release: release.ReleaseManifest | None,
    executable: str,
) -> InstallationView:
    capabilities = _v3_capabilities(info, held.target_id.rsplit(":", 1)[-1], held.bundle_format)
    operation = _v3_operation(held.action)
    plan_path = cache.stored_provider_plan(held.provider_plan_digest)
    if plan_path is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the exact approved provider plan artifact is absent or corrupt",
            details={"provider_plan_digest": held.provider_plan_digest},
            next_actions=["install plan --json"],
        )
    provider_plan = operation_v3.load_plan(plan_path, held.provider_plan_digest)
    if provider_plan.effects != held.effects:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the approved provider plan effects differ from the durable operation",
        )
    release_digest = (
        trusted_release.artifact_digest
        if trusted_release is not None
        else release.artifact_identity(Path(executable))[0]
    )
    installation.begin(
        connection,
        held.operation_id,
        observed_target_digest=_target_digest(invoke),
        at=moment(),
    )
    arguments: tuple[str, ...] = (
        "--plan",
        str(plan_path),
        "--plan-digest",
        provider_plan.digest,
        "--provider-release-digest",
        release_digest,
    )
    if bound_bundle is not None:
        arguments = (*arguments, *bound_bundle.common_arguments())
    try:
        answer = _object(invoke("apply-operation", arguments))
        reported = operation_v3.require_applied(answer, plan=provider_plan, bundle=bound_bundle)
    except BaseException as error:
        installation.interrupted(
            connection,
            held.operation_id,
            at=moment(),
            reason=f"the provider call did not complete: {type(error).__name__}",
        )
        code = (
            "AI_STP_TIMEOUT_UNCONFIRMED"
            if isinstance(error, (TimeoutError, subprocess.TimeoutExpired))
            else "AI_STP_PARTIAL_OPERATION"
        )
        raise CliFailure(
            code,
            "the provider call did not return verifiable evidence, so the target may have changed",
            details={"operation_id": held.operation_id},
            next_actions=[f"install recover --operation {held.operation_id} --json"],
        ) from error
    mapped = _mapped(connection, held.operation_id, reported)
    if mapped == installation.STATE_FAILED:
        installation.fail(
            connection,
            held.operation_id,
            at=moment(),
            reason=f"the provider refused: {reported}",
        )
        return _view(connection, held)
    if mapped == installation.STATE_STALE:
        installation.stale(
            connection,
            held.operation_id,
            at=moment(),
            reason="the provider locked the target and refused a stale plan",
        )
        return _view(connection, held)
    if mapped == installation.STATE_ROLLED_BACK:
        installation.roll_back(
            connection,
            held.operation_id,
            at=moment(),
            reason="the provider undid its own change",
        )
        return _view(connection, held)
    if mapped == installation.STATE_PARTIAL:
        installation.interrupted(
            connection,
            held.operation_id,
            at=moment(),
            reason=f"the provider reported {reported}",
        )
        return _view(connection, held)
    installation.applied(
        connection,
        held.operation_id,
        at=moment(),
        backup_ref=str(answer.get("backup_ref", "")) or None,
    )
    status_answer = _object(invoke("status", ()))
    observed = operation_v3.require_verified_status(
        status_answer,
        capabilities=capabilities,
        release_digest=release_digest,
        plan=provider_plan,
        bundle=bound_bundle,
        operation=operation,
    )
    _verify(
        connection,
        held.operation_id,
        mapped,
        reported,
        observed_target_digest=observed,
        plan=held,
        trusted_release=trusted_release,
    )
    return _view(connection, held)


def cancel(parameters: Mapping[str, object]) -> Answer[InstallationView]:
    """Abandon a plan before anything has been applied.

    Refused once applying has begun. Cancelling claims nothing was done, and
    past that point nobody can claim it — so the machine reports the conflict
    rather than recording a comfortable lie.
    """
    operation_id = _operation(parameters)
    with closing(open_registry(configured_path(), create=True)) as connection:
        installation.cancel(
            connection,
            operation_id,
            at=moment(),
            reason=str(parameters.get("reason") or "cancelled by the user"),
        )
        return Answer(_view(connection, installation._require(connection, operation_id)))  # pyright: ignore[reportPrivateUsage]


def status(parameters: Mapping[str, object]) -> Answer[InstallationStatus]:
    """Every operation that stopped without a settled outcome. Changes nothing."""
    del parameters
    registry = configured_path()
    if not registry.exists():
        return Answer(InstallationStatus(stopped=[]))
    with closing(open_readonly(registry)) as connection:
        return Answer(
            InstallationStatus(
                stopped=[_recovery(item) for item in installation.resumable(connection)]
            )
        )


def recover(parameters: Mapping[str, object]) -> Answer[RecoveryView]:
    """What one stopped operation left, and what may be done about it.

    Reports; recovers nothing. `operation.md` forbids an automatic retry of a
    partial operation, and doing the recovery from inside the report would be
    exactly that.
    """
    operation_id = _operation(parameters)
    with closing(open_readonly(configured_path())) as connection:
        return Answer(_recovery(installation.recovery(connection, operation_id)))


def resume(parameters: Mapping[str, object]) -> Answer[InstallationView]:
    """Finish the postcondition check that an interrupted apply never made.

    Not a retry, and deliberately a different command from one. `operation.md`
    forbids repeating a partial operation by itself, but the check it forbids
    repeating is the *effect*; looking at the target and writing down what is
    there is the step that was owed all along and never taken. Nothing here
    sends a bundle.

    An operation left in `applying` passes through `applied_unverified` first.
    That is not a guess that the effect happened — it is the honest name for
    "the provider was called and nobody has looked since", which is exactly the
    situation a killed process leaves behind.

    A provider that does not answer with the success state leaves the operation
    `partial` rather than `failed`: after the call was made, "nothing was done"
    is a claim nobody is in a position to make.
    """
    executable = _executable(parameters)
    operation_id = _operation(parameters)

    def work(connection: sqlite3.Connection) -> InstallationView:
        held = installation._require(connection, operation_id)  # pyright: ignore[reportPrivateUsage]
        # From the journal, not from the plan: the plan records what was going
        # to be done and never moves, and "where did this stop" is a question
        # only the journal can answer.
        current = journal.get(connection, operation_id)
        state = "" if current is None else current.state
        if state not in _UNFINISHED:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "only an operation that stopped before its result was checked can be resumed",
                details={"operation_id": operation_id, "state": state},
                next_actions=[f"install recover --operation {operation_id} --json"],
            )

        trusted_release = _verify_bound_release(connection, held, executable)
        invoke = invocation.provider_invoker(
            executable,
            held.provider_target or held.target_id,
            held.provider_protocol_version,
            unisolated_reason=_unisolated_reason(trusted_release, parameters),
        )
        info = _object(invoke("provider-info", ()))
        _speaks(info, held.provider_protocol_version)
        if held.provider_protocol_version == protocol_v3.VERSION:
            capabilities = _v3_capabilities(
                info,
                held.target_id.rsplit(":", 1)[-1],
                held.bundle_format,
            )
            operation = _v3_operation(held.action)
            capabilities.require(operation)
            plan_path = cache.stored_provider_plan(held.provider_plan_digest)
            if plan_path is None:
                raise CliFailure(
                    "AI_STP_PRECONDITION_FAILED",
                    "the exact approved provider plan artifact is absent or corrupt",
                    details={"provider_plan_digest": held.provider_plan_digest},
                    next_actions=["install plan --json"],
                )
            provider_plan = operation_v3.load_plan(plan_path, held.provider_plan_digest)
            bound_bundle = _bound_bundle_v3(held)
            release_digest = (
                trusted_release.artifact_digest
                if trusted_release is not None
                else release.artifact_identity(Path(executable))[0]
            )
            status_answer = _object(invoke("status", ()))
            recovery_state = str(status_answer.get("state", ""))
            cleanup_state = str(status_answer.get("cleanup_state", ""))
            if recovery_state == "recovery_required" or cleanup_state in {
                "committed_pending",
                "backup_staging_pending",
            }:
                recovered = _object(invoke("recover-operation", ()))
                recovered_digest = str(recovered.get("target_digest", ""))
                if recovered_digest == str(provider_plan.artifact["expected_target_digest"]):
                    installation.roll_back(
                        connection,
                        operation_id,
                        at=moment(),
                        reason="the provider recovered its durable pre-operation target",
                    )
                    return _view(connection, held)
                status_answer = _object(invoke("status", ()))
            if state == installation.STATE_APPLYING:
                installation.applied(connection, operation_id, at=moment())
            try:
                observed = operation_v3.require_verified_status(
                    status_answer,
                    capabilities=capabilities,
                    release_digest=release_digest,
                    plan=provider_plan,
                    bundle=bound_bundle,
                    operation=operation,
                )
            except CliFailure as error:
                installation.interrupted(
                    connection,
                    operation_id,
                    at=moment(),
                    reason=f"the provider v3 postcondition is not proven: {error.code}",
                )
                raise
            _verify(
                connection,
                operation_id,
                protocol.SUCCESS_STATE,
                "verified",
                observed_target_digest=observed,
                plan=held,
                trusted_release=trusted_release,
            )
            return _view(connection, held)
        _supports_bundle(
            info,
            held.target_id.rsplit(":", 1)[-1],
            held.bundle_format,
        )

        if state == installation.STATE_APPLYING:
            installation.applied(connection, operation_id, at=moment())

        answer = _object(invoke("status", ()))
        reported = str(answer.get("state", ""))
        mapped = _mapped(connection, operation_id, reported)
        _verify(
            connection,
            operation_id,
            mapped,
            reported,
            observed_target_digest=str(answer.get("target_digest", "")),
            plan=held,
            trusted_release=trusted_release,
        )
        return _view(connection, held)

    with closing(open_registry(configured_path(), create=True)) as connection:
        return Answer(work(connection))


def _mapped(connection: sqlite3.Connection, operation_id: str, reported: str) -> str:
    """The provider's state as ours, refusing one this build cannot map.

    An unmapped state is recorded as `partial` and then raised. Passing it
    through would put a word nobody defined into the operation log, and the one
    thing that log must not do is claim to know what happened when it does not.
    """
    try:
        return protocol.operation_state(reported) if reported else installation.STATE_PARTIAL
    except KeyError as error:
        installation.interrupted(
            connection,
            operation_id,
            at=moment(),
            reason=f"the provider reported a state with no meaning here: {reported!r}",
        )
        raise CliFailure(
            "AI_STP_INTERNAL",
            "the provider reported a state this build cannot map",
            details={"operation_id": operation_id, "reported": reported},
        ) from error


def _report_installation(connection: sqlite3.Connection, plan: installation.Plan) -> None:
    """Send the consented anonymous ping, once per component, or nothing at all.

    Everything here is best-effort by construction (`REQ-1318`). An installation
    that is verified stays verified whatever this does or fails to do: the
    result is a property of the target, not of a collector, a network or a
    version probe. So the whole body is guarded, and every path out of it is
    "no ping" rather than an error.

    Only `install` and `update` report. A backup, a restore or a removal did not
    put a component anywhere, and the question this answers is what people
    install on.
    """
    try:
        _report_installation_unguarded(connection, plan)
    except Exception:
        # Deliberately everything, and deliberately silent. This runs inside the
        # transaction that settles an operation; an exception escaping here
        # would turn a healthy install into a failed one over analytics.
        return


def _report_installation_unguarded(connection: sqlite3.Connection, plan: installation.Plan) -> None:
    if plan.action not in {"install", "update"}:
        return
    answer = telemetry.consent()
    if not answer.accepted or telemetry.suppressed():
        return
    values = config.effective_config()
    enabled = any(item.path == "telemetry.enabled" and item.value is True for item in values.values)
    if not enabled:
        return
    url = next(
        (str(item.value) for item in values.values if item.path == "telemetry.url"),
        "",
    )
    if not url:
        return

    _, _, harness_id = plan.target_id.partition(":")
    harness_version = _observed_harness_version(harness_id)
    if not harness_version:
        # A version nobody observed is not one to guess at, and a ping missing
        # a declared field is not a ping (`REQ-1317`).
        return

    for component in _installed_components(connection, plan):
        fields = telemetry.ping(
            operating_system=platform.system().lower(),
            harness=harness_id,
            harness_version=harness_version,
            ai_stp_version=cli_version(),
            component_type=component.component_type,
            name=component.name,
            source=component.source,
            identifier=component.identifier,
            version=component.version,
            anon=answer.anon,
        )
        if fields is not None:
            telemetry.send(url, fields)


@dataclass(frozen=True)
class _Installed:
    """One component of the installed setup, named only in public terms."""

    #: One of the eight declared component kinds. Read from `component_type`
    #: rather than `kind`: `kind` is the passport's discriminator and reads
    #: `component` for every one of them, which is a constant rather than an
    #: answer to the question `docs/contracts/cli-telemetry.md` asks.
    component_type: str
    name: str
    source: str
    identifier: str
    version: str


def _installed_components(
    connection: sqlite3.Connection, plan: installation.Plan
) -> tuple[_Installed, ...]:
    """The components this operation put on the target, as far as they are public.

    Anything that cannot be described without describing the machine is left
    out rather than approximated: no name, no kind, or no public source means no
    entry, and therefore no ping for it (`REQ-1317`).
    """
    if not plan.setup_stable_id or not plan.setup_version:
        return ()
    setup = _passport_document(connection, plan.setup_stable_id, plan.setup_version)
    if setup is None:
        return ()
    refs = setup.get("components")
    if not isinstance(refs, list):
        return ()

    found: list[_Installed] = []
    for raw in cast(list[object], refs):
        if not isinstance(raw, dict):
            continue
        ref = cast(dict[str, object], raw)
        stable_id = str(ref.get("stable_id") or "")
        version = str(ref.get("version") or "")
        if not stable_id or not version:
            continue
        document = _passport_document(connection, stable_id, version)
        if document is None:
            continue
        identifier, source = _public_identity(document, stable_id)
        if not identifier:
            continue
        found.append(
            _Installed(
                component_type=str(document.get("component_type") or ""),
                name=str(document.get("name") or ""),
                source=source,
                identifier=identifier,
                version=version,
            )
        )
    return tuple(found)


def _public_identity(document: Mapping[str, object], stable_id: str) -> tuple[str, str]:
    """How this object is publicly named, and by whom.

    A stable id is public only once the object is on the platform. Before that
    the honest public name is the repository it came from, and if there is
    neither, there is nothing to send.
    """
    visibility = str(document.get("visibility") or "")
    if visibility == "public":
        return stable_id, "platform"
    source = document.get("source")
    if isinstance(source, dict):
        repository = str(cast(dict[str, object], source).get("repository") or "")
        if repository.startswith("https://github.com/"):
            return repository, "github"
    return "", ""


def _passport_document(
    connection: sqlite3.Connection, stable_id: str, version: str
) -> Mapping[str, object] | None:
    recorded = versions.held(connection, stable_id, version)
    if recorded is None:
        return None
    revision = revisions.get(connection, recorded.revision_id)
    if revision is None:
        return None
    return cast(Mapping[str, object], revision.envelope.model_dump(mode="json"))


def _observed_harness_version(harness_id: str) -> str:
    detector = next((item for item in harnesses.DETECTORS if item.harness_id == harness_id), None)
    if detector is None:
        return ""
    found = harnesses.detect(detector)
    return found.installations[0].version if found.installations else ""


def _verify(
    connection: sqlite3.Connection,
    operation_id: str,
    mapped: str,
    reported: str,
    *,
    observed_target_digest: str,
    plan: installation.Plan,
    trusted_release: release.ReleaseManifest | None,
) -> None:
    """Turn a checked effect into success, or into the honest other answer.

    The digest is read from the target *after* the effect, not carried over
    from the plan. It is what later tells local drift from an untouched target,
    and a value copied from before the write could only ever say "unchanged".
    """
    at = moment()
    with transaction(connection):
        state = installation.verify(
            connection,
            operation_id,
            postconditions_met=mapped == protocol.SUCCESS_STATE,
            at=at,
            evidence=reported,
            observed_target_digest=observed_target_digest,
        )
        if state == installation.STATE_VERIFIED:
            _report_installation(connection, plan)
        if state == installation.STATE_VERIFIED and trusted_release is not None:
            provider_releases.record_verified(
                connection,
                provider_id=trusted_release.provider_id,
                sequence=trusted_release.sequence,
                artifact_digest=trusted_release.artifact_digest,
                at=at,
            )


def _target_digest(invoke: conformance.Invoker) -> str:
    """What the provider says the target is right now."""
    digest, _authorization = _provider_observation(invoke)
    if not digest:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider does not report a target digest, so a plan cannot be bound to one",
            next_actions=["provider conformance --harness <id> --executable <path> --json"],
        )
    return digest


def _provider_observation(
    invoke: conformance.Invoker,
) -> tuple[str, provider_status.AuthorizationEvidence | None]:
    """Read target identity and optional authorization evidence in one call."""
    answer = _object(invoke("status", ()))
    return str(answer.get("target_digest", "")), provider_status.authorization(answer)


def _speaks(info: dict[str, JsonValue], expected: int) -> None:
    version = info.get("protocol_version")
    if not isinstance(version, int) or version != expected:
        raise CliFailure(
            "AI_STP_SCHEMA_UNSUPPORTED",
            "this provider does not speak the protocol bound to the operation",
            details={"reported": str(version), "expected": str(expected)},
            next_actions=["provider trust --json"],
        )


def _supports_bundle(info: dict[str, JsonValue], harness_id: str, bundle_format: str) -> None:
    """Require the provider to declare the exact harness, actions and bundle format."""
    reported_harness = str(info.get("harness_id", ""))
    if harness_id and reported_harness != harness_id:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider belongs to a different harness",
            details={"expected": harness_id, "reported": reported_harness},
        )
    actions = info.get("supported_actions")
    required = {"status", "validate-bundle", "plan-bundle", "apply-bundle"}
    if not isinstance(actions, list) or not required.issubset(
        {str(item) for item in actions if isinstance(item, str)}
    ):
        raise CliFailure(
            "AI_STP_SCHEMA_UNSUPPORTED",
            "the provider does not declare the complete bundle lifecycle",
        )
    formats = info.get("bundle_formats")
    if bundle_format and (not isinstance(formats, list) or bundle_format not in formats):
        raise CliFailure(
            "AI_STP_SCHEMA_UNSUPPORTED",
            "the provider does not support the exact HarnessBundle format",
            details={"required": bundle_format},
        )
    os_name, architecture = _release_platform().split("/", 1)
    supported_os = info.get("supported_os")
    supported_arch = info.get("supported_arch")
    if not isinstance(supported_os, list) or os_name not in supported_os:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider does not support this operating system",
            details={"required": os_name},
        )
    if not isinstance(supported_arch, list) or architecture not in supported_arch:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider does not support this architecture",
            details={"required": architecture},
        )


def _v3_capabilities(
    info: dict[str, JsonValue], harness_id: str, bundle_format: str
) -> protocol_v3.ProviderCapabilities:
    try:
        capabilities = protocol_v3.parse_capabilities(cast(Mapping[str, object], info))
    except ValueError as error:
        raise CliFailure(
            "AI_STP_SCHEMA_UNSUPPORTED",
            "the provider-info payload does not satisfy protocol v3",
            details={"reason": str(error)},
        ) from error
    if capabilities.harness_id != harness_id:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider belongs to a different harness",
            details={"expected": harness_id, "reported": capabilities.harness_id},
        )
    if bundle_format and bundle_format not in capabilities.projection.bundle_formats:
        raise CliFailure(
            "AI_STP_SCHEMA_UNSUPPORTED",
            "the provider does not support the exact HarnessBundle format",
            details={"required": bundle_format},
        )
    os_name, architecture = _release_platform().split("/", 1)
    if os_name not in capabilities.supported_os:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider does not support this operating system",
            details={"required": os_name},
        )
    if architecture not in capabilities.supported_arch:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider does not support this architecture",
            details={"required": architecture},
        )
    return capabilities


def _v3_profile_accepts(
    capabilities: protocol_v3.ProviderCapabilities, compiled: bundle.Bundle
) -> None:
    conversion = compiled.manifest.get("conversion_report")
    if not isinstance(conversion, dict):
        raise CliFailure("AI_STP_INTERNAL", "the compiled bundle has no conversion report")
    entries = conversion.get("entries")
    if not isinstance(entries, list):
        raise CliFailure("AI_STP_INTERNAL", "the compiled bundle has no conversion entries")
    component_kinds: list[str] = []
    native_surfaces: list[str] = []
    projection_kinds: list[str] = []
    for item in entries:
        if not isinstance(item, dict):
            raise CliFailure("AI_STP_INTERNAL", "the compiled conversion entry is malformed")
        component_kinds.append(str(item.get("component_type", "")))
        native_surfaces.append(str(item.get("native_surface", "")))
        projection_kinds.append(str(item.get("projection_kind", "native_files")))
    try:
        protocol_v3.validate_profile_for_components(capabilities.projection, component_kinds)
    except ValueError as error:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the exact component graph exceeds provider capabilities",
            details={"reason": str(error)},
        ) from error
    try:
        protocol_v3.validate_profile_for_projections(capabilities.projection, projection_kinds)
    except ValueError as error:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the exact native package family exceeds provider capabilities",
            details={"reason": str(error)},
        ) from error
    unsupported = sorted(set(native_surfaces) - set(capabilities.projection.native_namespaces))
    if unsupported:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the exact native projection exceeds provider capabilities",
            details={"native_surfaces": ", ".join(unsupported)},
        )
    if (
        len(compiled.files) > capabilities.projection.max_files
        or len(compiled.archive) > capabilities.projection.max_bytes
    ):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the exact HarnessBundle exceeds provider-declared limits",
        )


#: Actions that bind to a target and a `BackupRef` rather than to a setup graph.
#: Naming a source for these describes something the operation does not use.
_SOURCELESS_ACTIONS: Final[frozenset[str]] = frozenset({"backup", "rollback"})


#: Journal actions whose subject is a program. Named here so the refusal below
#: reads them from one place rather than restating the three.
_PROGRAM_ACTIONS: Final[frozenset[str]] = frozenset(
    {"software_install", "software_update", "software_remove"}
)


def _v3_operation(action: str) -> protocol_v3.Operation:
    mapping = {
        "install": protocol_v3.Operation.INSTALL,
        "update": protocol_v3.Operation.REPLACE,
        "backup": protocol_v3.Operation.BACKUP,
        "remove": protocol_v3.Operation.REMOVE,
        "rollback": protocol_v3.Operation.RESTORE,
    }
    if action in _PROGRAM_ACTIONS:
        # An address, not a break. The journal accepts these because its state
        # machine is the same for either subject; `install` does not perform
        # them because its subject is a setup, and an agent that asked here
        # needs to be told where they are rather than that something failed.
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "that action installs a program, which harness does, not install",
            details={"action": action},
            next_actions=[f"harness {action.removeprefix('software_')} --json"],
        )
    try:
        return mapping[action]
    except KeyError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "that installation action has no provider v3 operation",
            details={"action": action},
        ) from error


def _bound_bundle(plan: installation.Plan) -> bundle_protocol.Binding:
    """Re-open and re-hash the exact cached artifact bound by an approved plan."""
    if plan.schema_version < 5 or not all(
        (
            plan.bundle_format,
            plan.bundle_digest,
            plan.bundle_artifact_digest,
            plan.provider_plan_digest,
        )
    ):
        raise CliFailure(
            "AI_STP_SCHEMA_UNSUPPORTED",
            "this legacy installation plan does not bind exact HarnessBundle bytes",
            next_actions=["install plan --json"],
        )
    path = cache.stored_raw_artifact(plan.bundle_artifact_digest)
    if path is None:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the exact HarnessBundle bytes approved by this plan are not in the verified cache",
            details={"artifact_digest": plan.bundle_artifact_digest},
            next_actions=["install plan --json"],
        )
    return bundle_protocol.binding(
        path,
        bundle_format=plan.bundle_format,
        bundle_digest=plan.bundle_digest,
        artifact_digest=plan.bundle_artifact_digest,
        bundle_size=plan.bundle_size,
    )


def _bound_bundle_v3(plan: installation.Plan) -> bundle_protocol.Binding | None:
    operation = _v3_operation(plan.action)
    if operation not in {protocol_v3.Operation.INSTALL, protocol_v3.Operation.REPLACE}:
        if any(
            (
                plan.bundle_format,
                plan.bundle_digest,
                plan.bundle_artifact_digest,
                plan.bundle_size,
            )
        ):
            raise CliFailure(
                "AI_STP_SCHEMA_UNSUPPORTED",
                "a non-bundle v3 operation unexpectedly binds HarnessBundle bytes",
            )
        return None
    return _bound_bundle(plan)


def _protocol_version(
    parameters: Mapping[str, object], trusted_release: release.ReleaseManifest | None = None
) -> int:
    """The pre-invocation protocol choice, later bound into the plan digest."""
    try:
        selected = parameters.get("protocol-version")
        version = int(
            str(
                selected
                or (
                    protocol.VERSION
                    if trusted_release is None
                    else trusted_release.protocol_version
                )
            )
        )
    except ValueError:
        version = 0
    if version not in {protocol.VERSION, protocol_v2.VERSION, protocol_v3.VERSION}:
        raise CliFailure(
            "AI_STP_SCHEMA_UNSUPPORTED",
            "this build cannot invoke that provider protocol version",
            details={
                "requested": str(parameters.get("protocol-version") or ""),
                "supported": (f"{protocol.VERSION}, {protocol_v2.VERSION}, {protocol_v3.VERSION}"),
            },
        )
    if trusted_release is not None and version != trusted_release.protocol_version:
        raise CliFailure(
            "AI_STP_SCHEMA_UNSUPPORTED",
            "the selected provider protocol differs from the signed release manifest",
            details={
                "selected": str(version),
                "manifest": str(trusted_release.protocol_version),
            },
        )
    return version


def _unisolated_reason(
    trusted_release: _ReleaseEvidence | release.ReleaseManifest | None,
    parameters: Mapping[str, object],
) -> str | None:
    """Why this install may proceed on Windows with nothing denying the network.

    Both answers are things the caller already had to establish: a release
    verified against manifest, policy and exact bytes, or an operator who named
    an unverified provider on purpose. Neither is new authority — this only
    reads which of the two happened. Off Windows it is ignored.
    """
    if trusted_release is not None:
        return "trusted_release"
    if bool(parameters.get("unverified-provider", False)):
        return "explicit_unverified_provider"
    return None


def _release_required(
    parameters: Mapping[str, object],
    protocol_version: int,
    trusted_release: release.ReleaseManifest | None,
) -> None:
    """Protocol v3 installs a signed release, or says out loud that it does not.

    v1 and v2 predate the signed-release line and keep their behaviour. v3 is
    where prepared SetupVersions and provider-owned operations live, so it is
    where an unverified executable would matter most.

    An unverified install stays possible. Refusing it outright would only move
    the same act outside the tool, where nothing records that it happened, and
    the person running a provider they just built is not the threat the pinned
    policy exists for. What changes is that it can no longer happen by
    omission: `unverified-provider` is the difference between a decision and a
    default, and the plan it produces reports `provider_release_trusted` false
    for anybody reading it afterwards.

    The rule governs the mutating path. `install target-status` and `diff`
    spawn an executable the caller named in order to observe, and install
    nothing; `provider-release.md` records that scope rather than leaving it to
    be inferred from which function happens to call this one.
    """
    unverified = bool(parameters.get("unverified-provider", False))
    if unverified and trusted_release is not None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a signed release manifest and unverified-provider contradict each other",
            next_actions=["install plan --provider-manifest <path> --json"],
        )
    if protocol_version != protocol_v3.VERSION or trusted_release is not None or unverified:
        return
    raise CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "protocol v3 installs a signed provider release",
        details={"protocol_version": str(protocol_version)},
        next_actions=[
            "provider fetch --harness <id> --json",
            "install plan --provider-manifest <path> --json",
            "install plan --unverified-provider --json",
        ],
    )


def _trusted_manifest(
    connection: sqlite3.Connection,
    parameters: Mapping[str, object],
    executable: str,
    *,
    recovery_requested: bool,
) -> _ReleaseEvidence:
    """Verify a signed manifest and exact executable before the first spawn."""
    given = str(parameters.get("provider-manifest") or "")
    if not given:
        if recovery_requested:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "provider release recovery requires the exact signed release manifest",
                next_actions=["install plan --provider-manifest <path> --json"],
            )
        return _ReleaseEvidence(None)
    place = Path(given).expanduser()
    if place.is_symlink() or not place.is_file():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no regular provider release manifest sits at that path",
            details={"manifest": redact_home(place)},
        )
    manifest = release.parse_manifest(place.read_text("utf-8"))
    observed_digest, observed_size = release.artifact_identity(Path(executable))
    known_sequence = provider_releases.minimum_sequence(connection, manifest.provider_id)
    if recovery_requested and manifest.sequence >= known_sequence:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "provider release recovery must name an older release than the local floor",
            details={
                "sequence": str(manifest.sequence),
                "known_sequence": str(known_sequence),
            },
        )
    recovery_verified = recovery_requested and provider_releases.was_verified(
        connection,
        provider_id=manifest.provider_id,
        sequence=manifest.sequence,
        artifact_digest=manifest.artifact_digest,
    )
    policy = release.pinned_policy()
    attested = bool(parameters.get("provider-build-attestation", False)) or (
        manifest.repository in policy.build_attestations
    )
    if attested and recovery_requested:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "provider release recovery currently requires signed local history",
        )
    verdict = (
        release.verify_attested(
            manifest,
            policy,
            known_sequence=known_sequence,
            observed_digest=observed_digest,
            observed_size=observed_size,
            platform=_release_platform(),
        )
        if attested
        else release.verify(
            manifest,
            policy,
            known_sequence=known_sequence,
            observed_digest=observed_digest,
            observed_size=observed_size,
            platform=_release_platform(),
            recovery_requested=recovery_requested,
            recovery_to_verified=recovery_verified,
        )
    )
    if not verdict.accepted:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider release does not satisfy the pinned trust policy and exact bytes",
            details={"refusals": ", ".join(item.code for item in verdict.refusals)},
            next_actions=["provider trust --manifest <path> --json"],
        )
    if Path(manifest.entry_point).name != Path(executable).name:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the signed provider entry point does not name this executable",
            details={
                "entry_point": manifest.entry_point,
                "executable": Path(executable).name,
            },
        )
    if not attested:
        return _ReleaseEvidence(manifest, verdict.trust_level)
    rule = policy.build_attestations[manifest.repository]
    given_bundle = str(parameters.get("provider-attestation-bundle") or "")
    bundle = Path(given_bundle).expanduser() if given_bundle else None
    if bundle is not None and (bundle.is_symlink() or not bundle.is_file()):
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no regular provider attestation bundle sits at that path",
            details={"bundle": redact_home(bundle)},
        )
    evidence = build_attestation.verify(
        Path(executable),
        build_attestation.Policy(
            repository=manifest.repository.removeprefix("github.com/"),
            source_commit=manifest.commit,
            signer_workflow=rule.signer_workflow,
            verified_publisher=rule.verified_publisher,
        ),
        bundle=bundle,
    )
    return _ReleaseEvidence(manifest, evidence.trust_level, evidence.document)


def _verify_bound_release(
    connection: sqlite3.Connection,
    plan: installation.Plan,
    executable: str,
) -> release.ReleaseManifest | None:
    """Re-check current policy and exact bytes before an approved effect."""
    manifest = _verify_bound_artifact(plan, executable)
    if manifest is None:
        return None
    digest, size = release.artifact_identity(Path(executable))
    recovery_requested = plan.provider_release_recovery
    recovery_verified = recovery_requested and provider_releases.was_verified(
        connection,
        provider_id=manifest.provider_id,
        sequence=manifest.sequence,
        artifact_digest=manifest.artifact_digest,
    )
    policy = release.pinned_policy()
    attested = plan.provider_release_trust in {"build_attested", "verified_publisher"} and bool(
        plan.provider_release_evidence
    )
    verdict = (
        release.verify_attested(
            manifest,
            policy,
            known_sequence=provider_releases.minimum_sequence(connection, manifest.provider_id),
            observed_digest=digest,
            observed_size=size,
            platform=_release_platform(),
        )
        if attested
        else release.verify(
            manifest,
            policy,
            known_sequence=provider_releases.minimum_sequence(connection, manifest.provider_id),
            observed_digest=digest,
            observed_size=size,
            platform=_release_platform(),
            recovery_requested=recovery_requested,
            recovery_to_verified=recovery_verified,
        )
    )
    if not verdict.accepted:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider release is no longer acceptable before apply",
            details={"refusals": ", ".join(item.code for item in verdict.refusals)},
            next_actions=["provider trust --json"],
        )
    if attested:
        rule = policy.build_attestations[manifest.repository]
        evidence = build_attestation.verify_stored(
            Path(executable),
            build_attestation.Policy(
                repository=manifest.repository.removeprefix("github.com/"),
                source_commit=manifest.commit,
                signer_workflow=rule.signer_workflow,
                verified_publisher=rule.verified_publisher,
            ),
            plan.provider_release_evidence,
        )
        if evidence.trust_level != plan.provider_release_trust:
            raise CliFailure(
                "AI_STP_PRECONDITION_FAILED",
                "the provider release trust level changed after plan approval",
            )
    return manifest


def _verify_bound_artifact(
    plan: installation.Plan, executable: str
) -> release.ReleaseManifest | None:
    """Check the exact artifact bound by a trusted plan without changing policy history."""
    if not plan.provider_release_manifest:
        return None
    manifest = release.parse_manifest(plan.provider_release_manifest)
    digest, size = release.artifact_identity(Path(executable))
    if (
        digest != manifest.artifact_digest
        or size != manifest.artifact_size
        or manifest.provider_version != plan.provider_version
        or manifest.protocol_version != plan.provider_protocol_version
    ):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider artifact no longer matches the release approved in the plan",
            details={"provider_id": manifest.provider_id},
        )
    return manifest


def _release_platform() -> str:
    return release.current_platform()


def _provider_target(parameters: Mapping[str, object], logical: str, version: int) -> str:
    """Resolve the filesystem target required by the v2/v3 isolation boundary."""
    given = str(parameters.get("target") or "")
    if not given:
        if version == protocol.VERSION:
            return logical
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "provider protocol v2/v3 requires an existing absolute target directory",
            next_actions=["install plan --target <directory> --protocol-version 3 --json"],
        )
    place = Path(given).expanduser()
    if place.is_symlink() or not place.is_absolute() or not place.is_dir():
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the provider target must be an existing absolute directory, not a symlink",
            details={"target": redact_home(place)},
        )
    return str(place.resolve())


def _executable(parameters: Mapping[str, object]) -> str:
    given = str(parameters.get("provider") or "")
    if not given:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the provider executable must be named; ai_stp never writes a target itself",
            next_actions=["provider conformance --harness <id> --executable <path> --json"],
        )
    place = Path(given).expanduser()
    try:
        return conformance.resolve_executable(given)
    except FileNotFoundError:
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no provider executable sits at that path",
            details={"provider": redact_home(place)},
        ) from None
    except PermissionError:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "the provider artifact exists but is not executable on this host",
            details={"provider": redact_home(place)},
            next_actions=["provider trust --json"],
        ) from None


def _operation(parameters: Mapping[str, object]) -> str:
    operation_id = str(parameters.get("operation") or "")
    if not operation_id:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the operation must be named",
            next_actions=["install status --json"],
        )
    return operation_id


def _view(connection: sqlite3.Connection, held: installation.Plan) -> InstallationView:
    current = journal.get(connection, held.operation_id)
    requirements = (
        targets.SetupRequirements()
        if not held.setup_stable_id or not held.setup_version
        else targets.setup_requirements(
            connection,
            stable_id=held.setup_stable_id,
            version=held.setup_version,
        )
    )
    return InstallationView(
        operation_id=held.operation_id,
        action=held.action,  # pyright: ignore[reportArgumentType]
        state="planned" if current is None else current.state,
        plan_digest=held.digest,
        target_id=held.target_id,
        expected_target_digest=held.expected_target_digest,
        provider_version=held.provider_version,
        provider_protocol_version=held.provider_protocol_version,
        provider_target=(redact_home(Path(held.provider_target)) if held.provider_target else ""),
        provider_release_trust=held.provider_release_trust,  # pyright: ignore[reportArgumentType]
        provider_release_trusted=held.provider_release_trust != "unverified",
        provider_release_recovery=held.provider_release_recovery,
        bundle_format=held.bundle_format,
        bundle_digest=held.bundle_digest,
        bundle_artifact_digest=held.bundle_artifact_digest,
        bundle_size=held.bundle_size,
        provider_plan_digest=held.provider_plan_digest,
        backup_ref=installation.backup_reference(connection, held.operation_id),
        required_authorization=requirements.requires_authorization,
        effects=list(held.effects),
        managed_paths=_planned_managed_paths(held),
        recovery_action=held.recovery_action,
        expires_at=held.expires_at,
        steps=[
            InstallationStep(
                sequence=item.sequence,
                at=item.at,
                state_before=item.state_before,
                state_after=item.state_after,
                result=item.result,
            )
            for item in installation.events(connection, held.operation_id)
        ],
    )


def _planned_managed_paths(held: installation.Plan) -> list[str]:
    if not held.bundle_artifact_digest:
        return []
    archive = cache.stored_raw_artifact(held.bundle_artifact_digest)
    if archive is None:
        return []
    return sorted(managed_diff.bundle_manifest(archive).expected)


def _recovery(report: installation.Recovery) -> RecoveryView:
    return RecoveryView(
        operation_id=report.operation_id,
        state=report.state,
        effects_recorded=list(report.effects_recorded),
        backup_ref=report.backup_ref,
        next_actions=list(report.next_actions),
    )


def _object(value: JsonValue) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], value) if isinstance(value, dict) else {}


def _plus(at: str, seconds: int) -> str:
    return format_timestamp(parse_timestamp(at) + timedelta(seconds=seconds))


def _project_id(connection: sqlite3.Connection, given: str) -> str:
    """Accept either the project passport's id or the root it was taken from.

    `install plan --project` and every `select --project` take a local project
    root; the four `target` commands documented the passport's stable id. One
    flag name, two vocabularies — and an agent learns the path form first,
    because those are the commands it runs first.

    Nothing refused the wrong one. `survey` looks up `f"{project}:{harness}"`,
    a path matches no row, and the answer came back `not_selected` with an empty
    `installed_stable_id`: a confident, wrong statement about whether a target
    is installed, which is the most consequential thing this command reports.

    Resolved through `project_passport.stable_id_for`, the same owner
    `context_for_project` uses, so the two forms cannot drift apart. A value
    that names no known root is passed through unchanged: it is either an id or
    something that will not match, and both were already true before.
    """
    if not given or given.startswith("project_"):
        return given
    candidate = Path(given).expanduser()
    if not candidate.is_dir():
        return given
    found = project_passport.stable_id_for(connection, candidate.resolve())
    return given if found is None else found


def target_status(parameters: Mapping[str, object]) -> Answer[TargetSurvey]:
    """The daily state of one pair. Reads, and changes nothing (`#177`).

    Every applicable state comes back, not the first one found: a pair can be
    waiting to install *and* missing a variable, and one answer would send
    somebody to fix a thing and meet the other immediately after.

    `catalog_drift` is reported and never acted on. `#177` says there is no
    automatic update, so wanting the newer version means planning it.
    """
    project_id = _required(parameters, "project")
    harness = _required(parameters, "harness")
    additional_required_env = _required_env(parameters)
    registry = configured_path()
    if not registry.exists():
        return Answer(_survey(targets.Survey(project_id=project_id, harness_id=harness)))
    observed = ""
    authorization_evidence = None
    if parameters.get("provider"):
        version = _protocol_version(parameters)
        logical = f"{project_id}:{harness}"
        target = _provider_target(parameters, logical, version)
        invoke = invocation.provider_invoker(_executable(parameters), target, version)
        observed, authorization_evidence = _provider_observation(invoke)

    with closing(open_readonly(registry)) as connection:
        found = targets.survey(
            connection,
            project_id=_project_id(connection, project_id),
            harness_id=harness,
            observed_target_digest=observed,
            present_env=frozenset(os.environ),
            additional_required_env=additional_required_env,
            authorization_evidence=authorization_evidence,
            catalog_version=str(parameters.get("catalog-version") or ""),
        )
        return Answer(_survey(found))


def target_diff(parameters: Mapping[str, object]) -> Answer[TargetDiff]:
    """What installing the selected version would change. Changes nothing itself.

    Drift is named as drift rather than as work to do: `REQ-818` forbids fixing
    it automatically, and something moved that target for a reason nobody here
    knows.
    """
    project_id = _required(parameters, "project")
    harness = _required(parameters, "harness")
    additional_required_env = _required_env(parameters)
    registry = configured_path()
    if not registry.exists():
        return Answer(
            TargetDiff(
                project_id=project_id,
                harness_id=harness,  # pyright: ignore[reportArgumentType]
                changes=[],
                managed_detail="not_applicable",
            )
        )
    observed = ""
    authorization_evidence = None
    if parameters.get("provider"):
        version = _protocol_version(parameters)
        logical = f"{project_id}:{harness}"
        target = _provider_target(parameters, logical, version)
        invoke = invocation.provider_invoker(_executable(parameters), target, version)
        observed, authorization_evidence = _provider_observation(invoke)

    with closing(open_readonly(registry)) as connection:
        found = targets.survey(
            connection,
            project_id=_project_id(connection, project_id),
            harness_id=harness,
            observed_target_digest=observed,
            present_env=frozenset(os.environ),
            additional_required_env=additional_required_env,
            authorization_evidence=authorization_evidence,
            catalog_version=str(parameters.get("catalog-version") or ""),
        )
        managed_detail = "not_applicable"
        managed_changes: list[ManagedPathChange] = []
        if targets.STATE_LOCAL_DRIFT in found.states:
            managed_detail, managed_changes = _managed_target_changes(
                connection, project_id=project_id, harness_id=harness
            )
        return Answer(
            TargetDiff(
                project_id=project_id,
                harness_id=harness,  # pyright: ignore[reportArgumentType]
                changes=list(targets.pending_changes(found)),
                managed_detail=managed_detail,  # pyright: ignore[reportArgumentType]
                managed_changes=managed_changes,
            )
        )


def _managed_target_changes(
    connection: sqlite3.Connection, *, project_id: str, harness_id: str
) -> tuple[str, list[ManagedPathChange]]:
    history = targets.verified(connection, project_id=project_id, harness_id=harness_id)
    if not history:
        return "unavailable", []
    held = installation.plan(connection, history[-1].operation_id)
    if not held.bundle_artifact_digest or not held.provider_target:
        return "unavailable", []
    archive = cache.stored_raw_artifact(held.bundle_artifact_digest)
    if archive is None:
        return "unavailable", []
    manifest = managed_diff.bundle_manifest(archive)
    changes = managed_diff.compare(Path(held.provider_target), manifest)
    return "available", [
        ManagedPathChange(
            code=item.code,  # pyright: ignore[reportArgumentType]
            path=item.path,
            expected_digest=item.expected_digest,
            observed_digest=item.observed_digest,
        )
        for item in changes
    ]


def target_rollback(parameters: Mapping[str, object]) -> Answer[RollbackTarget]:
    """Name the exact previous verified version. Rolls nothing back itself.

    A rollback is an ordinary plan with an ordinary approval, so this answers
    *what* to go back to and stops. Doing it from here would be an automatic
    change to a target, which is the one thing this whole surface refuses.
    """
    project_id = _required(parameters, "project")
    harness = _required(parameters, "harness")
    registry = configured_path()
    if not registry.exists():
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "this target has no verified version to roll back",
            next_actions=["select propose --harness <id> --json"],
        )
    with closing(open_readonly(registry)) as connection:
        previous = targets.rollback_target(
            connection, project_id=_project_id(connection, project_id), harness_id=harness
        )
        return Answer(
            RollbackTarget(
                project_id=project_id,
                harness_id=harness,  # pyright: ignore[reportArgumentType]
                setup_stable_id=previous.setup_stable_id,
                setup_version=previous.setup_version,
                verified_at=previous.at,
                operation_id=previous.operation_id,
            )
        )


def target_backups(parameters: Mapping[str, object]) -> Answer[TargetBackups]:
    """Every provider-owned copy this pair can restore from. Restores nothing.

    The read half `SPEC-012` assumed and nothing answered. A `BackupRef` used to
    appear exactly once, in the answer to `install apply`, so an agent that did
    not keep that stdout could not name the copy again — and the path from
    "I took a backup" to "restore it" was reproducible only by remembering.

    Deliberately not a column on `target rollback`. That command names the
    previous verified *version*, and a reference to a copy is not the identity
    of a setup (`REQ-814`); answering both from one place would blur exactly the
    distinction the two requirements exist to keep.
    """
    project_id = _required(parameters, "project")
    harness = _required(parameters, "harness")
    registry = configured_path()
    if not registry.exists():
        return Answer(
            TargetBackups(
                project_id=project_id,
                harness_id=harness,  # pyright: ignore[reportArgumentType]
            )
        )
    with closing(open_readonly(registry)) as connection:
        found = targets.backups(
            connection, project_id=_project_id(connection, project_id), harness_id=harness
        )
        return Answer(
            TargetBackups(
                project_id=project_id,
                harness_id=harness,  # pyright: ignore[reportArgumentType]
                backups=[
                    TargetBackup(
                        backup_ref=item.backup_ref,
                        operation_id=item.operation_id,
                        setup_stable_id=item.setup_stable_id,
                        setup_version=item.setup_version,
                        provider_target=item.provider_target,
                        created_at=item.created_at,
                    )
                    for item in found
                ],
            )
        )


def _survey(found: targets.Survey) -> TargetSurvey:
    return TargetSurvey(
        project_id=found.project_id,
        harness_id=found.harness_id,  # pyright: ignore[reportArgumentType]
        states=list(found.states),  # pyright: ignore[reportArgumentType]
        selected_stable_id=found.selected_stable_id,
        selected_version=found.selected_version,
        installed_stable_id=found.installed_stable_id,
        installed_version=found.installed_version,
        verified_target_digest=found.verified_target_digest,
        observed_target_digest=found.observed_target_digest,
        missing_env=list(found.missing_env),
        pending_authorization=found.pending_authorization,
        catalog_version=found.catalog_version,
    )


def _required(parameters: Mapping[str, object], name: str) -> str:
    given = str(parameters.get(name) or "")
    if not given:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            f"the {name} must be named",
            next_actions=["select session --harness <id> --json"],
        )
    return given


def _required_env(parameters: Mapping[str, object]) -> tuple[str, ...]:
    """Mandatory variable *names* the caller says this target needs.

    Names arrive from the caller rather than being read out of a passport here:
    the passport is the composition's and this command is about one target, and
    a value is never read either way (`REQ-1108`).
    """
    given: object = parameters.get("requires-env")
    if given is None:
        return ()
    items: tuple[object, ...] = (
        tuple(cast(list[object] | tuple[object, ...], given))
        if isinstance(given, list | tuple)
        else (given,)
    )

    names: list[str] = []
    for item in items:
        if not isinstance(item, str) or _ENV_NAME.fullmatch(item) is None:
            # Never echo the rejected item: NAME=value is precisely the hostile
            # case, and the suffix may be a real secret (`REQ-1108`).
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "required environment entries must be uppercase variable names, never NAME=value",
                next_actions=["help --agent --json"],
            )
        if item not in names:
            names.append(item)
    return tuple(names)
