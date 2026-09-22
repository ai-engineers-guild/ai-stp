---
description: "Corporate telemetry is allowed only behind a closed field boundary, tenant isolation, retention, subject rights, and a dedicated governance audit trail."
last_verified: "2026-09-22"
---

# ADR-0203: Telemetry privacy governance

Status: accepted. Extends SPEC-013 and ADR-0112; grounds milestone B2B-04.

## Context

ADR-0112 deliberately kept client egress to one anonymous GET and forbade
event streams precisely because an authenticated channel "capable of carrying
an account will eventually carry it." Milestone 7 now needs corporate
telemetry - heartbeats (#215) and invocation usage (#218) - which is exactly
that channel. The privacy foundation must therefore exist before the streams,
not after: a boundary that cannot be enumerated is not a boundary.

## Decision

The corporate telemetry surface is three layers that each enforce the same
closed boundary:

- **Contract** — heartbeat and invocation payloads are discriminated-union
  models with `extra="forbid"`; a forbidden field fails validation before any
  handler runs.
- **Platform boundary** —
  `telemetry_privacy_service.validate_event_fields` re-checks the closed key
  set, forbidden names at any nesting depth, absolute local paths, and
  environment-style values for non-HTTP callers (jobs, sync).
- **Storage** — `telemetry_event` has one enumerable column set; no column
  can hold a prompt, payload, credential, path, or repository byte.

Governance lives in three tenant-scoped, RLS-protected tables:

- `telemetry_policy` — retention for raw events independent of aggregates,
  processing legal basis, and employee notice text/version.
- `telemetry_revocation` — per `account` or `device` subject state:
  `active`, `revoked` (blocks ingestion, optionally anonymizes retained
  rows), `deleted` (terminal erasure).
- `telemetry_audit` — append-only record of every privileged read, export,
  policy write, rights change, deletion, and retention run; `detail` carries
  counts and identifiers only, never payloads.

Authorization reuses the ADR-0179 tenant-scoped permission table; the
migration seeds `telemetry.{write,read,list,export,manage,delete}` for the
`superadmin` role. Mutations use the existing idempotency-receipt machinery.

Retention is executed by `telemetry_retention.apply_retention` (per tenant)
and `apply_retention_all` (worker sweep); the job handler lives in
`apps/worker` and deletes raw rows past `raw_retention_days` idempotently.

## Consequences

- Streams #215/#218 emit through this boundary; they add no fields and own
  their own raw tables (`installation_heartbeat`, `runtime_usage_event`)
  while inheriting these governance rules. Subject erasure and retention
  sweeps apply across every governed raw table: stream tables carry subject
  identifiers in NOT NULL columns, so erasure there is physical deletion
  rather than in-place anonymization. `installation_heartbeat` holds current
  installation state, not raw events, so retention does not sweep it.
- Deletion is destructive but idempotent and audited; anonymization preserves
  aggregate counts while stripping subject identifiers.
- A revoked or deleted subject cannot produce new telemetry rows.
