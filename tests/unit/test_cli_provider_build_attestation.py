"""GitHub build attestation is a distinct, policy-pinned provider trust path."""

import json
import subprocess
from pathlib import Path

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import build_attestation

POLICY = build_attestation.Policy(
    repository="NDDev-OpenNetwork/codex-setup-system",
    source_commit="a" * 40,
    signer_workflow="NDDev-OpenNetwork/codex-setup-system/.github/workflows/release.yml",
)


def test_exact_policy_and_verified_timestamp_produce_attested_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "provider"
    artifact.write_bytes(b"exact")
    payload: list[object] = [{"verificationResult": {"verifiedTimestamps": [{"type": "tlog"}]}}]
    seen: list[str] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.extend(command)
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", run)
    evidence = build_attestation.verify(artifact, POLICY)

    assert evidence.trust_level == "build_attested"
    assert evidence.digest.startswith("sha256:")
    assert ["--repo", POLICY.repository] == seen[seen.index("--repo") : seen.index("--repo") + 2]
    assert POLICY.source_commit in seen
    assert POLICY.signer_workflow in seen
    assert "--deny-self-hosted-runners" in seen
    assert "shell" not in seen


def test_verified_publisher_is_stronger_only_after_byte_attestation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "provider"
    artifact.write_bytes(b"exact")
    payload: list[object] = [{"verificationResult": {"verifiedTimestamps": [{}]}}]

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", run)
    policy = build_attestation.Policy(
        repository=POLICY.repository,
        source_commit=POLICY.source_commit,
        signer_workflow=POLICY.signer_workflow,
        verified_publisher=True,
    )
    assert build_attestation.verify(artifact, policy).trust_level == "verified_publisher"


def test_missing_transparency_timestamp_is_not_trusted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "provider"
    artifact.write_bytes(b"exact")

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command, 0, '[{"verificationResult":{"verifiedTimestamps":[]}}]', ""
        )

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(CliFailure) as raised:
        build_attestation.verify(artifact, POLICY)
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"


_GH_WRAPPER = {
    "attestation": {
        "bundle": {
            "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
            "dsseEnvelope": {"payload": "e30=", "payloadType": "application/vnd.in-toto+json"},
            "verificationMaterial": {},
        },
        "bundle_url": "",
        "initiator": "",
    },
    "verificationResult": {"verifiedTimestamps": [{"type": "Tlog"}]},
}


def test_verify_stored_feeds_sigstore_bundle_not_github_cli_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Plan-bound evidence is gh JSON; apply must unwrap the Sigstore object.

    Writing `attestation` itself as `--bundle` makes gh refuse
    `unknown field "bundle"`, which used to fail attested apply after a
    successful plan.
    """
    artifact = tmp_path / "provider"
    artifact.write_bytes(b"exact")
    seen: list[str] = []
    payload: list[object] = [{"verificationResult": {"verifiedTimestamps": [{}]}}]

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.extend(command)
        bundle_path = Path(command[command.index("--bundle") + 1])
        document = json.loads(bundle_path.read_text(encoding="utf-8").splitlines()[0])
        assert "dsseEnvelope" in document
        assert "bundle_url" not in document
        assert "initiator" not in document
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", run)
    evidence = build_attestation.verify_stored(
        artifact, POLICY, json.dumps([_GH_WRAPPER], separators=(",", ":"))
    )
    assert evidence.trust_level == "build_attested"
    assert "--bundle" in seen


def test_verify_stored_rejects_github_cli_wrapper_as_the_bundle(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "provider"
    artifact.write_bytes(b"exact")
    with pytest.raises(CliFailure) as raised:
        build_attestation.verify_stored(
            artifact,
            POLICY,
            json.dumps([{"attestation": {"bundle_url": "", "initiator": ""}}]),
        )
    assert raised.value.code == "AI_STP_PRECONDITION_FAILED"
    assert raised.value.message == "the plan-bound provider attestation evidence is invalid"
