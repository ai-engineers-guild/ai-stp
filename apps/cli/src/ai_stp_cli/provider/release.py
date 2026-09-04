"""Provider release trust, anti-rollback and key recovery (`#172`).

`provider-release.md` and `SPEC-008` REQ-811/REQ-812 in executable form. A
release is accepted only against a policy that was already on this machine —
nothing inside a downloaded manifest widens what that machine will accept, which
is the whole point of pinning a policy rather than reading one.

**A signature is not trust.** `REQ-811` asks for publisher, source, digest and
sequence as well, and the contract says plainly that the mere presence of some
signature is not enough. Every one of them is a separate refusal here, because a
release that fails four of them and passes one is not four fifths trustworthy.

**Rollback is refused, recovery is chosen.** A lower sequence is not accepted
because it is signed; it is accepted only as an explicit recovery to a version
this machine verified before. That distinction is what makes an anti-rollback
counter worth keeping: a counter that any signed artifact can lower is a counter
that records nothing.

**Revocation blocks installs, not running targets.** `REQ-812` is explicit that
a revoked key stops new installs and updates without deleting anything already
in use. Nothing in this module removes a target, and there is no argument shape
that lets it.
"""

import base64
import binascii
import hashlib
import json
import platform
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal, NoReturn, cast

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from ai_stp_cli.errors import CliFailure
from ai_stp_foundation.canonical import JsonValue, canonize
from ai_stp_foundation.digests import is_digest

#: The policy schema this build understands. A policy from a future schema is
#: refused rather than read partially: a trust rule half-applied is worse than
#: none, because it looks like a decision somebody made.
#:
#: Schema 2 binds each pinned release to the provider and repository that may
#: present it. Schema 1 pinned bare digests, and a build that enforces the
#: binding cannot read one: it would have to invent which provider each digest
#: belongs to, and inventing a trust anchor is the failure this module exists to
#: prevent. So a v1 policy is refused rather than upgraded in place.
POLICY_SCHEMA_VERSION: Final[int] = 2

#: The pinned policy shipped beside this module.
POLICY_FILE: Final[str] = "provider-policy.toml"

POLICY_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "policy_id",
        "signature_subject",
        "minimum_sequence",
        "allowed_publishers",
        "allowed_repositories",
        "allowed_keys",
        "public_keys",
        "revoked_keys",
        "supported_protocols",
        "releases",
    }
)
OPTIONAL_POLICY_FIELDS: Final[frozenset[str]] = frozenset(
    {"verified_publishers", "build_attestations", "index_publishers"}
)
#: What one pinned release names. The digest alone would allow a signed manifest
#: to present one provider's approved bytes as another provider's release, and
#: the provider is the only writer of final harness state — so the bytes are
#: pinned together with who may deliver them, not on their own.
PINNED_RELEASE_FIELDS: Final[frozenset[str]] = frozenset(
    {"provider_id", "repository", "artifact_digest"}
)

#: Every reason a release is refused, closed by `provider-release.md`.
REFUSALS: Final[frozenset[str]] = frozenset(
    {
        "policy_schema_unsupported",
        "policy_id_mismatch",
        "publisher_not_allowed",
        "key_unknown",
        "key_revoked",
        "repository_not_allowed",
        "signature_missing",
        "signature_subject_mismatch",
        "signature_invalid",
        "key_material_invalid",
        "artifact_reference_floating",
        "release_not_pinned",
        "digest_mismatch",
        "size_mismatch",
        "platform_unsupported",
        "protocol_unsupported",
        "sequence_rollback",
        "recovery_artifact_unverified",
        "sequence_below_minimum",
    }
)

#: An address that names no exact artifact. `provider-release.md` forbids both by
#: name: a floating reference means two machines install different bytes from
#: one manifest, which is the same failure a floating dependency causes and for
#: the same reason.
FLOATING_MARKERS: Final[tuple[str, ...]] = ("latest", "main", "master", "head")


@dataclass(frozen=True)
class PinnedRelease:
    """Exact provider bytes this machine will install, and who may deliver them.

    All three fields together are the anchor. A digest on its own says which
    bytes are approved but not as what: the same approved executable presented
    under another `provider_id` would install one harness's provider while
    claiming to be another's, and the manifest carrying that claim can be
    perfectly signed. Binding closes that without asking the signature to mean
    more than it does.
    """

    provider_id: str
    repository: str
    artifact_digest: str


@dataclass(frozen=True)
class BuildAttestationRule:
    repository: str
    signer_workflow: str
    verified_publisher: bool = False


