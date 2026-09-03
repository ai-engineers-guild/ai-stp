---
description: "Canonical identifiers, serialization, references, hashes, and signatures."
last_verified: "2026-09-03"
---

# Canonical data

## Contract owner

Once executable code exists, the field owners are versioned schemas under `schemas/`,
OpenAPI, and the public provider protocol schema. Documents explain meaning but do not
create alternative field names. Until schemas exist, this document together with
`SPEC-015` is the normative source.

## Identifiers

A stable entity receives an opaque type-prefixed `stable_id`. The identifier is
independent of path, display name, version, or device and is never reused.

A revision receives a `revision_id` computed from the revision's canonical data:
`revision_` plus 64 hexadecimal characters of the hash in the `ai-stp:revision:v1`
domain under `ADR-0036`. There is no random revision identifier creation path. A
published artifact, version passport, plan, and package receive separate content-addressed
identifiers.

Under `ADR-0012`, no separate "version manifest" entity exists: an immutable version is
described by its passport. The word "manifest" is reserved for the bounded file table
inside a package under `harness-bundle.md` and the provider release manifest under
`provider-release.md`; neither is version identity.

## Canonical serialization

Structured data is serialized as UTF-8 JSON under RFC 8785 after Unicode NFC
normalization. Duplicate keys, nonnumeric values, ambiguous decimal numbers, a byte-order
mark, and an unknown incompatible schema version are rejected before hashing.

Time is recorded in UTC under RFC 3339 with milliseconds and the `Z` suffix. An `X.Y`
version is stored as a string but compared as two nonnegative integers.

A path within an artifact uses `/`, is relative, contains no empty segments, `.` or
`..`, and is compared after Unicode and case-sensitivity checks for the target filesystem.

## Hash domains

Different objects use different domains:

```text
ai-stp:artifact:v1
ai-stp:component-adaptation:v1
ai-stp:passport:v1
ai-stp:revision:v1
ai-stp:plan:v1
ai-stp:multi-root-transaction:v1
ai-stp:bundle:v1
ai-stp:attestation:v1
ai-stp:native-discovery:v1
ai-stp:project-index:v1
ai-stp:project-toolchain:v1
ai-stp:project-configuration:v1
ai-stp:selection-snapshot:v1
ai-stp:seo-snapshot:v1
ai-stp:seo-profile:v1
ai-stp:article-body:v1
ai-stp:article-revision:v1
ai-stp:article-active:v1
ai-stp:article-snapshot:v1
```

The three `project-*` domains belong to the project passport and are separated: file
inventory, installed toolset, and project configuration are different facts, and equal
content must not produce one identifier.

The `selection-snapshot` domain belongs to the recommendation session input snapshot
under `selection-proposal.md`: context passport revisions, selected harness, exact
candidates, and policy version. A change to it makes the proposal stale, so it is
separate from the passports from which it is assembled.

The `seo-snapshot`, `seo-profile`, and `article-body` domains belong to the server-side
SEO boundary under `seo-publication-projection.md`: the public fact aggregate, revision
presentation document, and article body. Equal bytes across them do not produce an
interchangeable identifier.

The `article-revision`, `article-active`, and `article-snapshot` domains belong to
article publication under `article-publication.md`: canonical localized revision,
active RU/EN pair, and complete repository snapshot. `article-body` remains the SEO body
hash and does not replace a revision's `content_digest`.

The `native-discovery` domain belongs to a reproducible read-only discovery candidate
under `ADR-0054` and `ADR-0055`. It binds the declared layout, scope, harness, redacted
path, and allowlisted source provenance, but does not create stable Component logical
identity: only explicit adoption creates that identity.

The hash is SHA-256 over the domain name, a null byte, and canonical bytes. Equal content
in different domains must not produce an interchangeable identifier.

`ArtifactRef.digest` always uses the `ai-stp:artifact:v1` domain and exact artifact
bytes. The raw SHA-256 of the HarnessBundle ZIP container belongs to the separate
`bundle_artifact_digest` field under `harness-bundle.md`; it is not an `ArtifactRef` and
is not validated as a domain-separated artifact hash. The local cache stores these
spaces separately because the `sha256:...` string does not itself encode the hash domain.

## Exact reference

A component version reference contains a stable identifier, optional native
implementation, version, and passport hash:

```json
{
  "stable_id": "component_...",
  "variant_id": "variant_...",
  "version": "1.2",
  "passport_digest": "sha256:..."
}
```

A setup version reference contains no variant: a setup belongs to one harness under
`ADR-0014`, so native implementation is not a separate axis of its identity.

```json
{
  "stable_id": "setup_...",
  "version": "1.2",
  "passport_digest": "sha256:..."
}
```

The `variant_id` field is permitted only in a component reference and only when the
component actually has separate native implementations. It denotes an implementation,
not a separate version line.

Floating branches, tags, version ranges, and the value `latest` are not storable references.

## Signature

A signature covers the domain-separated canonical hash of a passport or artifact, the
trust-policy identifier, and the permitted release context. A key or publisher from an
untrusted manifest does not automatically become trusted. The signature envelope does
not include itself in the signed data.

## Changes

Changing canonicalization, a hash domain, or an incompatible field set requires a new
schema version, reference vectors, a dual-read window, and an explicit migration. Old
published hashes are not recomputed.
