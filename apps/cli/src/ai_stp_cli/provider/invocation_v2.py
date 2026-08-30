"""Executable provider protocol v2 phase boundary.

The release manifest selects v2 before ``provider-info`` is invoked. Every v2
spawn therefore names an exact command phase. Local-only phases are wrapped in
the observed OS launcher; permitted network phases deliberately are not. The
decision travels beside the provider payload because enforcement is a consumer
observation and must never be trusted from provider output.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ai_stp_cli.provider import conformance, protocol_v2
from ai_stp_foundation.canonical import JsonValue


class NetworkLauncher(Protocol):
    """One proved launcher capable of wrapping a local-only provider argv."""

    @property
    def capability(self) -> protocol_v2.NetworkCapability: ...

    def wrap(
        self,
        argv: tuple[str, ...],
        *,
        target: Path,
        writable: tuple[Path, ...] = (),
    ) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class InvocationResult:
    """Provider payload plus the consumer-observed network decision."""

    payload: JsonValue
    network: protocol_v2.NetworkDecision


def _target(path: str) -> Path:
    target = Path(path)
    if target.is_symlink() or not target.is_absolute() or not target.is_dir():
        raise ValueError("provider v2 target must be an existing absolute directory")
    return target.resolve()


def _local_argv(
    argv: tuple[str, ...],
    *,
    target: Path,
    decision: protocol_v2.NetworkDecision,
    launcher: NetworkLauncher | None,
    capability: protocol_v2.NetworkCapability | None,
) -> tuple[str, ...]:
    """Require the launcher that produced the exact enforced observation."""
    if launcher is None or capability is None or launcher.capability != capability:
        refused = protocol_v2.decide(decision.command, decision.phase, None)
        protocol_v2.require_execution(refused)
        raise AssertionError("an unavailable local phase cannot continue")
    protocol_v2.require_execution(decision)
    return launcher.wrap(argv, target=target)


def invoke(
    executable: str,
    target: str,
    command: str,
    phase: protocol_v2.ActionPhase,
    arguments: Sequence[str] = (),
    *,
    launcher: NetworkLauncher | None,
    capability: protocol_v2.NetworkCapability | None,
) -> InvocationResult:
    """Invoke one exact v2 phase, failing before spawn when proof is absent."""
    resolved_target = _target(target)
    resolved_executable = conformance.resolve_executable(executable)
    decision = protocol_v2.decide(command, phase, capability)
    argv = (
        resolved_executable,
        command,
        "--phase",
        phase.value,
        "--target",
        str(resolved_target),
        *arguments,
    )
    if decision.requirement is protocol_v2.NetworkRequirement.NONE:
        argv = _local_argv(
            argv,
            target=resolved_target,
            decision=decision,
            launcher=launcher,
            capability=capability,
        )
    else:
        protocol_v2.require_execution(decision)
    return InvocationResult(
        payload=conformance.invoke_argv(argv, command=command),
        network=decision,
    )
