---
description: "Provider release manifest, trust, verification, and rollback protection."
last_verified: "2026-08-25"
---

# Provider release

## Manifest

The release manifest contains:

- `provider_id`, the provider version, and the protocol version;
- the exact public repository, commit, and license;
- the artifact address, size, and SHA-256;
- the entry point and supported systems and architectures;
- environment requirements;
- a monotonic sequence number;
- the trust policy identifier;
- `signing_key`, the signature subject, and the Ed25519 signature of the
  canonical manifest.

## Trust level

Machine output reports `provider_release_trust` as one of four values:

- `verified_publisher` — exact bytes are verified by a signature or build
  attestation, and the publisher is pinned as verified by local policy;
- `signed` — exact bytes and manifest are verified by an allowed Ed25519 key;
- `build_attested` — exact bytes are bound by a GitHub/Sigstore attestation to
  an allowed repository, source commit, and release workflow;
- `unverified` — no trusted path has completed.

A remote badge, publisher name, and managed workflow fields do not raise the
level without cryptographic verification of exact bytes. The compatibility
value `provider_release_trusted` equals
`provider_release_trust != unverified`.

The shipped policy marks `build_attestations` rules for
`NDDev-OpenNetwork/*-setup-system` as `verified_publisher`. After successful
GitHub attestation verification, the level becomes `verified_publisher`, not
`build_attested`. A manifest whose `repository` matches these rules is verified
through the attestation path; `provider-build-attestation` remains an explicit
form of the same choice. An empty `releases` list still installs nothing through
the Ed25519 path: OpenNetwork bytes are not added there.

## Trust policy

The client accepts a release only under locally pinned policy. The policy
defines the allowed publisher or key, repository, release process, signature
subject, schema version, minimum sequence, and exact list of approved releases.
A value from the downloaded manifest does not expand this list.

The current v2 schema uses an Ed25519 public key pinned by local policy under
the `signing_key` identifier. RFC 8785 bytes of all manifest fields except the
signature itself are signed within the `signature_subject` domain. The mere
presence of a signature string, key id, or a valid signature by an unknown key
is insufficient. Keyless attestation requires a separate versioned schema and
is not interpreted as v2.

Policy TOML is also a closed input: all v2 schema fields are required; unknown
fields, non-string names/values, a boolean in place of an integer, a negative
floor, duplicates, and an allowed key id without pinned public material are
rejected.

`releases` lists approved releases. Each entry contains exactly `provider_id`,
`repository`, and an exact SHA-256 `artifact_digest`; a floating or incorrectly
typed value does not become a trust anchor through type conversion. The digest
is pinned together with who may present it: the same approved bytes under
another `provider_id` would install one harness's provider under another's name,
and a manifest making that assertion may be impeccably signed. One digest cannot
belong to two entries, and an entry's `repository` MUST be included in
`allowed_repositories`.

Schema v1 pinned digests without this binding. A build that enforces the binding
does not read such a policy: it would have to invent which provider owns each
digest, and an invented trust anchor is exactly the failure this schema
prevents.

Manifest JSON is closed: the root MUST be an object, all fields are required,
unknown and duplicate names are prohibited, strings are not replaced by
numbers, a boolean is not accepted as an integer, and platform arrays contain
only unique, non-empty strings. Structural rejection occurs before signature
verification and provider execution.

## Verification

Before installation, the client verifies manifest canonicalization, signature,
source, hash, size, membership in the pinned release list, platform, protocol,
sequence, and revocation. The artifact is then unpacked into a new directory
under path and size limits and passes `provider-info` and diagnostics.

Membership is a separate check and is not established by the signature. A
signature proves that the manifest came from the holder of an allowed key and
has not changed since; it says nothing about whether anyone decided to install
this particular release. An erroneous publication and a signing key in another
party's hands produce a release that passes publisher, repository, key, bytes,
platform, and sequence checks. An empty list means there is nothing to install:
a list of approved bytes that approves everything when empty is not a
constraint.

## Provider without a signed release

Protocol v3 is installed from a release with a manifest: either Ed25519-signed
or attested for a repository in `build_attestations`. An `install plan` with
`protocol-version = 3` and no `provider-manifest` is rejected unless the caller
explicitly specifies `unverified-provider`. Subsequent actions name
`provider fetch` as the way to obtain a closed manifest when the publisher did
not supply one.

`provider fetch` materializes this JSON from attested bytes, the exact tag,
source commit, and executable `provider-info`. Sequence is encoded from the
exact semver tag `X.Y.Z` as `1_000_000 * X + 1_000 * Y + Z`; an optional `v`
prefix is removed, while the `latest` tag and prereleases are rejected.
`signing_key` equals `attested`, and the signature is empty: such a manifest
does not pass the Ed25519 path and is accepted only by `verify_attested`. This is
not a second trust anchor and does not add bytes to `releases`. The executable
is not run before successful GitHub attestation verification.

