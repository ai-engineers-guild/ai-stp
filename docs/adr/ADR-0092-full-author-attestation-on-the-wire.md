---
description: "Decision to transmit the complete signed author-attestation record over /v1 and verify its Ed25519 signature."
last_verified: "2026-08-15"
---

# ADR-0092: Complete author-attestation record on the wire

Status: accepted.

## Context

`ADR-0026` already requires an attestation signed by the device key and bound to
the exact publication coordinates. The canonical closed record and the
`ai-stp:attestation:v1` domain belong to
`ai_stp_assurance.AuthorAttestation`. The CLI signs that exact record.

The `/v1` wire model carried a truncated projection: without the digest,
subject, policy, harness, provider, or account. The server accepted any
`signature` string of length 16 or more and discarded `content_digest`. A string
of sixteen `s` characters passed as evidence. Two payload definitions existed
at the same time, and the server side verified neither the device key nor the
coordinates.

The missing fields cannot be reconstructed from the plan without losing the
binding: harness and provider versions are specified when signing and need not
match any passport field if the client did not send them.

## Options

1. Keep the projection and accept the string form. This is the current defect:
   it has test coverage but no cryptographic binding.
2. Reconstruct the canonical record on the server from the plan and passport.
   There is one definition on paper but a second in practice: the server guesses
   fields it never saw, and the signature differs from what the client signed.
3. The `/v1` wire carries the same closed record as assurance. The server
   verifies Ed25519 with the active device key over `attestation_digest` and
   compares every coordinate with the plan and session.

## Decision

Option 3 is accepted.

The sole payload definition is `ai_stp_assurance.AuthorAttestation`. The wire
model in `packages/contracts` is isomorphic to this record. The server does not
reconstruct missing coordinates and does not trust the signature string length.

Verification rejects a revoked or foreign device, a mismatched digest, version,
policy, tools, harness, provider, test cases, account, device, a time not in the
canonical timestamp form, and a signature that the key does not verify.

## Consequences

- the `/v1` AuthorAttestation schema changes: the canonical record fields and
  Ed25519 form arrive instead of `created_at` and a short signature;
- a client that sent the projection receives a typed rejection until it supplies
  the complete body; the CLI already stores the complete record and transmits it
  without new signing logic;
- tests in which `"s" * 16` counted as accepted evidence become negative tests;
- reverting to the projection decouples the signature from the coordinates
  again.

## Reconsideration conditions

The decision is reconsidered if a second legitimate signer besides the device
key appears, or if the wire must carry an attachment larger than the closed
record. A new ADR is then required; a second payload definition is not
introduced in the same major version.