@dataclass(frozen=True)
class IndexPublisherRule:
    """One PyPI project whose PEP 740 publisher triple this machine will bind."""

    pypi_project: str
    repository: str
    workflow: str
    environment: str
    verified_publisher: bool = False


@dataclass(frozen=True)
class TrustPolicy:
    """What this machine will accept, pinned locally and never widened.

    Held as sets of allowed values rather than as rules to evaluate: a policy
    that computed its own answers could be argued with by a manifest, and this
    one cannot be. During a key rotation both keys sit in `allowed_keys` at
    once — that overlap is the rotation, and without it every machine that has
    not updated its policy stops accepting releases.
    """

    schema_version: int
    policy_id: str
    allowed_publishers: frozenset[str]
    allowed_keys: frozenset[str]
    allowed_repositories: frozenset[str]

    #: Exact releases this machine may install. Required rather than defaulted,
    #: and empty means nothing is installable: a list of approved bytes that
    #: approves everything when left empty is not a list anybody can rely on,
    #: and the honest reading of "this machine pins no release" is that it has
    #: no release to install, not that any release will do.
    pinned_releases: frozenset[PinnedRelease]

    #: What a signature must be over. A signature over something else is a valid
    #: signature of the wrong thing, which is exactly how a valid signature ends
    #: up meaning nothing.
    signature_subject: str
    verified_publishers: frozenset[str] = frozenset()
    build_attestations: Mapping[str, BuildAttestationRule] = field(
        default_factory=lambda: MappingProxyType({})
    )
    index_publishers: Mapping[str, IndexPublisherRule] = field(
        default_factory=lambda: MappingProxyType({})
    )
    public_keys: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    revoked_keys: frozenset[str] = frozenset()
    minimum_sequence: int = 0
    supported_protocols: frozenset[int] = frozenset({1})


@dataclass(frozen=True)
class ReleaseManifest:
    """One provider release, as its manifest describes it."""

    provider_id: str
    provider_version: str
    protocol_version: int
    repository: str
    commit: str
    license: str
    artifact_url: str
    artifact_size: int
    artifact_digest: str
    entry_point: str
    supported_os: frozenset[str]
    supported_arch: frozenset[str]
    sequence: int
    policy_id: str
    publisher: str
    signing_key: str
    signature_subject: str
    signature: str


@dataclass(frozen=True)
class Refusal:
    """One reason this release is not acceptable."""

    code: str
    summary: str
    details: dict[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True)
class Verdict:
    """Whether a release may be installed, and every reason it may not."""

    accepted: bool
    refusals: tuple[Refusal, ...]

    #: The sequence this machine should remember afterwards. Unchanged when the
    #: release is refused: a rejected release must not move the counter, or
    #: refusing one would make the next rollback easier.
    next_minimum_sequence: int
    trust_level: Literal["verified_publisher", "signed", "unverified"] = "unverified"


def signed_trust_level(
    manifest: ReleaseManifest, policy: TrustPolicy
) -> Literal["verified_publisher", "signed"]:
    """Name the accepted signed path without treating a remote badge as byte evidence."""
    return "verified_publisher" if manifest.publisher in policy.verified_publishers else "signed"


def verify(
    manifest: ReleaseManifest,
    policy: TrustPolicy,
    *,
    known_sequence: int,
    observed_digest: str = "",
    observed_size: int = 0,
    platform: str = "",
    recovery_requested: bool = False,
    recovery_to_verified: bool = False,
) -> Verdict:
    """Decide one release against one pinned policy.

    Every check runs. A release that fails four of them and passes one is not
    four fifths trustworthy, and somebody fixing a release deserves the whole
    list rather than whichever failure came first.

    `observed_digest` and `observed_size` describe the artifact actually
    fetched. Left empty they are not compared — verifying a manifest before
    downloading anything is a legitimate step, and pretending to have checked
    bytes nobody has would be worse than saying so.
    """
    refusals: list[Refusal] = []

    if policy.schema_version != POLICY_SCHEMA_VERSION:
        # Nothing else is checked: a policy this build cannot read fully is a
        # policy whose other fields may not mean what they appear to.
        return Verdict(
            accepted=False,
            refusals=(
                Refusal(
                    "policy_schema_unsupported",
                    "this build does not read that trust policy schema",
                    {"found": str(policy.schema_version), "reads": str(POLICY_SCHEMA_VERSION)},
                ),
            ),
            next_minimum_sequence=known_sequence,
            trust_level="unverified",
        )

    refusals.extend(_publisher(manifest, policy))
    refusals.extend(_signature(manifest, policy))
    refusals.extend(_artifact(manifest, observed_digest, observed_size))
    refusals.extend(_pinned(manifest, policy))
    refusals.extend(_platform(manifest, policy, platform))
    refusals.extend(
        _sequence(
            manifest,
            policy,
            known_sequence,
            recovery_requested=recovery_requested,
            recovery_verified=recovery_to_verified,
        )
    )

    refusals.sort(key=lambda item: item.code)
    accepted = not refusals
    return Verdict(
        accepted=accepted,
        refusals=tuple(refusals),
        next_minimum_sequence=(
            max(known_sequence, manifest.sequence) if accepted else known_sequence
        ),
        trust_level=signed_trust_level(manifest, policy) if accepted else "unverified",
    )


