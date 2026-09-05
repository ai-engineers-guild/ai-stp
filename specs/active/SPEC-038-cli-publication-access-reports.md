---
description: "SPEC-038: CLI client for publication, access rights, and reports."
last_verified: "2026-08-13"
---

# SPEC-038: CLI Client for Publication, Access Rights, and Reports

## Purpose

The authenticated CLI guides the agent through the Phase 8 server-side workflows while keeping local compilation and passport editing on the client and ownership, publication, and access decisions on the platform. Wire formats are owned by `packages/contracts`; this document defines only the client-side sequence and data disclosure boundary.

## Scope

This includes commands for creating, reading, and confirming a publication plan, followed by reads of owner objects, grants, and report cases. It includes explicit confirmation, idempotent retries, and recovery from a lost response by reading server state.

This excludes the server-side state machine, background jobs, PostgreSQL, moderation, the web interface, modification of a local passport during publication, and sending artifact bytes to a route that accepts only a passport.

## Terms

- **Local released version** — an immutable pair of `stable_id` and `X.Y`
  associated with an exact passport revision in the SQLite registry.
- **Indeterminate result** — the transport completed without a contractual
  response, so the client does not claim whether the external effect occurred.

## Requirements

- `REQ-3801`: `publication plan` accepts only an exact locally released
  component version, materializes a formal `ComponentVersionPassport` from the
  pinned revision, and passes the digest of its artifact. The current head must
  not substitute for the released version's revision.
- `REQ-3810`: `setup publish plan` accepts an exact locally released setup
  version and creates one plan for each pinned component that is not yet public,
  plus one for the setup itself. An already public participant is listed with
  `already_published` and is not planned again. Public status is determined by
  the platform response, not by local `visibility`.
- `REQ-3811`: The set returns a `set_digest` over the ordered list of
  participants: role, object kind, `stable_id`, version, `plan_hash`, and the
  `already_published` flag. The state of an individual plan is not included in
  the digest. The set is stored locally because `plan_id` cannot be reconstructed
  by calculation; a repeated `plan` for the same setup version replaces the open
  set.
- `REQ-3812`: `setup publish confirm` requires the exact `set_digest` and an
  explicit `--confirm`, confirms participants in set order—components first,
  then the setup—and stops at the first rejection. The set transitions to
  `partial`; published participants remain published, and a repeated `plan`
  lists them as `already_published`. A set belonging to another account or
  device is rejected.
- `REQ-3813`: Report preview accepts the stable request topics from SPEC-016,
  validates their topic-specific component, author, requested recipient,
  custom-subject, reason, evidence, and locale fields, and stores the exact
  request bytes. Any authenticated account may prepare and submit ownership or
  verification requests; the CLI neither checks nor modifies verification.
- `REQ-3814`: Human CLI output supports RU and EN topic labels selected by an
  explicit locale or current CLI locale. JSON output, stored previews, digests,
  and wire requests retain stable English codes and original user-authored text.
- `REQ-3815`: The CLI exposes read-only request status and recovery after an
  indeterminate submit result. It exposes no command that approves ownership
  transfer or grants/revokes `author_verified`.
- `REQ-3802`: Creating a plan does not publish the object. The response shows
  the immutable `plan_id`, `plan_hash`, expiration, and effects; confirmation is
  a separate command requiring the exact hash and mandatory `--confirm`.
- `REQ-3803`: One network invocation of a mutating command retains one
  idempotency key across all transport retries. After an indeterminate result
  from confirm, the next safe step is `publication status`, not a new effect.
- `REQ-3804`: All commands require an active cloud session and send the bearer
  token only to a verified HTTPS endpoint. JSON responses and errors do not
  contain tokens, signatures, source bytes, or credential values.
- `REQ-3805`: The grants and reports client uses private wire models, separates
  preview and confirm where required by the server contract, and does not
  reproduce the server-side authorization matrix through local assumptions.
- `REQ-3806`: A mutating grants command requires explicit confirmation and a
  stable idempotency key. A raw invitation token is accepted only from the named
  environment variable and does not appear in process arguments, URLs, results,
  or errors.
