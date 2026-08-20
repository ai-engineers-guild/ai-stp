"""Exact consumer/provider binding for one HarnessBundle lifecycle."""

import hashlib
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import bundle_protocol
from ai_stp_foundation.canonical import JsonValue

LOGICAL = "sha256:" + "a" * 64
TARGET = "sha256:" + "b" * 64
PLAN = "sha256:" + "c" * 64


def _binding(tmp_path: Path) -> bundle_protocol.Binding:
    payload = b"literal zip bytes"
    path = tmp_path / "bundle.zip"
    path.write_bytes(payload)
    return bundle_protocol.binding(
        path,
        bundle_format="ai-stp-bundle/1",
        bundle_digest=LOGICAL,
        artifact_digest="sha256:" + hashlib.sha256(payload).hexdigest(),
        bundle_size=len(payload),
    )


def _echo(bound: bundle_protocol.Binding) -> dict[str, JsonValue]:
    return {
        "bundle_format": bound.bundle_format,
        "bundle_digest": bound.bundle_digest,
        "artifact_digest": bound.artifact_digest,
        "bundle_size": bound.bundle_size,
    }


def test_command_arguments_bind_one_absolute_artifact_and_target(tmp_path: Path) -> None:
    bound = _binding(tmp_path)
    common = bound.common_arguments()
    assert common[common.index("--bundle") + 1] == str((tmp_path / "bundle.zip").resolve())
    assert bound.plan_arguments(TARGET)[-2:] == ("--expected-target-digest", TARGET)
    assert bound.apply_arguments(TARGET, PLAN)[-2:] == ("--plan-digest", PLAN)


def test_validation_and_plan_require_exact_echoes_and_effects(tmp_path: Path) -> None:
    bound = _binding(tmp_path)
    bundle_protocol.require_validated({**_echo(bound), "valid": True}, bound)
    bundle_protocol.require_rejected(
        {**_echo(bound), "rejected": True, "reason": "digest_mismatch"},
        bound,
        "digest_mismatch",
    )
    planned = bundle_protocol.require_plan(
        {
            **_echo(bound),
            "state": "planned",
            "plan_digest": PLAN,
            "expected_target_digest": TARGET,
            "effects": ["write target"],
        },
        bound,
        TARGET,
    )
    assert planned.digest == PLAN
    assert planned.effects == ("write target",)

    with pytest.raises(CliFailure, match="exact HarnessBundle"):
        bundle_protocol.require_validated(
            {**_echo(bound), "valid": True, "bundle_size": bound.bundle_size + 1}, bound
        )
    with pytest.raises(CliFailure, match="required HarnessBundle refusal"):
        bundle_protocol.require_rejected(
            {**_echo(bound), "rejected": True, "reason": "path_duplicate"},
            bound,
            "digest_mismatch",
        )
    with pytest.raises(CliFailure, match="enumerate"):
        bundle_protocol.require_plan(
            {
                **_echo(bound),
                "state": "planned",
                "plan_digest": PLAN,
                "expected_target_digest": TARGET,
                "effects": [],
            },
            bound,
            TARGET,
        )


def test_apply_evidence_must_echo_bundle_target_and_provider_plan(tmp_path: Path) -> None:
    bound = _binding(tmp_path)
    answer = {
        **_echo(bound),
        "state": "verified",
        "expected_target_digest": TARGET,
        "plan_digest": PLAN,
    }
    bundle_protocol.require_applied(answer, bound, TARGET, PLAN)

    with pytest.raises(CliFailure, match="different provider plan"):
        bundle_protocol.require_applied(
            {**answer, "plan_digest": "sha256:" + "d" * 64}, bound, TARGET, PLAN
        )


def test_binding_refuses_symlink_noncanonical_digest_and_changed_size(tmp_path: Path) -> None:
    bound = _binding(tmp_path)
    link = tmp_path / "linked.zip"
    link.symlink_to(bound.path)
    with pytest.raises(CliFailure, match="regular absolute file"):
        bundle_protocol.binding(
            link,
            bundle_format=bound.bundle_format,
            bundle_digest=bound.bundle_digest,
            artifact_digest=bound.artifact_digest,
            bundle_size=bound.bundle_size,
        )
    with pytest.raises(CliFailure, match="canonical SHA-256"):
        bundle_protocol.binding(
            bound.path,
            bundle_format=bound.bundle_format,
            bundle_digest="not-a-digest",
            artifact_digest=bound.artifact_digest,
            bundle_size=bound.bundle_size,
        )
    with pytest.raises(CliFailure, match="size differs"):
        bundle_protocol.binding(
            bound.path,
            bundle_format=bound.bundle_format,
            bundle_digest=bound.bundle_digest,
            artifact_digest=bound.artifact_digest,
            bundle_size=bound.bundle_size + 1,
        )