def verify_attested(
    manifest: ReleaseManifest,
    policy: TrustPolicy,
    *,
    known_sequence: int,
    observed_digest: str,
    observed_size: int,
    platform: str,
) -> Verdict:
    """Verify the manifest facts that remain independent of build attestation."""
    refusals: list[Refusal] = []
    if policy.schema_version != POLICY_SCHEMA_VERSION:
        refusals.append(
            Refusal(
                "policy_schema_unsupported",
                "this build does not read that trust policy schema",
            )
        )
    if manifest.policy_id != policy.policy_id:
        refusals.append(Refusal("policy_id_mismatch", "the manifest names another policy"))
    if manifest.repository not in policy.build_attestations:
        refusals.append(
            Refusal("repository_not_allowed", "the repository has no pinned build identity")
        )
    refusals.extend(_artifact(manifest, observed_digest, observed_size))
    refusals.extend(_platform(manifest, policy, platform))
    refusals.extend(
        _sequence(
            manifest,
            policy,
            known_sequence,
            recovery_requested=False,
            recovery_verified=False,
        )
    )
    refusals.sort(key=lambda item: item.code)
    return Verdict(
        accepted=not refusals,
        refusals=tuple(refusals),
        next_minimum_sequence=(
            max(known_sequence, manifest.sequence) if not refusals else known_sequence
        ),
        trust_level="unverified",
    )


def _publisher(manifest: ReleaseManifest, policy: TrustPolicy) -> list[Refusal]:
    """Who published it, with which key, from where.

    Revocation is checked before membership. A revoked key is usually still in
    the allowed set — that is what revoking means — and checking membership
    first would accept it.
    """
    found: list[Refusal] = []
    if manifest.policy_id != policy.policy_id:
        found.append(
            Refusal(
                "policy_id_mismatch",
                "this release names a trust policy other than the pinned policy",
                {"found": manifest.policy_id, "required": policy.policy_id},
            )
        )
    if manifest.publisher not in policy.allowed_publishers:
        found.append(
            Refusal(
                "publisher_not_allowed",
                "this publisher is not in the pinned policy",
                {"publisher": manifest.publisher},
            )
        )
    if manifest.signing_key in policy.revoked_keys:
        found.append(
            Refusal(
                "key_revoked",
                "this signing key is revoked; existing targets keep running",
                {"key": manifest.signing_key},
            )
        )
    elif (
        manifest.signing_key not in policy.allowed_keys
        or manifest.signing_key not in policy.public_keys
    ):
        found.append(
            Refusal(
                "key_unknown",
                "this signing key and its public material are not in the pinned policy",
                {"key": manifest.signing_key},
            )
        )
    if manifest.repository not in policy.allowed_repositories:
        found.append(
            Refusal(
                "repository_not_allowed",
                "this repository is not in the pinned policy",
                {"repository": manifest.repository},
            )
        )
    return found


def _signature(manifest: ReleaseManifest, policy: TrustPolicy) -> list[Refusal]:
    """A signature, and a signature over the right thing.

    Two codes because they are two failures. A missing signature is an unsigned
    release; a signature over the wrong subject is a valid signature of
    something else, which is precisely how a valid signature comes to mean
    nothing at all.
    """
    found: list[Refusal] = []
    if not manifest.signature_subject or not manifest.signature:
        found.append(
            Refusal(
                "signature_missing",
                "this release carries no verifiable signature and subject",
                {"provider_id": manifest.provider_id},
            )
        )
        return found
    if manifest.signature_subject != policy.signature_subject:
        found.append(
            Refusal(
                "signature_subject_mismatch",
                "the signature covers something other than what the policy requires",
                {"found": manifest.signature_subject, "required": policy.signature_subject},
            )
        )

    material = policy.public_keys.get(manifest.signing_key)
    if material is None:
        # `_publisher` reports `key_unknown`. Do not invent a second diagnosis
        # for a key the policy never pinned.
        return found
    try:
        public_bytes = base64.b64decode(material, validate=True)
        public_key = VerifyKey(public_bytes)
    except (ValueError, binascii.Error):
        found.append(
            Refusal(
                "key_material_invalid",
                "the pinned signing key or release signature is not valid Ed25519 material",
                {"key": manifest.signing_key},
            )
        )
        return found
    try:
        signature = base64.b64decode(manifest.signature, validate=True)
    except (ValueError, binascii.Error):
        found.append(
            Refusal(
                "signature_invalid",
                "the release signature is not valid base64 Ed25519 material",
                {"key": manifest.signing_key},
            )
        )
        return found
    try:
        public_key.verify(signature_payload(manifest), signature)
    except (BadSignatureError, TypeError, ValueError):
        found.append(
            Refusal(
                "signature_invalid",
                "the release signature does not verify over the canonical manifest",
                {"key": manifest.signing_key},
            )
        )
    return found


