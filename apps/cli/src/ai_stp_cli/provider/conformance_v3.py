"""Safe executable conformance for capability-negotiated provider protocol v3."""

from __future__ import annotations

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
        arguments = (
            "--operation",
            operation.value,
            "--provider-release-digest",
            release_digest,
            "--operation-id",
            operation_id,
            "--expires-at",
            expiry,
            *corpus.valid.common_arguments(),
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
    {protocol_v3.UnsupportedReason.OPERATION.value}
)


def _undeclared_operation(
    invoke: conformance.Invoker,
    capabilities: protocol_v3.ProviderCapabilities,
    arguments: tuple[str, ...],
) -> conformance.Case:
    """Ask for an operation the provider never declared and require the refusal.

    This is the only capability rejection the pure surface can drive. The others
    -- `projection_profile_mismatch`, `unsupported_platform` and
    `unsupported_architecture` -- describe a disagreement between what the
    caller expects and what the provider is, and v3 argv carries no platform,
    architecture or projection profile from the caller. There is nothing to
    disagree with, so nothing here can provoke them.
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


def _object(value: JsonValue) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], value) if isinstance(value, dict) else {}
