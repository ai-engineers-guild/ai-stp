---
description: "SPEC-015: Canonical data, identifiers, and hashes."
last_verified: "2026-08-03"
---

# SPEC-015: Canonical data, identifiers, and hashes

## Purpose

All local, server, and provider implementations compute identical identifiers, bytes, hashes, and signatures for the same logical object and do not create incompatible duplicate schemas.

## Scope

Includes stable and content-addressed identifiers, representation of versions and references, canonical JSON, Unicode, time, and path rules, hash domains, signed data, and schema ownership. Table selection and encryption of user data at rest are out of scope.

## Terms

- `stable ID` — an opaque identifier of a logical object.
- `content ID` — a domain-separated hash of exact bytes.
- `passport digest` — the content ID of an immutable-version passport; replaces the former manifest hash.
- `canonical JSON` — the sole structured-data byte representation used for hashes and signatures.
- `schema owner` — the versioned JSON Schema, OpenAPI, or provider schema against which documents and examples are validated.

## Requirements

- `REQ-1501`: Stable identifiers have a type prefix, are opaque, do not depend on a path or display name, and are never reused.
- `REQ-1502`: An artifact, passport, revision, plan, and package use separate SHA-256 domains; no version-manifest domain exists.
- `REQ-1503`: Structured contracts are serialized according to RFC 8785 after UTF-8, NFC, and schema normalization.
- `REQ-1504`: Duplicate keys, non-numeric values, ambiguous decimal numbers, a byte order mark, and non-normalized paths are rejected before hashing.
- `REQ-1505`: Time has one UTC format with milliseconds, and version `X.Y` is compared as two numbers.
- `REQ-1506`: A stored object reference is a structured exact reference containing a stable identifier, version, and passport hash; an optional native implementation is permitted only in a component reference.
- `REQ-1507`: A signature covers the domain-separated canonical hash of a passport or artifact and does not include its own signature envelope.
- `REQ-1508`: One machine contract has one schema owner; architectural prose and examples do not introduce alternative field names.
- `REQ-1509`: Schema-generator output is deterministic and checked in CI against its source.
- `REQ-1510`: A change to canonicalization, a hash domain, or an incompatible schema uses a new version, a migration and dual-read window, and reference vectors.

## States and errors

Validation distinguishes invalid input, an unsupported schema, a non-canonical representation, and hash, signature, and reference mismatches. The canonicalizer does not silently repair signed data; it returns a typed error or creates a separate normalized draft before signing.

## Security and privacy

Domain separation prevents type substitution. A hash is not a secret and does not grant access. A canonicalization error does not include private data. A signature verifier uses an allowed key policy, not a key from an untrusted manifest.

## Compatibility and migration

Old hashes and published snapshots are not recomputed. A new reader supports declared older versions until the end of the compatibility window. Migration creates a new revision or version and preserves the original hash and provenance.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-1501` | Property tests confirm stability under renaming and moving and prohibit reuse. |
| `REQ-1502` | Reference vectors produce different digests for identical bytes in different domains. |
| `REQ-1503` | Fixtures from different languages produce identical canonical bytes. |
| `REQ-1504` | Negative fixtures reject duplicate keys, NaN, a byte order mark, and an ambiguous path. |
| `REQ-1505` | Time and version checks verify the canonical format and numeric ordering. |
| `REQ-1506` | Schema validation rejects a floating reference, a reference without a hash, and a variant in a setup reference. |
| `REQ-1507` | Signature mutation checks cover the data and signature envelope. |
| `REQ-1508` | A documentation-to-schema consistency check detects a renamed field. |
| `REQ-1509` | Repeating generation produces a clean diff and the same hash. |
| `REQ-1510` | Mixed-version fixtures verify migration, dual reads, and preservation of the old snapshot. |