def signature_payload(manifest: ReleaseManifest) -> bytes:
    """Canonical signed bytes: every manifest field except the signature."""
    return canonize(
        {
            "domain": manifest.signature_subject,
            "manifest": _manifest_document(manifest, include_signature=False),
        }
    )


def _manifest_document(
    manifest: ReleaseManifest, *, include_signature: bool
) -> dict[str, JsonValue]:
    document: dict[str, JsonValue] = {
        "provider_id": manifest.provider_id,
        "provider_version": manifest.provider_version,
        "protocol_version": manifest.protocol_version,
        "repository": manifest.repository,
        "commit": manifest.commit,
        "license": manifest.license,
        "artifact_url": manifest.artifact_url,
        "artifact_size": manifest.artifact_size,
        "artifact_digest": manifest.artifact_digest,
        "entry_point": manifest.entry_point,
        "supported_os": cast(list[JsonValue], sorted(manifest.supported_os)),
        "supported_arch": cast(list[JsonValue], sorted(manifest.supported_arch)),
        "sequence": manifest.sequence,
        "policy_id": manifest.policy_id,
        "publisher": manifest.publisher,
        "signing_key": manifest.signing_key,
        "signature_subject": manifest.signature_subject,
    }
    if include_signature:
        document["signature"] = manifest.signature
    return document


def serialize_manifest(manifest: ReleaseManifest) -> str:
    """Canonical JSON persisted inside an immutable installation plan."""
    return canonize(_manifest_document(manifest, include_signature=True)).decode("utf-8")