Installation with an unverified provider remains possible. Prohibiting it would
not remove the action, but would move it outside the tool where nobody records
it, and a person running a provider they have just built is not the threat for
which pinned policy exists. What changes is that this no longer happens by
default. The plan reports `provider_release_trusted` as `false`, and approval is
given against the plan digest that states this.

The requirement to name a release applies to the mutating path. `target
status`, `target diff` and `target backups` run the caller-named executable to
observe and install nothing, so a read without a manifest is not refused. The
trust a read runs under is nevertheless established the way a write establishes
it, in the writers' order: a `--provider-manifest` the caller names is verified
exactly as `install plan` verifies one; `--unverified-provider` is the
operator's decision and nothing is derived behind it; otherwise the release this
pair was last verified under counts when the named executable is its exact
bytes — the manifest the plan bound and the apply re-checked, read from the
journal. The pinned policy is re-read, so a release revoked since the install no
longer trusts the read; the build attestation is not re-run, because it is a
property of bytes that were attested at plan time and have not changed.

Protocols v1 and v2 predate the signed-release line and are unaffected by the
rule.

## Rollback protection

The client stores a monotonic floor and append-only history of exact
`provider_id + sequence + artifact_digest` in the local registry. The value is
not accepted from the CLI caller. An older release is rejected unless the user
chooses a separate confirmed recovery operation for an exact digest already
verified by this machine. A new digest at an old sequence does not become
recovery, and one sequence cannot be rebound to different bytes.

Such recovery is specified only by `--provider-release-recovery` together with
an exact `--provider-manifest`. The decision, canonical manifest, and its
signature are included in the immutable plan digest; ordinary `action=rollback`
applies to the target setup and does not relax the provider anti-rollback policy.

Before the provider's first execution, the trusted installation path verifies
the signature, policy identifier, membership in the pinned list, platform, and
exact executable bytes, preserves the canonical manifest within the plan
digest, and repeats policy and byte verification before `apply`. For an attested
release, the stored JSON response from
`gh attestation verify --format=json` is reverified with `gh --bundle` against
the extracted Sigstore bundle rather than against the GitHub CLI wrapper.
History advances atomically only together with operation state `verified`. A
history write failure rolls back `verified`, leaving the operation in
`applied_unverified`. The diagnostic manifest-verification command reads the
minimum permitted sequence but does not write it: merely reading a manifest is
not installation.

## Key rotation and revocation

Key rotation uses an overlap period in which the new policy trusts both the old
and new keys. Revocation blocks new installations and updates but does not
automatically remove active targets. Compromise requires a new policy, a list of
affected releases, and recovery instructions.

## Offline operation

Offline operation permits only a previously verified artifact from the local
cache that satisfies current policy and has not been revoked. The value `latest`
and a floating address are not used.

## Failures

The list is closed. Each failure has a stable code that does not change with the
message text:

| Code | When it occurs |
|---|---|
| `policy_schema_unsupported` | the policy schema version cannot be read by this build |
| `policy_id_mismatch` | the manifest refers to a policy line other than the locally pinned one |
| `publisher_not_allowed` | the publisher is not included in the pinned policy |
| `key_unknown` | the signing key is not included in the pinned policy |
| `key_revoked` | the key has been revoked |
| `repository_not_allowed` | the repository is not included in the pinned policy |
| `signature_missing` | the release does not carry a signature subject |
| `signature_subject_mismatch` | the signature covers something other than what the policy requires |
| `signature_invalid` | the signature cannot be decoded or does not verify over the canonical manifest |
| `key_material_invalid` | the pinned public key is not valid Ed25519 material |
| `artifact_reference_floating` | the artifact address or hash does not identify exact bytes |
| `release_not_pinned` | the release is not in the pinned list for this provider and repository |
| `digest_mismatch` | the downloaded artifact is not the artifact named by the manifest |
| `size_mismatch` | the downloaded artifact size does not match the manifest |
| `platform_unsupported` | the release does not support this system or architecture |
| `protocol_unsupported` | the protocol version is outside the range allowed by policy |
| `sequence_rollback` | the sequence is lower than the one already installed |
| `recovery_artifact_unverified` | recovery names an exact digest absent from local verified history |
| `sequence_below_minimum` | the sequence is below the policy minimum |

All checks are performed, not only until the first failure: a release that fails
four checks and passes one is not four-fifths trusted.

An unreadable policy schema stops the remaining checks: a trust rule applied
only halfway looks like someone's decision.

A rejected release does not advance the sequence counter. Otherwise, every
rejection would make the next rollback easier.

Recovery cannot go below the policy minimum. A separate machine has no way to
cross a minimum raised after a compromise.

Updating the provider does not update user targets or setups. The new version is
installed alongside the old one; the current pointer changes after diagnostics,
and the previous version is preserved for rollback.
