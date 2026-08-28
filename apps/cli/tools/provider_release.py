#!/usr/bin/env python3
"""Create and use the offline Ed25519 key for exact provider release manifests."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.provider import release

SUBJECT = "ai-stp:provider-release-manifest:v1"
POLICY_ID = "nddev/provider/1"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    keygen = subparsers.add_parser("keygen")
    keygen.add_argument("--private-key", required=True, type=Path)

    sign = subparsers.add_parser("sign")
    sign.add_argument("--private-key", required=True, type=Path)
    sign.add_argument("--provider-id", required=True)
    sign.add_argument("--provider-version", required=True)
    sign.add_argument("--repository", required=True)
    # Required rather than defaulted. This was `NDDev-it-com`, a publisher the
    # shipped `provider-policy.toml` explicitly no longer trusts — so the tool
    # minted releases under an organisation the estate had moved off, and the
    # only thing that would have caught it is somebody reading both files.
    # Who is publishing is a fact the caller has and this tool does not.
    sign.add_argument("--publisher", required=True)
    sign.add_argument("--commit", required=True)
    sign.add_argument("--license", required=True, dest="license_name")
    sign.add_argument("--artifact", required=True, type=Path)
    sign.add_argument("--artifact-url", required=True)
    sign.add_argument("--entry-point", required=True)
    sign.add_argument("--protocol-version", required=True, type=int)
    sign.add_argument("--sequence", required=True, type=int)
    sign.add_argument("--supported-os", required=True, action="append")
    sign.add_argument("--supported-arch", required=True, action="append")
    sign.add_argument("--output", required=True, type=Path)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--artifact", required=True, type=Path)
    verify.add_argument("--public-key", required=True)
    verify.add_argument("--key-id", required=True)
    verify.add_argument("--platform", required=True)
    return parser


def _public(private: Ed25519PrivateKey) -> bytes:
    return private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def _key_id(public: bytes) -> str:
    return "ed25519:" + hashlib.sha256(public).hexdigest()[:24]


def _outside_checkout(path: Path) -> Path:
    resolved = path.resolve(strict=False)
    checkout = Path(__file__).resolve().parents[3]
    try:
        resolved.relative_to(checkout)
    except ValueError:
        return resolved
    raise ValueError("release key and manifest outputs must be outside the repository")


def _write_exclusive(path: Path, payload: bytes, mode: int) -> None:
    destination = _outside_checkout(path)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def generate(private_path: Path) -> dict[str, object]:
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    _write_exclusive(private_path, pem, 0o600)
    public = _public(private)
    return {
        "key_id": _key_id(public),
        "public_key": base64.b64encode(public).decode("ascii"),
        "private_key": str(private_path.resolve(strict=False)),
    }


def _load_private(path: Path) -> Ed25519PrivateKey:
    # `os.getuid` is POSIX-only, and the guards below are the only thing standing
    # between a group-readable private key and a signed provider release. Skipping
    # them where the attribute is missing would make the strongest key in the
    # system unprotected on exactly one platform, silently.
    #
    # Refusing instead is cheap: this is offline release tooling run by a
    # maintainer, not a user path. Windows support here means implementing an ACL
    # check, not omitting the question.
    getuid = getattr(os, "getuid", None)
    if getuid is None:
        raise ValueError(
            "signing a provider release is supported on POSIX only: this platform "
            "has no uid/mode model and no ACL check is implemented"
        )
    held = path.lstat()
    if path.is_symlink() or not path.is_file() or held.st_uid != getuid():
        raise ValueError("private key must be a current-user-owned regular file")
    if stat_mode := held.st_mode & 0o077:
        raise ValueError(f"private key permissions expose group/other bits: {stat_mode:o}")
    loaded = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(loaded, Ed25519PrivateKey):
        raise ValueError("private key is not Ed25519")
    return loaded


def sign(args: argparse.Namespace) -> dict[str, object]:
    if args.sequence < 1:
        raise ValueError("provider release sequence must be positive")
    if len(args.supported_os) != len(set(args.supported_os)) or len(args.supported_arch) != len(
        set(args.supported_arch)
    ):
        raise ValueError("supported platform values must be unique")
    private = _load_private(args.private_key)
    public = _public(private)
    digest, size = release.artifact_identity(args.artifact)
    unsigned = release.ReleaseManifest(
        provider_id=args.provider_id,
        provider_version=args.provider_version,
        protocol_version=args.protocol_version,
        repository=args.repository,
        commit=args.commit,
        license=args.license_name,
        artifact_url=args.artifact_url,
        artifact_size=size,
        artifact_digest=digest,
        entry_point=args.entry_point,
        supported_os=frozenset(args.supported_os),
        supported_arch=frozenset(args.supported_arch),
        sequence=args.sequence,
        policy_id=POLICY_ID,
        publisher=args.publisher,
        signing_key=_key_id(public),
        signature_subject=SUBJECT,
        signature="",
    )
    unsigned = release.parse_manifest(release.serialize_manifest(unsigned))
    signature = base64.b64encode(private.sign(release.signature_payload(unsigned))).decode("ascii")
    manifest = release.parse_manifest(
        release.serialize_manifest(replace(unsigned, signature=signature))
    )
    # Self-consistency, not trust. This policy is built from the manifest being
    # signed, so it can only prove the manifest is internally coherent and that
    # signing produced something the verifier reads. The release becomes
    # installable when a person adds it to `provider-policy.toml`, which is the
    # approval this tool must not be able to grant itself.
    policy = release.TrustPolicy(
        schema_version=release.POLICY_SCHEMA_VERSION,
        policy_id=POLICY_ID,
        allowed_publishers=frozenset({args.publisher}),
        allowed_keys=frozenset({_key_id(public)}),
        allowed_repositories=frozenset({args.repository}),
        pinned_releases=frozenset(
            {
                release.PinnedRelease(
                    provider_id=manifest.provider_id,
                    repository=manifest.repository,
                    artifact_digest=manifest.artifact_digest,
                )
            }
        ),
        signature_subject=SUBJECT,
        public_keys={_key_id(public): base64.b64encode(public).decode("ascii")},
        supported_protocols=frozenset({args.protocol_version}),
    )
    for os_name in args.supported_os:
        for architecture in args.supported_arch:
            verdict = release.verify(
                manifest,
                policy,
                known_sequence=0,
                observed_digest=digest,
                observed_size=size,
                platform=f"{os_name}/{architecture}",
            )
            if not verdict.accepted:
                raise ValueError(
                    "generated manifest failed verification: "
                    + ", ".join(item.code for item in verdict.refusals)
                )
    payload = (release.serialize_manifest(manifest) + "\n").encode("utf-8")
    _write_exclusive(args.output, payload, 0o644)
    return {
        "manifest": str(args.output.resolve(strict=False)),
        "manifest_digest": release.manifest_identity(manifest),
        "artifact_digest": digest,
        "artifact_size": size,
        "key_id": manifest.signing_key,
        "public_key": base64.b64encode(public).decode("ascii"),
        "sequence": manifest.sequence,
    }


def verify(args: argparse.Namespace) -> dict[str, object]:
    manifest = release.parse_manifest(args.manifest.read_text("utf-8"))
    digest, size = release.artifact_identity(args.artifact)
    # Same self-consistency check as `sign`, against a manifest somebody else
    # produced: it answers "is this manifest well formed and correctly signed by
    # the key I named", not "may this machine install it". The second question
    # is answered only by the pinned policy, through `provider trust`.
    policy = release.TrustPolicy(
        schema_version=release.POLICY_SCHEMA_VERSION,
        policy_id=POLICY_ID,
        allowed_publishers=frozenset({manifest.publisher}),
        allowed_keys=frozenset({args.key_id}),
        allowed_repositories=frozenset({manifest.repository}),
        pinned_releases=frozenset(
            {
                release.PinnedRelease(
                    provider_id=manifest.provider_id,
                    repository=manifest.repository,
                    artifact_digest=manifest.artifact_digest,
                )
            }
        ),
        signature_subject=SUBJECT,
        public_keys={args.key_id: args.public_key},
        supported_protocols=frozenset({manifest.protocol_version}),
    )
    verdict = release.verify(
        manifest,
        policy,
        known_sequence=0,
        observed_digest=digest,
        observed_size=size,
        platform=args.platform,
    )
    if not verdict.accepted:
        raise ValueError("manifest refused: " + ", ".join(item.code for item in verdict.refusals))
    return {
        "accepted": True,
        "manifest_digest": release.manifest_identity(manifest),
        "artifact_digest": digest,
        "sequence": manifest.sequence,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "keygen":
            result = generate(args.private_key)
        elif args.command == "sign":
            result = sign(args)
        else:
            result = verify(args)
    except (OSError, ValueError, TypeError, CliFailure) as error:
        print(f"provider_release.py: ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
