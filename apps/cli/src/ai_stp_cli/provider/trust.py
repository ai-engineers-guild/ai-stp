"""Establishing that a provider executable is the release it claims to be.

Lifted out of `commands.install` because a second caller arrived. The harness
program lifecycle spawns a provider too, and had been doing so without any of
this — no manifest, no attestation, no byte comparison, and no launcher-less
trust reason, which is why `harness install` could not reach a provider on
macOS or Windows at all and ran an unverified one on Linux.

Copying these four into a second command would have been the third table of one
fact this week. They live here once, and both callers read the same decision.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import provider_releases
from ai_stp_cli.paths import redact_home
from ai_stp_cli.provider import build_attestation, network_launcher, protocol_v3, release


@dataclass(frozen=True)
class ReleaseEvidence:
    manifest: release.ReleaseManifest | None
    trust: str = "unverified"
    evidence: str = ""


def unisolated_reason(
    trusted_release: ReleaseEvidence | release.ReleaseManifest | None,
    parameters: Mapping[str, object],
) -> str | None:
    """Why this install may proceed on Windows with nothing denying the network.

    Both answers are things the caller already had to establish: a release
    verified against manifest, policy and exact bytes, or an operator who named
    an unverified provider on purpose. Neither is new authority — this only
    reads which of the two happened. Off Windows it is ignored.
    """
    if trusted_release is not None:
        return network_launcher.TRUSTED_RELEASE
    if bool(parameters.get("unverified-provider", False)):
        return network_launcher.EXPLICIT_UNVERIFIED_PROVIDER
    return None


def release_required(
    parameters: Mapping[str, object],
    protocol_version: int,
    trusted_release: release.ReleaseManifest | None,
) -> None:
    """Protocol v3 installs a signed release, or says out loud that it does not.

    v1 and v2 predate the signed-release line and keep their behaviour. v3 is
    where prepared SetupVersions and provider-owned operations live, so it is
    where an unverified executable would matter most.

    An unverified install stays possible. Refusing it outright would only move
    the same act outside the tool, where nothing records that it happened, and
    the person running a provider they just built is not the threat the pinned
    policy exists for. What changes is that it can no longer happen by
    omission: `unverified-provider` is the difference between a decision and a
    default, and the plan it produces reports `provider_release_trusted` false
    for anybody reading it afterwards.

    The rule governs the mutating path. `install target-status` and `diff`
    spawn an executable the caller named in order to observe, and install
    nothing; `provider-release.md` records that scope rather than leaving it to
    be inferred from which function happens to call this one.
    """
    unverified = bool(parameters.get("unverified-provider", False))
    if unverified and trusted_release is not None:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "a signed release manifest and unverified-provider contradict each other",
            next_actions=["install plan --provider-manifest <path> --json"],
        )
    if protocol_version != protocol_v3.VERSION or trusted_release is not None or unverified:
        return
    raise CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "protocol v3 installs a signed provider release",
        details={"protocol_version": str(protocol_version)},
        next_actions=[
            "provider fetch --harness <id> --json",
            "install plan --provider-manifest <path> --json",
            "install plan --unverified-provider --json",
        ],
    )


def trusted_manifest(
    connection: sqlite3.Connection,
    parameters: Mapping[str, object],
    executable: str,
    *,
    recovery_requested: bool,
) -> ReleaseEvidence:
    """Verify a signed manifest and exact executable before the first spawn."""
    given = str(parameters.get("provider-manifest") or "")
    if not given:
        if recovery_requested:
            raise CliFailure(
                "AI_STP_VALIDATION_ERROR",
                "provider release recovery requires the exact signed release manifest",
                next_actions=["install plan --provider-manifest <path> --json"],
            )
        return ReleaseEvidence(None)
    place = Path(given).expanduser()
    if place.is_symlink() or not place.is_file():
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no regular provider release manifest sits at that path",
            details={"manifest": redact_home(place)},
        )
    manifest = release.parse_manifest(place.read_text("utf-8"))
    observed_digest, observed_size = release.artifact_identity(Path(executable))
    known_sequence = provider_releases.minimum_sequence(connection, manifest.provider_id)
    if recovery_requested and manifest.sequence >= known_sequence:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "provider release recovery must name an older release than the local floor",
            details={
                "sequence": str(manifest.sequence),
                "known_sequence": str(known_sequence),
            },
        )
    recovery_verified = recovery_requested and provider_releases.was_verified(
        connection,
        provider_id=manifest.provider_id,
        sequence=manifest.sequence,
        artifact_digest=manifest.artifact_digest,
    )
    policy = release.pinned_policy()
    attested = bool(parameters.get("provider-build-attestation", False)) or (
        manifest.repository in policy.build_attestations
    )
    if attested and recovery_requested:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "provider release recovery currently requires signed local history",
        )
    verdict = (
        release.verify_attested(
            manifest,
            policy,
            known_sequence=known_sequence,
            observed_digest=observed_digest,
            observed_size=observed_size,
            platform=release.current_platform(),
        )
        if attested
        else release.verify(
            manifest,
            policy,
            known_sequence=known_sequence,
            observed_digest=observed_digest,
            observed_size=observed_size,
            platform=release.current_platform(),
            recovery_requested=recovery_requested,
            recovery_to_verified=recovery_verified,
        )
    )
    if not verdict.accepted:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the provider release does not satisfy the pinned trust policy and exact bytes",
            details={"refusals": ", ".join(item.code for item in verdict.refusals)},
            next_actions=["provider trust --manifest <path> --json"],
        )
    if Path(manifest.entry_point).name != Path(executable).name:
        raise CliFailure(
            "AI_STP_PRECONDITION_FAILED",
            "the signed provider entry point does not name this executable",
            details={
                "entry_point": manifest.entry_point,
                "executable": Path(executable).name,
            },
        )
    if not attested:
        return ReleaseEvidence(manifest, verdict.trust_level)
    rule = policy.build_attestations[manifest.repository]
    given_bundle = str(parameters.get("provider-attestation-bundle") or "")
    bundle = Path(given_bundle).expanduser() if given_bundle else None
    if bundle is not None and (bundle.is_symlink() or not bundle.is_file()):
        raise CliFailure(
            "AI_STP_NOT_FOUND",
            "no regular provider attestation bundle sits at that path",
            details={"bundle": redact_home(bundle)},
        )
    evidence = build_attestation.verify(
        Path(executable),
        build_attestation.Policy(
            repository=manifest.repository.removeprefix("github.com/"),
            source_commit=manifest.commit,
            signer_workflow=rule.signer_workflow,
            verified_publisher=rule.verified_publisher,
        ),
        bundle=bundle,
    )
    return ReleaseEvidence(manifest, evidence.trust_level, evidence.document)
