---
description: "SPEC-044: GitHub archived state as local evidence of obsolescence."
last_verified: "2026-08-13"
---

# SPEC-044: GitHub archive evidence

## Purpose

For an exact local version with a public GitHub source, the CLI obtains the repository's official `archived` state and stores it as timestamped external evidence. The signal warns of obsolescence but does not itself change the lifecycle, eligibility, published bytes, or installed target.

## Scope

The initial implementation covers the machine CLI and local registry. The public catalog/detail projection belongs to platform/web. Only `github.com` and the official REST endpoint are supported. The first version does not accept GitHub credentials and requests only public metadata; a private repository produces the indistinguishable `unavailable` state.

## Terms

- **Observation** — an immutable row representing one GitHub response, with a timestamp and TTL.
- **Repository identity** — the numeric GitHub repository id, which survives rename and transfer.
- **Proposal** — a mechanical lifecycle proposal with no automatic effect.
- **Freshness** — a comparison of the read time against the stored observation's validity period.

## Requirements

- `REQ-4401`: Refresh accepts an exact `stable_id` and `X.Y`, reads the source from the stored immutable passport, and rejects a local, missing, credentialed, or non-GitHub source.
- `REQ-4402`: A successful observation stores the immutable GitHub repository id, canonical `full_name`, original coordinate, `archived`, `fetched_at`, TTL, and an optional ETag. Redirect, rename, and transfer are accepted only from the official response with the same repository id after the first observation.
- `REQ-4403`: `archived=true` returns only a `deprecated` proposal and a warning. It never creates `blocked`, changes the lifecycle, bytes, passport, selection, installation, or target, or performs a replacement.
- `REQ-4404`: Every changed observation is added to append-only history. `unarchive` does not erase the previous archived fact; a repeated `304` updates freshness through a separate observation without inventing a state change.
- `REQ-4405`: Offline show uses the latest observation and marks it `fresh` or `stale`. Missing evidence has the `unavailable` state; 404, 403, rate limiting, an invalid response, and transport failure do not become deprecation and do not destroy stored evidence.
- `REQ-4406`: Refresh uses conditional GET, a closed response model, a bounded response size, and no more than one request. Credentials are not accepted, read from the environment, or included in the registry or response.
- `REQ-4407`: The machine CLI uses shared strict schemas for refresh/show/history; history is bounded, ordered, and includes attribution and freshness.

## States and errors

Evidence is `fresh`, `stale`, or `unavailable`; repository state is `active`, `archived`, or `unavailable`; proposal is `none` or `deprecated`. A network error returns a typed failure and does not replace the last good snapshot.

## Security and privacy

The request is constructed only from a validated public source passport. Redirects are not followed automatically. The response size is bounded, and the response is validated against a strict schema. The first version intentionally has no credential surface.

## Compatibility and migration

SQLite receives an append-only observation table. Existing versions do not change; without refresh, their response is truthfully `unavailable`. New provider hosts and lifecycle automation require a separate decision.

## Acceptance criteria

| Requirement | Executable evidence |
|---|---|
| `REQ-4401` | Exact-version fixtures accept a GitHub source and reject a local/unknown coordinate before HTTP. |
| `REQ-4402` | The mock returns rename/transfer with the same id and a collision with a different id; exact coordinates are stored. |
| `REQ-4403` | The archived fixture returns a proposal without changing version, selection, installation, or target. |
| `REQ-4404` | Archived → unarchived → 304 remain three ordered observations. |
| `REQ-4405` | Clock-controlled tests distinguish fresh/stale, while 404/rate-limit/outage preserve the previous snapshot. |
| `REQ-4406` | The transport test verifies the conditional header, one request, bounded body, and absence of a credential surface. |
| `REQ-4407` | The registry, generated schemas, and machine help declare one evidence refresh command and two read-only commands. |
