"""Provider protocol v2 network contract (`ADR-0047`, `REQ-821` through `REQ-824`).

This module is deliberately separate from frozen v1. It defines the wire
declaration and the decision that a future verified OS launcher must consume;
it does not pretend that naming a launcher enforces anything. Until capability
discovery supplies observed ``enforced`` evidence, every local-only action is
refused before a provider may be invoked.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from ai_stp_cli.provider import protocol

VERSION: Final[int] = 2
COMMANDS: Final[tuple[str, ...]] = protocol.COMMANDS


class NetworkRequirement(StrEnum):
    """The network capability one provider phase declares."""

    NONE = "none"
    ARTIFACT_DOWNLOAD = "artifact_download"
    RUNTIME_EXTERNAL = "runtime_external"


class NetworkEnforcement(StrEnum):
    """What the consumer actually observed for this invocation decision."""

    ENFORCED = "enforced"
    UNAVAILABLE = "unavailable"
    NOT_REQUESTED = "not_requested"


class ActionPhase(StrEnum):
    """A closed phase prevents download permission from widening local apply."""

    EXECUTE = "execute"
    DOWNLOAD = "download"
    APPLY = "apply"


@dataclass(frozen=True)
class PhasePolicy:
    """One command phase and its exact network requirement."""

    phase: ActionPhase
    requirement: NetworkRequirement


_LOCAL: Final[tuple[PhasePolicy, ...]] = (
    PhasePolicy(ActionPhase.EXECUTE, NetworkRequirement.NONE),
)
_DOWNLOAD_THEN_APPLY: Final[tuple[PhasePolicy, ...]] = (
    PhasePolicy(ActionPhase.DOWNLOAD, NetworkRequirement.ARTIFACT_DOWNLOAD),
    PhasePolicy(ActionPhase.APPLY, NetworkRequirement.NONE),
)

ACTION_NETWORK: Final[Mapping[str, tuple[PhasePolicy, ...]]] = MappingProxyType(
    {
        "provider-info": _LOCAL,
        "software-status": _LOCAL,
        "software-plan": _LOCAL,
        "software-install": _DOWNLOAD_THEN_APPLY,
        "software-update": _DOWNLOAD_THEN_APPLY,
        "software-remove": _LOCAL,
        "validate-bundle": _LOCAL,
        "plan-bundle": _LOCAL,
        "apply-bundle": _LOCAL,
        "status": _LOCAL,
        "restore": _LOCAL,
        "launch": (PhasePolicy(ActionPhase.EXECUTE, NetworkRequirement.RUNTIME_EXTERNAL),),
    }
)


@dataclass(frozen=True)
class NetworkCapability:
    """Observed capability evidence from an OS-specific probe.

    ``not_requested`` is an invocation result, never a capability probe result.
    An enforced result without a launcher identity and evidence is a claim with
    no proof and is rejected at construction time.
    """

    enforcement: NetworkEnforcement
    os_name: str
    launcher_id: str | None
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.os_name:
            raise ValueError("network capability must name the operating system")
        if self.enforcement is NetworkEnforcement.NOT_REQUESTED:
            raise ValueError("not_requested is not a capability probe result")
        if self.enforcement is NetworkEnforcement.ENFORCED and (
            not self.launcher_id or not self.evidence
        ):
            raise ValueError("enforced capability requires launcher identity and evidence")
        if self.enforcement is NetworkEnforcement.UNAVAILABLE and self.launcher_id is not None:
            raise ValueError("unavailable capability cannot name an active launcher")


@dataclass(frozen=True)
class NetworkDecision:
    """The auditable pre-invocation result for exactly one command phase."""

    command: str
    phase: ActionPhase
    requirement: NetworkRequirement
    enforcement: NetworkEnforcement
    launcher_id: str | None
    evidence: tuple[str, ...]

    @property
    def allows_execution(self) -> bool:
        if self.requirement is NetworkRequirement.NONE:
            return self.enforcement is NetworkEnforcement.ENFORCED
        return self.enforcement is NetworkEnforcement.NOT_REQUESTED


class NetworkCapabilityUnavailable(RuntimeError):
    """A local-only phase has no proved network-denying launcher."""

    error_code: Final[str] = "AI_STP_DEPENDENCY_UNAVAILABLE"

    def __init__(self, decision: NetworkDecision) -> None:
        self.decision = decision
        super().__init__(
            f"network isolation is unavailable for {decision.command}:{decision.phase.value}"
        )


def phase_policy(command: str, phase: ActionPhase) -> PhasePolicy:
    """Return one closed policy entry; unknown command/phase is refused."""
    try:
        policies = ACTION_NETWORK[command]
    except KeyError as error:
        raise KeyError(f"unknown provider v2 command: {command}") from error
    for held in policies:
        if held.phase is phase:
            return held
    raise KeyError(f"unknown provider v2 phase: {command}:{phase.value}")


def decide(
    command: str,
    phase: ActionPhase,
    capability: NetworkCapability | None,
) -> NetworkDecision:
    """Decide before invocation without overstating unavailable enforcement."""
    requirement = phase_policy(command, phase).requirement
    if requirement is not NetworkRequirement.NONE:
        return NetworkDecision(
            command=command,
            phase=phase,
            requirement=requirement,
            enforcement=NetworkEnforcement.NOT_REQUESTED,
            launcher_id=None,
            evidence=(f"policy permits {requirement.value} for this exact phase",),
        )
    if capability is None:
        enforcement = NetworkEnforcement.UNAVAILABLE
        launcher_id = None
        evidence = ("no verified network launcher was discovered",)
    else:
        enforcement = capability.enforcement
        launcher_id = capability.launcher_id
        evidence = capability.evidence
    return NetworkDecision(
        command=command,
        phase=phase,
        requirement=requirement,
        enforcement=enforcement,
        launcher_id=launcher_id,
        evidence=evidence,
    )


def require_execution(decision: NetworkDecision) -> None:
    """Fail before invoking a provider when the decision does not permit it."""
    if not decision.allows_execution:
        raise NetworkCapabilityUnavailable(decision)


def wire_policy() -> dict[str, list[dict[str, str]]]:
    """Return the exact provider-info ``action_network`` declaration."""
    return {
        command: [
            {"phase": held.phase.value, "network_requirement": held.requirement.value}
            for held in policies
        ]
        for command, policies in ACTION_NETWORK.items()
    }


def _build_wire_schema() -> dict[str, object]:
    """Return a closed JSON Schema for provider-info ``action_network``."""
    declaration = wire_policy()
    properties: dict[str, object] = {}
    for command in declaration:
        policies = ACTION_NETWORK[command]
        phases: list[dict[str, object]] = []
        for held in policies:
            phases.append(
                {
                    "type": "object",
                    "properties": {
                        "phase": {"const": held.phase.value},
                        "network_requirement": {"const": held.requirement.value},
                    },
                    "required": ["phase", "network_requirement"],
                    "additionalProperties": False,
                }
            )
        properties[command] = {
            "type": "array",
            "prefixItems": phases,
            "items": False,
            "minItems": len(phases),
            "maxItems": len(phases),
        }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://nddev.asia/schemas/provider-protocol/v2/action-network.json",
        "type": "object",
        "properties": properties,
        "required": list(declaration),
        "additionalProperties": False,
    }


WIRE_SCHEMA: Final[dict[str, object]] = _build_wire_schema()
