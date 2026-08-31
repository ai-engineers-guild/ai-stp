---
description: "Independent definition artifact and complete passport of a confirmed SetupVersion."
last_verified: "2026-08-09"
---

# ADR-0051: SetupVersion Definition Artifact

Status: accepted.

## Context

Confirmation of a proposal created a generic `PassportEnvelope` containing only `facts`, although, according to the public schema, `SetupVersion` must have a `SetupVersionPassport`: exact references to components, version, purpose, aggregated requirements, license, and `ArtifactRef`. The bundle accepted the generic envelope as a passport, so the local version did not conform to its own generated schema.

HarnessBundle cannot be used as the passport's `artifact`. The ZIP contains `setup-passport.json`; if the passport contains the digest of that ZIP, the digest depends on itself and cannot be computed without a fixed point. Substituting `bundle_digest` would also conflate the `artifact` and `bundle` domains.

## Decision

Explicit confirmation creates separate canonical bytes in the
`ai-stp-setup-definition/1` format. The definition contains:

- stable ID and `X.Y` SetupVersion;
- one `harness_id`;
- selection input digest;
- sorted exact component refs with passport digest.

The bytes are serialized using RFC 8785, receive the domain-separated digest
`ai-stp:artifact:v1`, and are stored in an immutable SQLite content store in the same
transaction as the entity, revision, version, RecommendationTrace, and pin. The full
`SetupVersionPassport.artifact` points to these bytes and their size. The passport
also includes `artifact_format=ai-stp-setup-definition/1`.

HarnessBundle is a subsequent native compilation. It includes the immutable
passport, reports, and managed files, and has its own logical `bundle_digest` and raw
SHA-256 ZIP bytes. None of its digests replaces the SetupVersion `ArtifactRef`.

## Metadata Completeness

If every component reference resolves to a complete `ComponentVersionPassport`,
the setup version aggregates required environment variables, credentials,
authorization, permissions, external access points, and the license. Ordering and
deduplication are deterministic.

Historical local components may have only a generic envelope. Such a partial
SetupVersion is stored with `member_metadata_complete=false`, a conservative private
composite license, and `redistribution_allowed=false`. This flag is a mandatory
publication blocker; local composition/provider checks continue to read exact
component revisions and do not treat an incomplete aggregate as permission.

## Atomicity and Compatibility

Definition bytes are written within `BEGIN IMMEDIATE`. A failure after writing the
content row rolls it back together with the revision/version/trace/pin; no
authoritative orphaned artifact remains. Repeated confirmation returns the already
created immutable version and does not build a new definition.

Previously created local SetupVersions are not rewritten: retroactively changing an
immutable passport would violate exact references. A new confirmation always creates
a complete passport. Public publication of the old generic form requires an
explicit new version/fork rather than a hidden digest migration.

## Consequences

SetupVersion and HarnessBundle no longer form a hash cycle, the local object passes
the formal passport schema, and the artifact can be synchronized independently of
a specific provider conversion. The cost is a separate small content row and an
explicit publication blocker for legacy metadata.