- `REQ-3807`: A report is first stored as an exact local preview. Confirm accepts
  its identifier and digest, while a retry after an indeterminate result uses
  the stored payload and the same idempotency key. Diagnostics are optional,
  bounded UTF-8 input, fully visible in the preview, and rejected if they
  contain absolute paths or secret-bearing assignments.
- `REQ-3808`: Owner reads use only authenticated server-side list,
  object-detail, and exact-version models. The CLI does not treat a grant as
  ownership, does not mix the owner workspace with the local or public catalog,
  and returns the opaque cursor without interpretation.
- `REQ-3809`: `attestation sign` creates a new owner-only file containing the
  complete `AuthorAttestation`, signs the exact digest of the released object
  and all verification coordinates with the active device's key, and never
  overwrites an existing file. `publication plan` accepts such files explicitly,
  validates the private model, exact `stable_id`, `version`, object and passport
  digests, account, device, absence of duplicates, and signature before HTTP,
  and then sends only the fields of the existing wire model.

## States and errors

Publication plan states come only from `PublicationPlanResponse` and are not
computed by the client. A missing or expired session requires a new login; a
revoked device remains a distinct permanent rejection. A local passport
completeness error occurs before the HTTP call. After a transport error from
confirm, the command suggests the read-only status of the known plan.

## Security and privacy

The client materializes the private version passport model and does not add
artifact contents or environment state to it. The endpoint undergoes the common
HTTPS verification; redirects are prohibited so that the bearer token is not
sent to another authority. Errors do not repeat the URL, token, or response
body.

## Compatibility and migration

The new commands are additive and use the existing `/v1` and exported schemas.
The local exact report preview is stored in a separate table added through a
standard reversible SQLite migration; existing registries retain all existing
rows. A version not associated with an available revision is rejected without
a network effect.

## Acceptance criteria

| Requirement | Evidence |
| ----------- | -------- |
| `REQ-3801` | A unit/process test releases a version, advances the draft, and verifies that the plan is built from the recorded revision and exact artifact digest. |
| `REQ-3802` | Registry and transport tests establish three separate commands and mandatory confirmation of the exact hash. |
| `REQ-3803` | The mock transport loses the response and observes one key across retries; the error suggests status for the known plan id. |
| `REQ-3804` | Contract tests verify the bearer header and the absence of prohibited fields in the request/output/error. |
| `REQ-3805` | The fixture corpus covers the happy path, authorization rejection, replay, and recovery for grants and reports. |
| `REQ-3806` | Registry and transport tests cover all grant routes, retries with one key, mandatory confirm, and the absence of the raw token from the command's public surface. |
| `REQ-3807` | The process/unit corpus proves preview without HTTP, exact-digest confirm, persistence after a lost response, replay without a second effect, and fail-closed diagnostics. |
| `REQ-3808` | Transport/registry tests establish three read-only routes, the bearer boundary, exact path/query, and separate CLI views without leakage into OpenAPI. |
| `REQ-3809` | Unit/registry/schema tests establish owner-only writes without overwriting, the complete signed payload, signature corruption, mismatched exact coordinates, duplicates, and the private CLI-only schema. |
| `REQ-3810` | Unit tests plan a setup with a public pin and a non-public pin and verify that a plan is created only for the non-public pin while the public pin is listed as `already_published`; local `visibility` contradicts the platform response in this case. |
| `REQ-3811` | The digest is computed over the ordered list; changing the order, adding a participant, or using a different `plan_hash` produces a different digest, while changing plan state produces the same digest. A repeated plan replaces the open set for the same version. |
| `REQ-3812` | Confirm without the flag is rejected with a typed error; rejection of the second of three participants leaves the first published, the set in `partial`, and the third unconfirmed; another account or device is rejected. |
| `REQ-3813` | Registry, process, and contract tests cover every topic, topic-specific rejection, exact preview/confirm, and submission by an unverified account and Official. |
| `REQ-3814` | RU/EN snapshots differ only in human labels; JSON and digest fixtures remain byte-identical for the same authored request. |
| `REQ-3815` | A lost-response fixture recovers one case by idempotency key, and registry parity proves no ownership/verification decision command exists. |
