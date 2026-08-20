"""Protocol v2 conformance checks declarations, phases and consumer decisions."""

from __future__ import annotations

import stat
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest

from ai_stp_cli.commands import select
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import conformance, conformance_v2, invocation_v2, protocol_v2
from ai_stp_foundation.canonical import JsonValue

CAPABILITY = protocol_v2.NetworkCapability(
    enforcement=protocol_v2.NetworkEnforcement.ENFORCED,
    os_name="linux",
    launcher_id="test-launcher/1",
    evidence=("test boundary denied network",),
)


def _arguments(arguments: Sequence[str]) -> dict[str, str]:
    return dict(zip(arguments[::2], arguments[1::2], strict=True))


def _bundle_echo(arguments: Sequence[str]) -> dict[str, JsonValue]:
    values = _arguments(arguments)
    return {
        "bundle_format": values["--bundle-format"],
        "bundle_digest": values["--bundle-digest"],
        "artifact_digest": values["--artifact-digest"],
        "bundle_size": int(values["--bundle-size"]),
    }


def _conforming(
    *,
    action_network: JsonValue | None = None,
    wrong_decision: bool = False,
) -> conformance_v2.PhaseInvoker:
    info: dict[str, JsonValue] = {
        "protocol_version": protocol_v2.VERSION,
        "harness_id": "codex",
        "provider_version": "2.0.0",
        "supported_actions": list(protocol_v2.COMMANDS),
        "bundle_formats": ["ai-stp-bundle/1"],
        "supported_os": ["linux", "macos"],
        "supported_arch": ["x86_64", "arm64"],
        "limits": {"max_files": 2000},
        "action_network": cast(JsonValue, protocol_v2.wire_policy())
        if action_network is None
        else action_network,
    }

    def invoke(
        command: str,
        phase: protocol_v2.ActionPhase,
        arguments: Sequence[str],
    ) -> conformance_v2.PhaseInvocation:
        decision = protocol_v2.decide(command, phase, CAPABILITY)
        if wrong_decision and command == "provider-info":
            decision = protocol_v2.decide("launch", protocol_v2.ActionPhase.EXECUTE, CAPABILITY)
        if command == "provider-info":
            payload: JsonValue = info
        elif command == "validate-bundle":
            case = Path(_arguments(arguments)["--bundle"]).parent.name
            if case == "valid":
                payload = {**_bundle_echo(arguments), "valid": True}
            else:
                reasons = {item.name: item.refusal for item in conformance.MALICIOUS_BUNDLES}
                payload = {
                    **_bundle_echo(arguments),
                    "rejected": True,
                    "reason": reasons[case],
                }
        elif command == "plan-bundle":
            values = _arguments(arguments)
            payload = {
                **_bundle_echo(arguments[:-2]),
                "state": "planned",
                "expected_target_digest": values["--expected-target-digest"],
                "plan_digest": "sha256:" + "2" * 64,
                "effects": ["write conformance target"],
            }
        elif command == "status":
            payload = {"state": "verified"}
        else:
            payload = {"answered": f"{command}:{phase.value}"}
        return invocation_v2.InvocationResult(payload=payload, network=decision)

    return invoke


def test_conforming_v2_provider_passes_every_command_phase_and_safety_case() -> None:
    report = conformance_v2.run(_conforming(), harness_id="codex")

    assert report.conforms, [case.detail for case in report.failures]
    assert report.protocol_version == protocol_v2.VERSION


def test_v2_conformance_never_invokes_an_effect_or_launch() -> None:
    seen: list[str] = []
    provider = _conforming()

    def invoke(
        command: str,
        phase: protocol_v2.ActionPhase,
        arguments: Sequence[str],
    ) -> conformance_v2.PhaseInvocation:
        seen.append(command)
        return provider(command, phase, arguments)

    report = conformance_v2.run(invoke, harness_id="codex")

    assert report.conforms
    assert not set(seen) & {
        "software-install",
        "software-update",
        "software-remove",
        "apply-bundle",
        "restore",
        "launch",
    }


def test_widened_provider_network_declaration_fails() -> None:
    widened = cast(dict[str, JsonValue], protocol_v2.wire_policy())
    launch = cast(list[JsonValue], widened["launch"])
    cast(dict[str, JsonValue], launch[0])["network_requirement"] = "none"

    report = conformance_v2.run(_conforming(action_network=widened), harness_id="codex")

    assert "action_network_exact" in {case.name for case in report.failures}


def test_provider_payload_cannot_forge_the_consumer_network_decision() -> None:
    report = conformance_v2.run(_conforming(wrong_decision=True), harness_id="codex")

    assert "network_decision_provider-info_execute" in {case.name for case in report.failures}


def test_cli_v2_conformance_fails_before_provider_spawn_without_launcher(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "spawned"
    provider = tmp_path / "provider"
    provider.write_text(
        f"#!/usr/bin/env python3\nopen({str(marker)!r}, 'w').write('yes')\n",
        encoding="utf-8",
    )
    provider.chmod(provider.stat().st_mode | stat.S_IXUSR)
    unavailable = protocol_v2.NetworkCapability(
        enforcement=protocol_v2.NetworkEnforcement.UNAVAILABLE,
        os_name="linux",
        launcher_id=None,
        evidence=("no launcher",),
    )
    monkeypatch.setattr(
        "ai_stp_cli.commands.select.network_launcher.discover_bubblewrap",
        lambda: (None, unavailable),
    )

    with pytest.raises(CliFailure) as caught:
        select.provider_conformance(
            {
                "harness": "codex",
                "executable": str(provider),
                "target": str(tmp_path),
                "protocol-version": 2,
            }
        )

    assert caught.value.code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert not marker.exists()


def test_cli_refuses_to_guess_a_protocol_newer_than_v3(tmp_path: Path) -> None:
    provider = tmp_path / "provider"
    provider.write_text("#!/bin/sh\nprintf '{}\\n'\n", encoding="utf-8")
    provider.chmod(provider.stat().st_mode | stat.S_IXUSR)

    with pytest.raises(CliFailure) as caught:
        select.provider_conformance(
            {
                "harness": "codex",
                "executable": str(provider),
                "target": str(tmp_path),
                "protocol-version": 4,
            }
        )

    assert caught.value.code == "AI_STP_VALIDATION_ERROR"
