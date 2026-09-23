---
description: "Operator notes for runtime usage telemetry: outbox, ingestion, scoped reports, and export receipts."
last_verified: "2026-09-22"
---

# Runtime usage telemetry — engineering notes

Scope: GitHub #218 / `SPEC-088` / `ADR-0201`. This page is the operator-facing
map of the usage stream; the normative text lives in the spec and ADR.

## Flow

1. The provider runtime adapter accepts a component invocation and calls
   `ai_stp_cli.provider.usage_reporting.record_invocation` with identities and
   coordinates only. Components never emit or shape events; heartbeats and
   health checks never reach the seam.
2. The event lands in the local outbox
   (`data_dir()/runtime-usage-outbox.sqlite3`): dedup on `event_id`,
   exponential backoff to `MAX_ATTEMPTS`, `dead` beyond it, `MAX_ROWS` and
   `MAX_AGE_SECONDS` bounds, fail-closed when full.
3. `usage flush` drains due events to
   `POST /v1/corporate/organizations/{org}/telemetry/usage-events`, which
   deduplicates on `(organization_id, event_id)` and rejects body rows naming
   another tenant.
4. Reads: `GET .../telemetry/usage-reports` (aggregates + installed-vs-invoked)
   under `telemetry_usage.read`; `GET .../telemetry/usage-events` (redacted
   drill-down, audited) under `telemetry_usage.events`;
   `POST .../telemetry/usage-exports` under `telemetry_usage.export` produces a
   bounded digested receipt in `runtime_usage_export` plus an audit row.

## Permissions

Seeded as data by migration `0088` into the ADR-0179 policy table:
`superadmin` gets all four keys, `lead` gets `ingest` + `read`, `staff` gets
`ingest`. Scope resolution: organization scope sees the tenant; a team-scoped
principal sees its own events plus members of teams where the permission
holds.

## Boundaries

- No prompts, arguments, model I/O, MCP payloads, paths, environment values,
  credentials, or secrets in events, outbox, reports, exports, audit, or logs.
- The anonymous ADR-0112 channel is unrelated and untouched.
- Retention windows, deletion, anonymization, and revocation are the privacy
  stream (`SPEC-089`); this stream stores only the closed set and reads only
  through the policy table.

## Operations

- Outbox growth: check `usage outbox --json`; a persistent nonzero `dead`
  count means a device has been failing delivery past the attempt cap.
- Repeated `duplicates` in ingest responses are expected on retry and are not
  an error condition.
