---
description: "Operator notes for runtime usage telemetry: outbox, ingestion, scoped reports, and export receipts."
last_verified: "2026-09-26"
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
   (one `runtime-usage-outbox-<digest>.sqlite3` per account and organization): dedup on `event_id`,
   exponential backoff to `MAX_ATTEMPTS`, `dead` beyond it, `MAX_ROWS` and
   `MAX_AGE_SECONDS` bounds, fail-closed when full. Each successful heartbeat
   policy read caches usage collection enablement in that scoped database.
   A cached disabled policy prevents new records and both automatic and manual
   flush; pending records remain visible in `usage outbox`.
3. `usage flush` drains due events to
   `POST /v1/corporate/organizations/{org}/telemetry/usage-events`, which
   deduplicates on `(organization_id, event_id)` and rejects body rows naming
   another tenant. The receipt names each accepted, duplicate, or rejected ID;
   only accepted and duplicate events leave the local queue.
   A native confirmation sharing the same invocation ID promotes an earlier
   agent report without adding a use. A reused ID with different coordinates
   is rejected. Receipts only remove the exact payload sent, so a confirmation
   arriving while a fallback is in flight remains queued.
   Intake rejects events while collection is disabled or policy is absent;
   rejected IDs stay queued for inspection and retry after policy changes.
4. Reads: `GET .../telemetry/usage-reports` (aggregates + assignments versus observed use)
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

- `usage hook --harness codex|grok-build --scope project|global --json`
  consumes at most 1 MiB of native hook JSON from stdin, without network access.
  It resolves the current linked project from the process working directory,
  checks the held account/device and newest installation, and verifies the exact
  component passport and managed files. Creating that link requires
  `project.link`. Migration `0104` seeds it for `superadmin`, `lead`, and
  `staff`, and seeds `project.unlink` for `superadmin` and `lead`. Install this
  command as ordinary hook content through the harness provider; the command
  alone does not install it or bypass the harness's trust decision.
- Native coverage currently accepts terminal MCP `PostToolUse` results from
  Codex and Grok Build. Native session/tool-call IDs determine deduplication.
  Pre-execution, dispatch-failure, malformed, truncated, ambiguous, and drifted
  observations are refused. Other component kinds remain agent-reported or
  unsupported; this adapter does not turn content loading into a native call.
- `usage record --activity-kind load` keeps agent-reported instruction or
  setting loads separate from invocations. Omitting it retains `invocation`.
- Outbox growth: check `usage outbox --organization <org> --json`; a persistent nonzero `dead`
  count means a device has been failing delivery past the attempt cap.
- Repeated `duplicates` in ingest responses are expected on retry and are not
  an error condition.
- When a whole batch is rejected, check that organization usage collection is
  enabled independently of inventory scanning.
