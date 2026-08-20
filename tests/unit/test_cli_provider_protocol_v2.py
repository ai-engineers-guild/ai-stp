"""Protocol v2 models network policy without pretending a launcher exists."""

from dataclasses import fields

import pytest
from jsonschema import Draft202012Validator, ValidationError

from ai_stp_cli.provider import protocol, protocol_v2


def test_v2_is_explicit_and_frozen_v1_is_unchanged() -> None:
    assert protocol.VERSION == 1
    assert protocol_v2.VERSION == 2
    assert protocol_v2.COMMANDS == protocol.COMMANDS
    assert not {field.name for field in fields(protocol.Boundary)} & {
        "network_requirement",
        "network_enforcement",
    }


def test_every_v2_command_has_one_closed_network_declaration() -> None:
    assert set(protocol_v2.ACTION_NETWORK) == set(protocol_v2.COMMANDS)


def test_v2_wire_schema_accepts_only_the_exact_phase_policy() -> None:
    schema = protocol_v2.WIRE_SCHEMA
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(  # pyright: ignore[reportUnknownMemberType]
        protocol_v2.wire_policy()
    )

    widened = protocol_v2.wire_policy()
    widened["launch"][0]["network_requirement"] = "none"
    with pytest.raises(ValidationError):
        validator.validate(widened)  # pyright: ignore[reportUnknownMemberType]


@pytest.mark.parametrize("command", ["software-install", "software-update"])
def test_download_permission_does_not_widen_local_apply(command: str) -> None:
    download = protocol_v2.phase_policy(command, protocol_v2.ActionPhase.DOWNLOAD)
    apply = protocol_v2.phase_policy(command, protocol_v2.ActionPhase.APPLY)
    assert download.requirement is protocol_v2.NetworkRequirement.ARTIFACT_DOWNLOAD
    assert apply.requirement is protocol_v2.NetworkRequirement.NONE


def test_local_action_without_a_verified_launcher_fails_before_invocation() -> None:
    invoked = False
    decision = protocol_v2.decide("apply-bundle", protocol_v2.ActionPhase.EXECUTE, None)

    with pytest.raises(protocol_v2.NetworkCapabilityUnavailable) as caught:
        protocol_v2.require_execution(decision)
        invoked = True

    assert not invoked
    assert caught.value.error_code == "AI_STP_DEPENDENCY_UNAVAILABLE"
    assert decision.enforcement is protocol_v2.NetworkEnforcement.UNAVAILABLE
    assert not decision.allows_execution


def test_enforced_claim_requires_launcher_identity_and_evidence() -> None:
    with pytest.raises(ValueError, match="launcher identity and evidence"):
        protocol_v2.NetworkCapability(
            enforcement=protocol_v2.NetworkEnforcement.ENFORCED,
            os_name="linux",
            launcher_id=None,
            evidence=(),
        )


def test_observed_enforcement_allows_the_exact_local_phase() -> None:
    capability = protocol_v2.NetworkCapability(
        enforcement=protocol_v2.NetworkEnforcement.ENFORCED,
        os_name="linux",
        launcher_id="verified-test-launcher/1",
        evidence=("DNS refused", "IPv4 refused", "IPv6 refused"),
    )
    decision = protocol_v2.decide("validate-bundle", protocol_v2.ActionPhase.EXECUTE, capability)

    protocol_v2.require_execution(decision)
    assert decision.allows_execution
    assert decision.enforcement is protocol_v2.NetworkEnforcement.ENFORCED


@pytest.mark.parametrize(
    ("command", "phase", "requirement"),
    [
        (
            "software-install",
            protocol_v2.ActionPhase.DOWNLOAD,
            protocol_v2.NetworkRequirement.ARTIFACT_DOWNLOAD,
        ),
        (
            "launch",
            protocol_v2.ActionPhase.EXECUTE,
            protocol_v2.NetworkRequirement.RUNTIME_EXTERNAL,
        ),
    ],
)
def test_explicitly_permitted_network_is_reported_as_not_requested(
    command: str,
    phase: protocol_v2.ActionPhase,
    requirement: protocol_v2.NetworkRequirement,
) -> None:
    decision = protocol_v2.decide(command, phase, None)

    protocol_v2.require_execution(decision)
    assert decision.requirement is requirement
    assert decision.enforcement is protocol_v2.NetworkEnforcement.NOT_REQUESTED


def test_unknown_command_or_phase_is_never_guessed() -> None:
    with pytest.raises(KeyError, match="unknown provider v2 command"):
        protocol_v2.phase_policy("do-everything", protocol_v2.ActionPhase.EXECUTE)
    with pytest.raises(KeyError, match="unknown provider v2 phase"):
        protocol_v2.phase_policy("launch", protocol_v2.ActionPhase.APPLY)
