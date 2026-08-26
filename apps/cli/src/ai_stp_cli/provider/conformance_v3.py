"""Safe executable conformance for capability-negotiated provider protocol v3."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import composition
from ai_stp_cli.provider import (
    bundle_corpus,
    bundle_protocol,
    conformance,
    operation_v3,
    protocol_v3,
)
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import is_digest


def run(
    invoke: conformance.Invoker,
    *,
    harness_id: str,
    target: Path,
) -> conformance.Report:
    """Exercise only pure v3 commands against an explicitly disposable target."""
    raw_info = _object(invoke("provider-info", ()))
    cases: list[conformance.Case] = []
    try:
        capabilities = protocol_v3.parse_capabilities(cast(dict[str, object], raw_info))
    except ValueError as error:
        reported_version = raw_info.get("protocol_version")
        cases.append(conformance.Case("provider_info_v3_closed", False, str(error)))
        return conformance.Report(
            harness_id=str(raw_info.get("harness_id", "")),
            protocol_version=(reported_version if isinstance(reported_version, int) else 0),
            cases=tuple(cases),
        )
    cases.append(
        conformance.Case(
            "provider_info_v3_closed",
            True,
            "provider-info satisfies the exact v3 capability schema and digest",
        )
    )
    matches = capabilities.harness_id == harness_id
    cases.append(
        conformance.Case(
            "harness_matches",
            matches,
            f"reports {capabilities.harness_id!r}"
            + ("" if matches else f", expected {harness_id!r}"),
        )
    )
    route = _literal_route(capabilities)
    cases.append(
        conformance.Case(
            "declared_native_route_is_compilable",
            route is not None,
            "one declared component route matches the canonical compiler"
            if route is not None
            else "no declared component kind/native namespace pair matches the compiler",
        )
    )
    first_status = _object(invoke("status", ()))
    second_status = _object(invoke("status", ()))
    state = str(first_status.get("state", ""))
    target_digest = str(first_status.get("target_digest", ""))
    status_valid = (
        state in {"missing", "unmanaged", "managed"}
        and is_digest(target_digest)
        and first_status == second_status
    )
    cases.append(
        conformance.Case(
            "status_is_exact_and_repeatable",
            status_valid,
            f"reports {state!r} with a canonical digest"
            if status_valid
            else "status is not a stable exact v3 target observation",
        )
    )
    cases.append(_populated_target(target, state))
    if route is None or not status_valid:
        return conformance.Report(
            harness_id=capabilities.harness_id,
            protocol_version=protocol_v3.VERSION,
            cases=tuple(cases),
        )

    component_kind, native_surface, target_path = route
    with bundle_corpus.materialized_v3(
        harness_id=harness_id,
        component_kind=component_kind,
        native_surface=native_surface,
        target_path=target_path,
    ) as corpus:
        valid_answer = _object(invoke("validate-bundle", corpus.valid.common_arguments()))
        try:
            bundle_protocol.require_validated(valid_answer, corpus.valid)
        except CliFailure as error:
            cases.append(conformance.Case("valid_v3_bundle_accepted", False, error.message))
        else:
            cases.append(
                conformance.Case(
                    "valid_v3_bundle_accepted",
                    True,
                    "accepts an exact compiler/provider-native literal",
                )
            )
        cases.extend(_rejections(invoke, corpus))
        operation = (
            protocol_v3.Operation.REPLACE if state == "managed" else protocol_v3.Operation.INSTALL
        )
        expiry = (
            (datetime.now(UTC) + timedelta(minutes=10))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        release_digest = "sha256:" + "d" * 64
        operation_id = "operation_provider_conformance_v3"
        arguments = operation_v3.plan_arguments(
            operation=operation,
            release_digest=release_digest,
            operation_id=operation_id,
            expires_at=expiry,
            bundle=corpus.valid,
        )
        first_plan = _object(invoke("plan-operation", arguments))
        second_plan = _object(invoke("plan-operation", arguments))
        try:
            parsed = operation_v3.require_plan(
                first_plan,
                capabilities=capabilities,
                release_digest=release_digest,
                operation_id=operation_id,
                operation=operation,
                target=target,
                expected_target_digest=target_digest,
                bundle=corpus.valid,
                backup_ref=None,
                permission_profile=None,
                expires_at=expiry,
            )
        except CliFailure as error:
            cases.append(conformance.Case("pure_v3_plan_is_exact", False, error.message))
        else:
            cases.append(
                conformance.Case(
                    "pure_v3_plan_is_exact",
                    first_plan == second_plan,
                    f"plan {parsed.digest} is exact and repeatable"
                    if first_plan == second_plan
                    else "the same pure plan request returned different bytes",
                )
            )
        cases.append(_undeclared_operation(invoke, capabilities, arguments))
        cases.append(_undeclared_permission_profile(invoke, capabilities, arguments))
        cases.append(_declared_software_artifact(invoke, capabilities, arguments))
        repeated_valid = _object(invoke("validate-bundle", corpus.valid.common_arguments()))
        cases.append(
            conformance.Case(
                "pure_v3_validation_is_repeatable",
                valid_answer == repeated_valid,
                "the same exact bundle validates identically"
                if valid_answer == repeated_valid
                else "validation changed on a second read",
            )
        )
    return conformance.Report(
        harness_id=capabilities.harness_id,
        protocol_version=protocol_v3.VERSION,
        cases=tuple(cases),
    )


#: Capability refusals this run drives, as opposed to the bundle refusals the
#: corpus drives. Named here so the coverage guard reads one source instead of
#: keeping a second list that agrees until somebody adds a case.
DRIVEN_CAPABILITY_REJECTIONS: Final[frozenset[str]] = frozenset(
    {
        protocol_v3.UnsupportedReason.OPERATION.value,
        protocol_v3.UnsupportedReason.PERMISSION_PROFILE.value,
    }
)


def _populated_target(target: Path, state: str) -> conformance.Case:
    """What an empty target cannot tell you about a provider.

    The run is given a disposable target and never writes to it, so whatever the
    operator points at is what gets exercised. Pointed at an empty directory —
    which is the convenient thing to do — two classes of defect are invisible by
    construction: a provider that mishandles material already in the home, and
    a provider that refuses a symbolic link sitting outside every namespace it
    declared. Both were found on live homes by a provider implementation that
    passed every case here.

    So the run says which it got. A provider reported as conforming against an
    empty directory has not been shown to survive a real installation, and that
    sentence is worth more than a silently narrower run.
    """
    try:
        entries = sorted(item.name for item in target.iterdir())
    except OSError as error:  # pragma: no cover - the caller already checked it
        return conformance.Case("target_was_populated", False, str(error))
    if not entries:
        return conformance.Case(
            "target_was_populated",
            True,
            "target was empty, so nothing here exercises a provider against "
            "existing material; point at a disposable copy of a real home to cover that",
        )
    unmanaged = state in {"unmanaged", "managed"}
    return conformance.Case(
        "target_was_populated",
        unmanaged,
        f"target held {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} "
        f"and status reported {state!r}"
        if unmanaged
        else f"target was not empty and status still reported {state!r}",
    )


def _undeclared_operation(
    invoke: conformance.Invoker,
    capabilities: protocol_v3.ProviderCapabilities,
    arguments: tuple[str, ...],
) -> conformance.Case:
    """Ask for an operation the provider never declared and require the refusal.

    Platform, architecture and projection-profile disagreements still cannot be
    driven here: v3 argv does not carry those expectations from the caller.
    """
    undeclared = sorted(
        operation.value
        for operation in protocol_v3.Operation
        if operation not in capabilities.operations
    )
    if not undeclared:
        return conformance.Case(
            "refuses_undeclared_operation",
            True,
            "provider declares every operation, so none can be asked for undeclared",
        )
    asked = undeclared[0]
    replaced = list(arguments)
    replaced[replaced.index("--operation") + 1] = asked
    answer = _object(invoke("plan-operation", tuple(replaced)))
    reason = answer.get("reason")
    refused = answer.get("rejected") is True and reason == protocol_v3.UnsupportedReason.OPERATION
    return conformance.Case(
        "refuses_undeclared_operation",
        refused,
        f"refuses {asked!r} with {reason!r}"
        if refused
        else f"asked for undeclared {asked!r} and received {answer.get('reason', answer)!r}",
    )


#: Every field an offline plan must carry before a consumer may fetch bytes.
#: `sha256` and `byte_length` are what the applier checks before it writes;
#: `platform` is what makes the choice reproducible on another machine;
#: `entry_point` is the path the provider will expose under `--prefix`, and it
#: is not a path inside the archive — the archive's own shape never reaches the
#: wire, which is what lets a harness whose archive has no wrapper directory
#: work without a special case.
SOFTWARE_ARTIFACT_FIELDS: Final[tuple[str, ...]] = (
    "platform",
    "url",
    "sha256",
    "byte_length",
    "entry_point",
)


def _declared_software_artifact(
    invoke: conformance.Invoker,
    capabilities: protocol_v3.ProviderCapabilities,
    arguments: tuple[str, ...],
) -> conformance.Case:
    """The program lifecycle must match what the provider said about it.

    Declared, the plan must name exact bytes without the network. The consumer
    downloads and the provider never does: `download` is not one of the kit's
    commands, and both commands that could have carried it are
    `network_requirement: none`. So the only thing standing between a plan and
    a verified install is whether the plan already said which bytes it meant. A
    provider that declares `software_install` and answers without
    `software_artifacts` has moved that decision to download time, where no plan
    digest covers it.

    Undeclared, it must refuse with `unsupported_operation`. That branch is an
    assertion and not a skip on purpose. Scoring "did not declare it" as passed
    is how a case becomes permanent green that reads as coverage: it would stay
    green through any future argv mistake, and green is exactly what it reported
    for the one provider whose lifecycle does not exist while every provider
    that has one went red.

    Both branches send a *well formed* request, which is what makes either
    refusal mean anything. A program lives under `--prefix`, not under
    `--target`; sending the core operation's argv unchanged asks a provider to
    install a program without saying where, and its refusal then says the
    request was malformed rather than anything about the capability.
    """
    name = "software_lifecycle_matches_its_declaration"
    declared = protocol_v3.Operation.SOFTWARE_INSTALL in capabilities.operations
    # Never created and never written: `plan-operation` is pure, and the
    # provider accepts a `--prefix` that does not exist yet. A directory made
    # here would be one this run has to remove again.
    prefix = Path(tempfile.gettempdir()).resolve() / "ai-stp-conformance-prefix"
    request = operation_v3.plan_arguments(
        operation=protocol_v3.Operation.SOFTWARE_INSTALL,
        release_digest=_argument(arguments, "--provider-release-digest"),
        operation_id=_argument(arguments, "--operation-id"),
        expires_at=_argument(arguments, "--expires-at"),
        prefix=prefix,
    )
    answer = _object(invoke("plan-operation", request))
    reason = answer.get("reason")
    if not declared:
        refused = (
            answer.get("rejected") is True
            and reason == protocol_v3.UnsupportedReason.OPERATION.value
        )
        return conformance.Case(
            name,
            refused,
            f"does not declare software_install and refuses it with {reason!r}"
            if refused
            else "does not declare software_install and answered a well-formed request with "
            f"{reason or answer.get('state')!r} instead of unsupported_operation",
        )
    if answer.get("rejected") is True:
        return conformance.Case(
            name,
            False,
            f"declares software_install and refused a well-formed plan with {reason!r}",
        )
    plan = answer.get("plan")
    artifacts = plan.get("software_artifacts") if isinstance(plan, dict) else None
    if not isinstance(artifacts, list) or not artifacts:
        return conformance.Case(
            name,
            False,
            "planned software_install without naming any software_artifacts",
        )
    for index, entry in enumerate(artifacts):
        if not isinstance(entry, dict):
            return conformance.Case(name, False, f"software_artifacts[{index}] is not an object")
        missing = [field for field in SOFTWARE_ARTIFACT_FIELDS if entry.get(field) is None]
        if missing:
            return conformance.Case(
                name,
                False,
                f"software_artifacts[{index}] omits {', '.join(missing)}",
            )
    return conformance.Case(
        name,
        True,
        f"names {len(artifacts)} artifact(s) with complete identity before any fetch",
    )


def _undeclared_permission_profile(
    invoke: conformance.Invoker,
    capabilities: protocol_v3.ProviderCapabilities,
    arguments: tuple[str, ...],
) -> conformance.Case:
    """Ask for a permission profile the provider never declared.

    `--permission-profile` is already on the wire. Naming a profile outside the
    closed `permission_profiles` list is not `unsupported_operation` — the
    operation is supported — and it is not a projection-profile mismatch.
    """
    asked = "ai-stp-conformance-unknown-profile"
    if asked in capabilities.permission_profiles:
        return conformance.Case(
            "refuses_undeclared_permission_profile",
            True,
            "provider already declares the conformance sentinel profile",
        )
    answer = _object(
        invoke("plan-operation", (*arguments, "--permission-profile", asked)),
    )
    reason = answer.get("reason")
    refused = (
        answer.get("rejected") is True
        and reason == protocol_v3.UnsupportedReason.PERMISSION_PROFILE.value
    )
    return conformance.Case(
        "refuses_undeclared_permission_profile",
        refused,
        f"refuses {asked!r} with {reason!r}"
        if refused
        else f"asked for undeclared profile {asked!r} and received "
        f"{answer.get('reason', answer)!r}",
    )


def _literal_route(
    capabilities: protocol_v3.ProviderCapabilities,
) -> tuple[str, str, str] | None:
    for kind in sorted(capabilities.projection.component_kinds, key=lambda item: item.value):
        rule = composition.rule_for(kind.value, capabilities.harness_id)
        if rule is None or rule.relative not in capabilities.projection.native_namespaces:
            continue
        target_path = (
            rule.relative if rule.shape == "file" else f"{rule.relative}/provider-conformance.md"
        )
        return kind.value, rule.relative, target_path
    return None


def _rejections(
    invoke: conformance.Invoker,
    corpus: bundle_corpus.Corpus,
) -> list[conformance.Case]:
    cases: list[conformance.Case] = []
    for malicious in corpus.malicious:
        answer = _object(invoke("validate-bundle", malicious.binding.common_arguments()))
        try:
            bundle_protocol.require_rejected(answer, malicious.binding, malicious.refusal)
        except CliFailure:
            passed = False
        else:
            passed = malicious.refusal in protocol_v3.BUNDLE_REJECTIONS
        cases.append(
            conformance.Case(
                f"rejects_v3_{malicious.name}",
                passed,
                f"returns {answer.get('reason')!r}"
                if passed
                else (
                    "did not return the exact v3 refusal and artifact binding: "
                    f"expected {malicious.refusal!r}, received {answer.get('reason')!r}"
                ),
            )
        )
    return cases


def _argument(arguments: tuple[str, ...], flag: str) -> str:
    """Read one value out of an argv the run already built."""
    return arguments[arguments.index(flag) + 1]


def _object(value: JsonValue) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], value) if isinstance(value, dict) else {}
