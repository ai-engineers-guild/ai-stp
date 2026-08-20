"""Executable conformance checks for provider protocol v2 network phases."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import bundle_corpus, bundle_protocol, conformance, protocol, protocol_v2
from ai_stp_foundation.canonical import JsonValue


class PhaseInvocation(Protocol):
    """The payload and consumer decision returned by one exact phase."""

    @property
    def payload(self) -> JsonValue: ...

    @property
    def network(self) -> protocol_v2.NetworkDecision: ...


class PhaseInvoker(Protocol):
    """The only v2 provider door: command, phase, arguments, observed result."""

    def __call__(
        self,
        command: str,
        phase: protocol_v2.ActionPhase,
        arguments: Sequence[str],
    ) -> PhaseInvocation: ...


def run(invoke: PhaseInvoker, *, harness_id: str) -> conformance.Report:
    """Run the closed v2 declaration, phase and v1-compatible safety corpus."""
    with bundle_corpus.materialized(
        protocol_version=protocol_v2.VERSION, harness_id=harness_id
    ) as corpus:
        info_result = invoke("provider-info", protocol_v2.ActionPhase.EXECUTE, ())
        info = _object(info_result.payload)
        cases: list[conformance.Case] = [
            _fields_present(info),
            _version_spoken(info),
            _harness_matches(info, harness_id),
            _actions_exact(info),
            _network_declaration_exact(info),
            _decision_exact(info_result, "provider-info", protocol_v2.ActionPhase.EXECUTE),
            _safe_actions_answer(invoke),
            _valid_bundle_accepted(invoke, corpus.valid),
            _valid_bundle_planned(invoke, corpus.valid),
        ]
        cases.extend(_rejections(invoke, corpus))
        cases.append(_state_mapped(invoke))
        cases.append(_reads_repeat(invoke, corpus.valid))
    version = info.get("protocol_version")
    return conformance.Report(
        harness_id=str(info.get("harness_id", "")),
        protocol_version=version if isinstance(version, int) else 0,
        cases=tuple(cases),
    )


def _fields_present(info: dict[str, JsonValue]) -> conformance.Case:
    required = (*protocol.INFO_FIELDS, "action_network")
    missing = [name for name in required if name not in info]
    return conformance.Case(
        "provider_info_v2_complete",
        not missing,
        "every v2 field is answered" if not missing else f"missing: {', '.join(missing)}",
    )


def _version_spoken(info: dict[str, JsonValue]) -> conformance.Case:
    version = info.get("protocol_version")
    matches = version == protocol_v2.VERSION
    return conformance.Case(
        "protocol_version_v2_spoken",
        matches,
        "speaks v2" if matches else f"announces {version!r}, expected 2",
    )


def _harness_matches(info: dict[str, JsonValue], harness_id: str) -> conformance.Case:
    reported = str(info.get("harness_id", ""))
    matches = reported == harness_id
    return conformance.Case(
        "harness_matches",
        matches,
        f"reports {reported!r}" + ("" if matches else f", expected {harness_id!r}"),
    )


def _actions_exact(info: dict[str, JsonValue]) -> conformance.Case:
    declared = {str(item) for item in _list(info.get("supported_actions"))}
    expected = set(protocol_v2.COMMANDS)
    missing = sorted(expected - declared)
    invented = sorted(declared - expected)
    matches = not missing and not invented
    detail = "declares every and only v2 command"
    if not matches:
        detail = f"missing={missing}, invented={invented}"
    return conformance.Case("actions_exact_v2", matches, detail)


def _network_declaration_exact(info: dict[str, JsonValue]) -> conformance.Case:
    declaration = info.get("action_network")
    expected = cast(JsonValue, protocol_v2.wire_policy())
    matches = declaration == expected
    return conformance.Case(
        "action_network_exact",
        matches,
        "declares the closed command/phase policy"
        if matches
        else "action_network differs from the closed v2 policy",
    )


def _decision_exact(
    result: PhaseInvocation,
    command: str,
    phase: protocol_v2.ActionPhase,
) -> conformance.Case:
    expected = protocol_v2.phase_policy(command, phase)
    decision = result.network
    matches = (
        decision.command == command
        and decision.phase is phase
        and decision.requirement is expected.requirement
        and decision.allows_execution
    )
    return conformance.Case(
        f"network_decision_{command}_{phase.value}",
        matches,
        f"reports {decision.requirement.value}/{decision.enforcement.value}"
        if matches
        else "consumer decision does not match the invoked phase",
    )


def _safe_actions_answer(invoke: PhaseInvoker) -> conformance.Case:
    """Probe only no-effect commands; mutating phases belong to disposable E2E."""
    silent: list[str] = []
    wrong_decisions: list[str] = []
    arguments: dict[str, tuple[str, ...]] = {
        "provider-info": (),
        "software-status": (),
        "software-plan": (),
        "status": (),
    }
    for command in sorted(arguments):
        policies = protocol_v2.ACTION_NETWORK[command]
        for policy in policies:
            result = invoke(command, policy.phase, arguments[command])
            answer = _object(result.payload)
            label = f"{command}:{policy.phase.value}"
            if answer.get("unsupported") is True or not answer:
                silent.append(label)
            if not _decision_exact(result, command, policy.phase).passed:
                wrong_decisions.append(label)
    matches = not silent and not wrong_decisions
    return conformance.Case(
        "safe_v2_phases_answer",
        matches,
        "every declared phase answers under its exact decision"
        if matches
        else f"silent={silent}, wrong_decisions={wrong_decisions}",
    )


def _valid_bundle_accepted(
    invoke: PhaseInvoker, artifact: bundle_protocol.Binding
) -> conformance.Case:
    result = invoke("validate-bundle", protocol_v2.ActionPhase.EXECUTE, artifact.common_arguments())
    try:
        bundle_protocol.require_validated(_object(result.payload), artifact)
    except CliFailure as error:
        return conformance.Case("valid_literal_bundle_accepted", False, error.message)
    return conformance.Case(
        "valid_literal_bundle_accepted", True, "accepts and echoes the exact ZIP binding"
    )


def _valid_bundle_planned(
    invoke: PhaseInvoker, artifact: bundle_protocol.Binding
) -> conformance.Case:
    result = invoke(
        "plan-bundle",
        protocol_v2.ActionPhase.EXECUTE,
        artifact.plan_arguments(_CONFORMANCE_TARGET_DIGEST),
    )
    try:
        bundle_protocol.require_plan(_object(result.payload), artifact, _CONFORMANCE_TARGET_DIGEST)
    except CliFailure as error:
        return conformance.Case("valid_literal_bundle_planned", False, error.message)
    return conformance.Case(
        "valid_literal_bundle_planned", True, "plans and echoes the exact ZIP binding"
    )


def _rejections(invoke: PhaseInvoker, corpus: bundle_corpus.Corpus) -> list[conformance.Case]:
    cases: list[conformance.Case] = []
    for malicious in corpus.malicious:
        result = invoke(
            "validate-bundle",
            protocol_v2.ActionPhase.EXECUTE,
            malicious.binding.common_arguments(),
        )
        answer = _object(result.payload)
        reason = str(answer.get("reason", ""))
        try:
            bundle_protocol.require_rejected(answer, malicious.binding, malicious.refusal)
        except CliFailure:
            passed = False
        else:
            passed = True
        cases.append(
            conformance.Case(
                f"rejects_{malicious.name}",
                passed,
                f"rejected exact artifact as {reason!r}"
                if passed
                else "did not return the exact artifact binding and required refusal",
            )
        )
    return cases


def _state_mapped(invoke: PhaseInvoker) -> conformance.Case:
    result = invoke("status", protocol_v2.ActionPhase.EXECUTE, ())
    answer = _object(result.payload)
    reported = str(answer.get("state", ""))
    try:
        protocol.operation_state(reported)
    except KeyError:
        return conformance.Case(
            "state_is_mapped", False, f"reports {reported!r}, which maps to nothing"
        )
    return conformance.Case("state_is_mapped", True, f"reports {reported!r}")


def _reads_repeat(invoke: PhaseInvoker, artifact: bundle_protocol.Binding) -> conformance.Case:
    changed: list[str] = []
    for command in sorted(protocol.READ_COMMANDS):
        arguments = artifact.common_arguments() if command == "validate-bundle" else ()
        if command == "plan-bundle":
            arguments = artifact.plan_arguments(_CONFORMANCE_TARGET_DIGEST)
        first = invoke(command, protocol_v2.ActionPhase.EXECUTE, arguments).payload
        second = invoke(command, protocol_v2.ActionPhase.EXECUTE, arguments).payload
        if first != second:
            changed.append(command)
    return conformance.Case(
        "reads_are_repeatable",
        not changed,
        "every read answers the same twice"
        if not changed
        else f"answered differently on a second read: {', '.join(changed)}",
    )


def _object(value: JsonValue) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], value) if isinstance(value, dict) else {}


def _list(value: JsonValue | None) -> list[JsonValue]:
    return cast(list[JsonValue], value) if isinstance(value, list) else []


_CONFORMANCE_TARGET_DIGEST = "sha256:" + "0" * 64
