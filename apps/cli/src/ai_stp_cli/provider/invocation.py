"""One way to call a provider, for every command that calls one.

The isolation boundary, the launcher discovery and the refusal that explains a
missing one are the same for a setup installation and for a program lifecycle.
Written twice they would agree until one of them learned something the other did
not — which is exactly how a plan argv came to exist in two versions in this
tree, with one of them missing the argument that defines a program operation.
"""

from __future__ import annotations

import platform
from collections.abc import Sequence
from pathlib import Path

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import (
    conformance,
    invocation_v2,
    invocation_v3,
    network_launcher,
    protocol,
    protocol_v2,
    protocol_v3,
)
from ai_stp_foundation.canonical import JsonValue


def provider_invoker(
    executable: str,
    target: str,
    version: int,
    *,
    unisolated_reason: str | None = None,
    writable: tuple[Path, ...] = (),
) -> conformance.Invoker:
    """Select frozen v1 or an enforced local-only v2/v3 boundary.

    `--target` is injected here and never by an argv builder. A caller that adds
    it by hand is exercising a call path that does not exist, and a probe written
    that way reports every provider as broken while the code is correct.
    """
    if version == protocol.VERSION:
        return conformance.subprocess_invoker(executable, target)

    launcher, capability = network_launcher.discover_launcher()
    # Only the install lifecycle names a reason, and only Windows can act on
    # one. Everything that merely observes a target passes nothing and keeps
    # refusing there, which is the scope `#416` decided rather than a scope
    # inferred from which function happens to call this.
    unisolated = (
        network_launcher.unisolated_local_phase(unisolated_reason)
        if unisolated_reason is not None
        and platform.system().lower() in network_launcher.UNISOLATED_PLATFORMS
        else None
    )

    def invoke(command: str, arguments: Sequence[str]) -> JsonValue:
        try:
            if version == protocol_v3.VERSION:
                return invocation_v3.invoke(
                    executable,
                    target,
                    command,
                    arguments,
                    launcher=launcher,
                    capability=capability,
                    unisolated=unisolated,
                    writable=writable,
                )
            return invocation_v2.invoke(
                executable,
                target,
                command,
                protocol_v2.ActionPhase.EXECUTE,
                arguments,
                launcher=launcher,
                capability=capability,
            ).payload
        except protocol_v2.NetworkCapabilityUnavailable as error:
            raise CliFailure(
                error.error_code,
                "provider protocol v2/v3 cannot run this local phase without network isolation",
                details={
                    "command": error.decision.command,
                    "phase": error.decision.phase.value,
                    "network_enforcement": error.decision.enforcement.value,
                },
                next_actions=["provider network --json"],
            ) from None

    return invoke
