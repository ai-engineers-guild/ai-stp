"""Verify exact provider bytes against a pinned GitHub build identity."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from ai_stp_cli.errors import CliFailure
from ai_stp_foundation.canonical import JsonValue, canonize

#: `gh` exits 4 when no credential is configured. Every other non-zero exit is
#: a verdict about the artifact; this one is a fact about the machine.
GH_NOT_AUTHENTICATED: Final[int] = 4


@dataclass(frozen=True)
class Policy:
    repository: str
    source_commit: str
    signer_workflow: str
    verified_publisher: bool = False


@dataclass(frozen=True)
class Evidence:
    trust_level: str
    digest: str
    document: str


def verify(artifact: Path, policy: Policy, *, bundle: Path | None = None) -> Evidence:
    """Run GitHub's verifier with every identity-bearing policy flag pinned."""
    command = [
        "gh",
        "attestation",
        "verify",
        str(artifact),
        "--repo",
        policy.repository,
        "--source-digest",
        policy.source_commit,
        "--signer-workflow",
        policy.signer_workflow,
        "--deny-self-hosted-runners",
        "--format=json",
    ]
    if bundle is not None:
        command.extend(("--bundle", str(bundle)))
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            shell=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "GitHub attestation verification is unavailable",
            details={"dependency": "gh", "exception": type(error).__name__},
        ) from error
    if completed.returncode == GH_NOT_AUTHENTICATED:
        # `gh` exits 4 when it has no credential, and that is a fact about this
        # machine, not about the bytes. Reporting it as "the artifact has no
        # acceptable attestation" accuses the artifact: it sends the reader to
        # the provider's repository to look for a signing defect that is not
        # there, when the fix is one `gh auth login` here.
        #
        # Measured 2026-08-29 while wiring the real-provider E2E: five of five
        # harnesses failed identically, which is the shape of an instrument
        # problem and not of five broken releases. The two are cleanly
        # distinguishable — a genuine verdict exits 1 — so nothing is guessed.
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "GitHub attestation cannot be checked because gh is not authenticated here",
            # The remedy goes in `details`, not `next_actions`: that list names
            # this CLI's own commands, and `gh auth login` is somebody else's.
            details={
                "dependency": "gh",
                "repository": policy.repository,
                "remedy": "run 'gh auth login', or set GH_TOKEN",
            },
        )
    if completed.returncode != 0:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider artifact has no acceptable GitHub build attestation",
            details={"repository": policy.repository},
        )
    try:
        parsed: object = json.loads(completed.stdout)
    except ValueError as error:
        raise CliFailure(
            "AI_STP_DEPENDENCY_UNAVAILABLE",
            "GitHub attestation verification returned invalid JSON",
            details={"dependency": "gh"},
        ) from error
    if not isinstance(parsed, list) or not parsed:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "GitHub verified no attestation for the provider artifact",
            details={"repository": policy.repository},
        )
    rows = cast(list[object], parsed)
    if not any(_has_verified_timestamp(item) for item in rows):
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider attestation has no verified transparency timestamp",
            details={"repository": policy.repository},
        )
    document = canonize(cast(JsonValue, parsed)).decode("utf-8")
    digest = f"sha256:{hashlib.sha256(document.encode('utf-8')).hexdigest()}"
    return Evidence(
        trust_level="verified_publisher" if policy.verified_publisher else "build_attested",
        digest=digest,
        document=document,
    )


def verify_stored(artifact: Path, policy: Policy, document: str) -> Evidence:
    """Re-verify plan-bound bundles without fetching mutable remote state."""
    try:
        parsed: object = json.loads(document)
        if not isinstance(parsed, list) or not parsed:
            raise TypeError("attestation evidence must be a non-empty list")
        rows = cast(list[object], parsed)
        bundles = [_sigstore_bundle(item) for item in rows]
    except (ValueError, TypeError, KeyError) as error:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the plan-bound provider attestation evidence is invalid",
        ) from error
    with tempfile.TemporaryDirectory(prefix="ai-stp-provider-attestation-") as raw:
        bundle = Path(raw) / "bundle.jsonl"
        bundle.write_text(
            "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in bundles),
            encoding="utf-8",
        )
        return verify(artifact, policy, bundle=bundle)


def _sigstore_bundle(item: object) -> dict[str, object]:
    """Return the Sigstore bundle `gh attestation verify --bundle` accepts.

    GitHub CLI `--format=json` wraps that object as `attestation.bundle` next
    to `bundle_url` and `initiator`. Feeding the wrapper back as `--bundle`
    fails with `unknown field "bundle"`.
    """
    attestation = _json_field(item, "attestation", item)
    bundle = _json_field(attestation, "bundle", attestation)
    if not isinstance(bundle, dict) or "dsseEnvelope" not in bundle:
        raise TypeError("attestation row is not a Sigstore bundle")
    return cast(dict[str, object], bundle)


def _json_field(container: object, key: str, fallback: object) -> object:
    if not isinstance(container, dict):
        raise TypeError("attestation row must be an object")
    held = cast(dict[object, object], container)
    if key not in held:
        return fallback
    return held[key]


def _has_verified_timestamp(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    result = cast(dict[object, object], item).get("verificationResult")
    if not isinstance(result, dict):
        return False
    timestamps = cast(dict[object, object], result).get("verifiedTimestamps")
    return isinstance(timestamps, list) and len(cast(list[object], timestamps)) > 0
