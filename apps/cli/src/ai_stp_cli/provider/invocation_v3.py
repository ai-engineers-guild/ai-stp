"""Executable boundary for the local-only provider protocol v3 core."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ai_stp_cli.provider import conformance, invocation_v2, protocol_v2, protocol_v3
from ai_stp_foundation.canonical import JsonValue


def _target(path: str) -> Path:
    target = Path(path)
    if target.is_symlink() or not target.is_absolute() or not target.is_dir():
        raise ValueError("provider v3 target must be an existing absolute directory")
    return target.resolve()


def invoke(
    executable: str,
    target: str,
    command: str,
    arguments: Sequence[str] = (),
    *,
    launcher: invocation_v2.NetworkLauncher | None,
    capability: protocol_v2.NetworkCapability | None,
) -> JsonValue:
    """Run one exact core command under consumer-proved network denial."""
    if command not in protocol_v3.CORE_COMMANDS:
        raise KeyError(f"unknown provider v3 core command: {command}")
    resolved_target = _target(target)
    resolved_executable = conformance.resolve_executable(executable)
    if (
        launcher is None
        or capability is None
        or launcher.capability != capability
        or capability.enforcement is not protocol_v2.NetworkEnforcement.ENFORCED
    ):
        raise protocol_v2.NetworkCapabilityUnavailable(
            protocol_v2.NetworkDecision(
                command=command,
                phase=protocol_v2.ActionPhase.EXECUTE,
                requirement=protocol_v2.NetworkRequirement.NONE,
                enforcement=protocol_v2.NetworkEnforcement.UNAVAILABLE,
                launcher_id=None,
                evidence=("no verified network launcher was discovered",),
            )
        )
    provider_arguments = (
        () if command == "provider-info" else ("--target", str(resolved_target), "--json")
    )
    argv = (resolved_executable, command, *provider_arguments, *arguments)
    wrapped = launcher.wrap(argv, target=resolved_target)
    return conformance.invoke_argv(wrapped, command=command)