def manifest_identity(manifest: ReleaseManifest) -> str:
    """Digest of every signed-manifest field, including its exact signature."""
    payload = serialize_manifest(manifest).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def parse_manifest(text: str) -> ReleaseManifest:
    """Read a closed release manifest without supplying security defaults."""
    try:
        parsed = json.loads(text, object_pairs_hook=_unique_json_object)
    except ValueError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the release manifest is not valid JSON",
            details={"detail": str(error)},
        ) from error

    if not isinstance(parsed, dict):
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the release manifest must be one JSON object",
            details={"field": "<root>"},
        )
    document = cast(dict[str, object], parsed)

    wanted = (
        "provider_id",
        "provider_version",
        "protocol_version",
        "repository",
        "commit",
        "license",
        "artifact_url",
        "artifact_size",
        "artifact_digest",
        "entry_point",
        "supported_os",
        "supported_arch",
        "sequence",
        "policy_id",
        "publisher",
        "signing_key",
        "signature_subject",
        "signature",
    )
    missing = [name for name in wanted if name not in document]
    if missing:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the release manifest is missing required fields",
            details={"missing": ", ".join(missing)},
        )
    unknown = sorted(set(document) - set(wanted))
    if unknown:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the release manifest contains fields this schema does not define",
            details={"unknown": ", ".join(unknown)},
        )

    return ReleaseManifest(
        provider_id=_manifest_string(document, "provider_id"),
        provider_version=_manifest_string(document, "provider_version"),
        protocol_version=_manifest_integer(document, "protocol_version", minimum=1),
        repository=_manifest_string(document, "repository"),
        commit=_manifest_string(document, "commit"),
        license=_manifest_string(document, "license"),
        artifact_url=_manifest_string(document, "artifact_url"),
        artifact_size=_manifest_integer(document, "artifact_size", minimum=0),
        artifact_digest=_manifest_string(document, "artifact_digest"),
        entry_point=_manifest_string(document, "entry_point"),
        supported_os=_manifest_string_set(document, "supported_os"),
        supported_arch=_manifest_string_set(document, "supported_arch"),
        sequence=_manifest_integer(document, "sequence", minimum=0),
        policy_id=_manifest_string(document, "policy_id"),
        publisher=_manifest_string(document, "publisher"),
        signing_key=_manifest_string(document, "signing_key"),
        signature_subject=_manifest_string(document, "signature_subject", empty=True),
        signature=_manifest_string(document, "signature", empty=True),
    )


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build one JSON object while refusing duplicate names at any depth."""
    document: dict[str, object] = {}
    for name, value in pairs:
        if name in document:
            raise ValueError(f"duplicate JSON field: {name}")
        document[name] = value
    return document


def _manifest_string(document: Mapping[str, object], name: str, *, empty: bool = False) -> str:
    value = document[name]
    if not isinstance(value, str) or (not empty and not value):
        _manifest_shape(name, "a non-empty string" if not empty else "a string")
    return value


def _manifest_integer(document: Mapping[str, object], name: str, *, minimum: int) -> int:
    value = document[name]
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _manifest_shape(name, f"an integer greater than or equal to {minimum}")
    return value


def _manifest_string_set(document: Mapping[str, object], name: str) -> frozenset[str]:
    value = document[name]
    if not isinstance(value, list):
        _manifest_shape(name, "an array of unique non-empty strings")
    items = cast(list[object], value)
    if any(not isinstance(item, str) or not item for item in items) or len(items) != len(
        set(items)
    ):
        _manifest_shape(name, "an array of unique non-empty strings")
    return frozenset(cast(list[str], items))


def _manifest_shape(name: str, expected: str) -> NoReturn:
    raise CliFailure(
        "AI_STP_VALIDATION_ERROR",
        "the release manifest field has the wrong shape",
        details={"field": name, "expected": expected},
    )


def current_platform() -> str:
    """OS and architecture this process is running on, as the release contract names them."""
    system = platform.system().casefold()
    os_name = "macos" if system == "darwin" else system
    machine = platform.machine().casefold()
    architecture = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return f"{os_name}/{architecture}"


def artifact_identity(path: Path) -> tuple[str, int]:
    """SHA-256 and size of one exact regular provider artifact."""
    if path.is_symlink() or not path.is_file():
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the provider artifact must be one existing regular file, not a symlink",
            details={"artifact": str(path)},
        )
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return f"sha256:{digest.hexdigest()}", size


def _artifact(manifest: ReleaseManifest, digest: str, size: int) -> list[Refusal]:
    found: list[Refusal] = []
    lowered = manifest.artifact_url.casefold()
    if not is_digest(manifest.artifact_digest) or any(
        mark in lowered.rsplit("/", 1)[-1] for mark in FLOATING_MARKERS
    ):
        found.append(
            Refusal(
                "artifact_reference_floating",
                "this release does not name exact bytes at an exact address",
                {"url": manifest.artifact_url, "digest": manifest.artifact_digest},
            )
        )
    if digest and digest != manifest.artifact_digest:
        found.append(
            Refusal(
                "digest_mismatch",
                "the fetched artifact is not the one this manifest names",
                {"declared": manifest.artifact_digest, "fetched": digest},
            )
        )
    if size and size != manifest.artifact_size:
        found.append(
            Refusal(
                "size_mismatch",
                "the fetched artifact is not the size this manifest names",
                {"declared": str(manifest.artifact_size), "fetched": str(size)},
            )
        )
    return found


def _pinned(manifest: ReleaseManifest, policy: TrustPolicy) -> list[Refusal]:
    """Refuse a release this machine never approved, however well it is signed.

    This is the check the signature cannot make. A signature proves the manifest
    came from the holder of an allowed key and was not altered afterwards; it
    says nothing about whether anybody decided to install *this* release. Those
    are different questions, and only the second one is answered by a list that
    was already on the machine before the manifest arrived.

    It matters most exactly when the other checks are passing: an erroneous
    publication, or a signing key in the wrong hands, produces a release that
    satisfies publisher, repository, key, bytes, platform and sequence. Without
    this check the approved-release list is a comment.
    """
    candidate = PinnedRelease(
        provider_id=manifest.provider_id,
        repository=manifest.repository,
        artifact_digest=manifest.artifact_digest,
    )
    if candidate in policy.pinned_releases:
        return []
    return [
        Refusal(
            "release_not_pinned",
            "this machine has not pinned that release for that provider",
            {
                "provider_id": manifest.provider_id,
                "repository": manifest.repository,
                "digest": manifest.artifact_digest,
            },
        )
    ]


#: The musl dynamic loader, which Alpine and other musl distributions install
#: under this name. Positive evidence rather than an absence: a check that
#: refused whenever glibc could not be *confirmed* would refuse on every system
#: whose detection this code has not met.
_MUSL_LOADER: Final[str] = "ld-musl-"


def _runs_musl() -> bool:
    """Whether this Linux runs musl rather than glibc.

    Nothing in protocol v3 can express this. `provider-info.schema.json`
    requires `supported_os` and `supported_arch` and has no libc field, both
    are open arrays of free strings so `linux-musl` would validate, and the
    match key is split at exactly one `/` — there is no third axis for a
    spelling to land in. So the answer cannot come from a manifest and has to
    be read from the machine.

    Measured on the publishing side rather than assumed: `0.0.40` ships
    `…-x86_64-unknown-linux-gnu`, dynamically linked against `libc.so.6` with
    interpreter `/lib64/ld-linux-x86-64.so.2`, and the release carries no musl
    asset at all. This program is Python and runs on Alpine perfectly well, so
    without this the sequence there is: resolve the platform, accept the
    release, fetch it, and fail to execute with a dynamic-loader error naming
    neither libc nor the actual problem.

    Refusing on this reading is safe in a way that *selecting* on it would not
    be. It only ever turns a confusing failure into a true sentence; it never
    picks an artifact.
    """
    if platform.system().casefold() != "linux":
        return False
    library, _ = platform.libc_ver()
    if "musl" in library.casefold():
        return True
    try:
        return any(
            any(directory.glob(f"{_MUSL_LOADER}*"))
            for directory in (Path("/lib"), Path("/usr/lib"))
            if directory.is_dir()
        )
    except OSError:  # pragma: no cover - an unreadable /lib is not a musl proof
        return False


def _platform(manifest: ReleaseManifest, policy: TrustPolicy, platform: str) -> list[Refusal]:
    found: list[Refusal] = []
    if manifest.protocol_version not in policy.supported_protocols:
        found.append(
            Refusal(
                "protocol_unsupported",
                "this release speaks a protocol version the policy does not allow",
                {"protocol": str(manifest.protocol_version)},
            )
        )
    if platform:
        system, _, machine = platform.partition("/")
        if system not in manifest.supported_os or machine not in manifest.supported_arch:
            found.append(
                Refusal(
                    "platform_unsupported",
                    "this release does not support this platform",
                    {"platform": platform},
                )
            )
        elif system == "linux" and _runs_musl():
            # The manifest said yes and could not have said otherwise: v3 has
            # no libc field, so `linux/x86_64` matches a glibc-only release
            # exactly as well here as on Debian. The refusal has to come from
            # the machine, and it names the axis the manifest cannot carry so
            # the answer is actionable rather than merely negative.
            found.append(
                Refusal(
                    "platform_unsupported",
                    "this release is linked against glibc and this system runs musl; "
                    "protocol v3 has no field for a C library, so the manifest cannot "
                    "say so and this is read from the machine",
                    {"platform": platform, "libc": "musl"},
                )
            )
    return found


def _sequence(
    manifest: ReleaseManifest,
    policy: TrustPolicy,
    known: int,
    *,
    recovery_requested: bool,
    recovery_verified: bool,
) -> list[Refusal]:
    """Anti-rollback, and the one door through it.

    A lower sequence is refused because it is lower, not because it is
    suspicious — and it is accepted only as an explicit recovery to a version
    this machine verified before. A counter any signed artifact can lower is a
    counter that records nothing.

    The policy floor is separate from the machine's own counter: a policy can
    raise the floor for everyone after a compromise, and a machine that never
    installed anything still refuses everything below it.
    """
    found: list[Refusal] = []
    if manifest.sequence < policy.minimum_sequence:
        found.append(
            Refusal(
                "sequence_below_minimum",
                "this release is older than the policy's minimum sequence",
                {"sequence": str(manifest.sequence), "minimum": str(policy.minimum_sequence)},
            )
        )
    if manifest.sequence < known:
        if not recovery_requested:
            found.append(
                Refusal(
                    "sequence_rollback",
                    (
                        "this release is older than one already installed; "
                        "recovery is a separate decision"
                    ),
                    {"sequence": str(manifest.sequence), "installed": str(known)},
                )
            )
        elif not recovery_verified:
            found.append(
                Refusal(
                    "recovery_artifact_unverified",
                    "recovery requires this exact release digest in local verified history",
                    {"sequence": str(manifest.sequence)},
                )
            )
    return found


def load_policy(text: str) -> TrustPolicy:
    """Read the pinned policy, refusing anything under-specified.

    Every refusal names the field. A policy is edited by a person adding a key
    after a rotation, and "invalid policy" without a field name is a message
    that makes them guess at the one thing they must not guess at.
    """
    return _policy(_policy_document(text))


def pinned_policy() -> TrustPolicy:
    """The policy this build ships, read from the file beside this module."""
    return load_policy(
        resources.files("ai_stp_cli").joinpath("provider", POLICY_FILE).read_text("utf-8")
    )


def _policy_document(text: str) -> dict[str, object]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise CliFailure(
            "AI_STP_VALIDATION_ERROR",
            "the provider trust policy is not valid TOML",
            details={"detail": str(error)},
        ) from error


def _policy(document: dict[str, object]) -> TrustPolicy:
    unknown = sorted(set(document) - POLICY_FIELDS - OPTIONAL_POLICY_FIELDS)
    if unknown:
        _policy_failure("unknown_fields", f"unknown fields: {', '.join(unknown)}")
    missing = sorted(POLICY_FIELDS - set(document))
    if missing:
        _policy_failure(missing[0], "the field is required")

    allowed_keys = _names(document, "allowed_keys")
    public_keys = _public_keys(document)
    missing_material = sorted(allowed_keys - set(public_keys))
    if missing_material:
        _policy_failure(
            "public_keys",
            f"allowed keys have no pinned public material: {', '.join(missing_material)}",
        )
    allowed_repositories = _names(document, "allowed_repositories")
    pins = _pinned_releases(document)
    stray = sorted({pin.repository for pin in pins} - allowed_repositories)
    if stray:
        # A pin naming a repository the policy does not allow cannot ever be
        # accepted, so it is an editing mistake rather than a stricter policy —
        # and a rule that silently never fires is the shape this whole change
        # exists to remove.
        _policy_failure(
            "releases",
            f"pinned releases name repositories the policy does not allow: {', '.join(stray)}",
        )
    return TrustPolicy(
        schema_version=_policy_integer(document, "schema_version", minimum=1),
        policy_id=_policy_string(document, "policy_id"),
        allowed_publishers=_names(document, "allowed_publishers"),
        verified_publishers=(
            _names(document, "verified_publishers")
            if "verified_publishers" in document
            else frozenset()
        ),
        build_attestations=MappingProxyType(_build_attestations(document)),
        index_publishers=MappingProxyType(_index_publishers(document)),
        allowed_keys=allowed_keys,
        allowed_repositories=allowed_repositories,
        pinned_releases=frozenset(pins),
        signature_subject=_policy_string(document, "signature_subject"),
        public_keys=MappingProxyType(public_keys),
        revoked_keys=_names(document, "revoked_keys"),
        minimum_sequence=_policy_integer(document, "minimum_sequence", minimum=0),
        supported_protocols=_protocols(document),
    )


def _policy_failure(field: str, detail: str) -> NoReturn:
    raise CliFailure(
        "AI_STP_VALIDATION_ERROR",
        f"the provider trust policy has an invalid {field}",
        details={"field": field, "detail": detail},
    )


def _policy_string(document: dict[str, object], field_name: str) -> str:
    held = document.get(field_name)
    if not isinstance(held, str) or not held:
        _policy_failure(field_name, "expected one non-empty string")
    return held


def _policy_integer(document: dict[str, object], field_name: str, *, minimum: int) -> int:
    held = document.get(field_name)
    if isinstance(held, bool) or not isinstance(held, int) or held < minimum:
        _policy_failure(field_name, f"expected an integer greater than or equal to {minimum}")
    return held


def _names(document: dict[str, object], field_name: str) -> frozenset[str]:
    held = document.get(field_name)
    if not isinstance(held, list):
        _policy_failure(field_name, "expected a list of non-empty strings")
    raw_values = cast(list[object], held)
    if not all(isinstance(item, str) and item for item in raw_values):
        _policy_failure(field_name, "expected a list of non-empty strings")
    values = cast(list[str], raw_values)
    if len(values) != len(set(values)):
        _policy_failure(field_name, "duplicate values are not allowed")
    return frozenset(values)


def _public_keys(document: dict[str, object]) -> dict[str, str]:
    held = document.get("public_keys")
    if not isinstance(held, dict):
        _policy_failure("public_keys", "expected non-empty string key ids and material")
    raw_keys = cast(dict[object, object], held)
    if not all(
        isinstance(key, str) and key and isinstance(value, str) and value
        for key, value in raw_keys.items()
    ):
        _policy_failure("public_keys", "expected non-empty string key ids and material")
    return cast(dict[str, str], raw_keys)


def _protocols(document: dict[str, object]) -> frozenset[int]:
    held = document.get("supported_protocols")
    if not isinstance(held, list):
        _policy_failure("supported_protocols", "expected positive integer versions")
    raw_values = cast(list[object], held)
    if not all(
        not isinstance(item, bool) and isinstance(item, int) and item >= 1 for item in raw_values
    ):
        _policy_failure("supported_protocols", "expected positive integer versions")
    values = cast(list[int], raw_values)
    if len(values) != len(set(values)):
        _policy_failure("supported_protocols", "duplicate versions are not allowed")
    return frozenset(values)


def _build_attestations(document: dict[str, object]) -> dict[str, BuildAttestationRule]:
    held = document.get("build_attestations", [])
    if not isinstance(held, list):
        _policy_failure("build_attestations", "expected a list of repository rules")
    rules: dict[str, BuildAttestationRule] = {}
    for index, raw in enumerate(cast(list[object], held)):
        if not isinstance(raw, dict):
            _policy_failure("build_attestations", f"rule {index} must be a table")
        item = cast(dict[str, object], raw)
        if set(item) != {"repository", "signer_workflow", "verified_publisher"}:
            _policy_failure(
                "build_attestations",
                f"rule {index} must name repository, signer_workflow and verified_publisher",
            )
        repository = item.get("repository")
        workflow = item.get("signer_workflow")
        verified = item.get("verified_publisher")
        if (
            not isinstance(repository, str)
            or not repository
            or not isinstance(workflow, str)
            or not workflow
            or not isinstance(verified, bool)
        ):
            _policy_failure("build_attestations", f"rule {index} has the wrong shape")
        if repository in rules:
            _policy_failure("build_attestations", f"duplicate repository {repository}")
        rules[repository] = BuildAttestationRule(repository, workflow, verified)
    return rules


def _index_publishers(document: dict[str, object]) -> dict[str, IndexPublisherRule]:
    held = document.get("index_publishers", [])
    if not isinstance(held, list):
        _policy_failure("index_publishers", "expected a list of project rules")
    rules: dict[str, IndexPublisherRule] = {}
    expected = {"pypi_project", "repository", "workflow", "environment", "verified_publisher"}
    for index, raw in enumerate(cast(list[object], held)):
        if not isinstance(raw, dict):
            _policy_failure("index_publishers", f"rule {index} must be a table")
        item = cast(dict[str, object], raw)
        if set(item) != expected:
            _policy_failure(
                "index_publishers",
                f"rule {index} must name pypi_project, repository, workflow, "
                "environment and verified_publisher",
            )
        project = item.get("pypi_project")
        repository = item.get("repository")
        workflow = item.get("workflow")
        environment = item.get("environment")
        verified = item.get("verified_publisher")
        if (
            not isinstance(project, str)
            or not project
            or not isinstance(repository, str)
            or not repository
            or not isinstance(workflow, str)
            or not workflow
            or not isinstance(environment, str)
            or not environment
            or not isinstance(verified, bool)
        ):
            _policy_failure("index_publishers", f"rule {index} has the wrong shape")
        if project in rules:
            _policy_failure("index_publishers", f"duplicate project {project}")
        rules[project] = IndexPublisherRule(
            pypi_project=project,
            repository=repository,
            workflow=workflow,
            environment=environment,
            verified_publisher=verified,
        )
    return rules


def _pinned_releases(document: dict[str, object]) -> tuple[PinnedRelease, ...]:
    """Read the exact approved releases, refusing anything under-specified.

    Order is preserved so the reported policy reads the way the file does; the
    decision itself uses a set, because a pin is not more approved for being
    listed first.
    """
    expected = ", ".join(sorted(PINNED_RELEASE_FIELDS))
    held = document.get("releases")
    if not isinstance(held, list):
        _policy_failure("releases", "expected a list of pinned release tables")
    pins: list[PinnedRelease] = []
    for index, raw_item in enumerate(cast(list[object], held)):
        if not isinstance(raw_item, dict):
            _policy_failure("releases", f"release {index} must contain exactly {expected}")
        item = cast(dict[str, object], raw_item)
        if set(item) != set(PINNED_RELEASE_FIELDS):
            _policy_failure("releases", f"release {index} must contain exactly {expected}")
        provider_id = item.get("provider_id")
        if not isinstance(provider_id, str) or not provider_id:
            _policy_failure("releases", f"release {index} names no provider")
        repository = item.get("repository")
        if not isinstance(repository, str) or not repository:
            _policy_failure("releases", f"release {index} names no repository")
        digest = item.get("artifact_digest")
        if not isinstance(digest, str) or not is_digest(digest):
            _policy_failure("releases", f"release {index} has no exact SHA-256 digest")
        pins.append(
            PinnedRelease(
                provider_id=provider_id,
                repository=repository,
                artifact_digest=digest,
            )
        )
    if len({pin.artifact_digest for pin in pins}) != len(pins):
        # Not merely a duplicate entry: one artifact approved under two
        # identities is the substitution the binding exists to refuse, written
        # into the policy itself.
        _policy_failure("releases", "duplicate artifact digests are not allowed")
    return tuple(pins)
