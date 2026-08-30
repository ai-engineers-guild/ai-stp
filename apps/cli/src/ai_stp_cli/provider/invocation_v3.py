"""Executable boundary for the local-only provider protocol v3 core."""

from __future__ import annotations

import platform
from collections.abc import Sequence
from pathlib import Path

from ai_stp_cli.provider import (
    conformance,
    network_launcher,
    protocol_v2,
    protocol_v3,
)
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
    launcher: network_launcher.NetworkLauncher | None,
    capability: protocol_v2.NetworkCapability | None,
    unisolated: network_launcher.UnisolatedLocalPhase | None = None,
    writable: tuple[Path, ...] = (),
) -> JsonValue:
    """Run one exact core command under consumer-proved network denial."""
    if command not in protocol_v3.CORE_COMMANDS:
        raise KeyError(f"unknown provider v3 core command: {command}")
    resolved_target = _target(target)
    resolved_executable = conformance.resolve_executable(executable)
    isolated = (
        launcher is not None
        and capability is not None
        and launcher.capability == capability
        and capability.enforcement is protocol_v2.NetworkEnforcement.ENFORCED
    )
    # Re-checked here rather than trusted from construction. The permission is a
    # value, and a value can travel; the platform that needs the exception is
    # the only one allowed to act on it. On Linux an unisolated phase would be a
    # proved capability being skipped, which is a different thing entirely.
    excepted = (
        unisolated is not None
        and platform.system().lower() in network_launcher.UNISOLATED_PLATFORMS
        and unisolated.reason in network_launcher.UNISOLATED_REASONS
    )
    if not isolated and not excepted:
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
    # Everything else is unchanged by the exception: literal argv, the resolved
    # target, the timeouts and output limits. Only the isolation is absent, and
    # its absence is what `provider network` keeps reporting.
    if launcher is None:
        return conformance.invoke_argv(argv, command=command)
    return launcher.run(argv, target=resolved_target, writable=writable, command=command)
