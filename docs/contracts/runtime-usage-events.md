---
description: "Runtime usage event ingestion, scoped reports, drill-down, and export routes for corporate telemetry."
last_verified: "2026-09-22"
---

# Runtime usage events contract

Wire contract for corporate runtime component-usage telemetry (`SPEC-088`,
`ADR-0201`). All routes live under the authenticated `/v1` corporate namespace
and require an active corporate membership; permission keys are data-seeded
into the tenant policy table.

## Event

`RuntimeUsageEvent` — closed field set, `extra="forbid"`:

| field | meaning |
|---|---|
| `schema_version` | `1` |
| `event_id` | safe correlation id, the dedup key (`^[A-Za-z0-9][A-Za-z0-9_.:-]{7,79}$`) |
| `organization_id` | tenant |
| `employee_id` | account id |
| `device_id` | device reference |
| `project_id` | remote project id |
| `harness` | harness id |
| `setup` | `{stable_id, version, passport_digest}` |
| `component` | `{kind, stable_id, version, passport_digest}` |
| `invoked_at` | canonical UTC timestamp |
| `outcome` | `succeeded` \| `failed` \| `cancelled` |

Forbidden everywhere: prompts, model inputs/outputs, arguments, MCP payloads,
source or repository contents, local paths, environment values, credentials,
secrets.

## Routes

- `POST /corporate/organizations/{organization_id}/telemetry/usage-events` —
  body `RuntimeUsageEventBatch` (`events`, max 256). Permission
  `telemetry_usage.ingest`. Returns `{accepted, duplicates, rejected}`;
  dedup on `(organization_id, event_id)`, cross-tenant body rows rejected.
  Identity is bound to the caller: `employee_id` must be the authenticated
  account, `device_id` the session's device (or an active device of that
  account when the session has none), `project_id` an active project of the
  tenant; `invoked_at` may not be in the future or past the raw retention
  window. Violations count as `rejected`, never stored.
- `GET .../telemetry/usage-events` — query `RuntimeUsageEventQuery`.
  Permission `telemetry_usage.events`; audited; redacted rows only.
- `GET .../telemetry/usage-reports` — query `RuntimeUsageReportQuery`
  (filters plus `group_by`, `offset`, `limit`). Permission
  `telemetry_usage.read`; returns grouped rows and the installed-vs-invoked
  list.
- `POST .../telemetry/usage-exports` — body `RuntimeUsageExportRequest`
  (`query`, `authorization_revision`, `idempotency_key`). Permission
  `telemetry_usage.export`; bounded, idempotent, digested receipt, audited.
- `GET .../telemetry/usage-exports/{export_id}` — the stored receipt.
  Permission `telemetry_usage.read`.

## CLI surface

- `usage record` — the intake the provider adapter calls after accepting an
  invocation; buffers one closed-field event in the local outbox. Employee
  and device come from the held session, never from options.
- `usage report|events|export` — the read surface over the routes above.
- `usage outbox` — local buffer state; `usage flush` — drain due events.
- Provider seam: `provider/usage_reporting.record_invocation` — the only
  sender; buffers one closed-field event per accepted invocation.
