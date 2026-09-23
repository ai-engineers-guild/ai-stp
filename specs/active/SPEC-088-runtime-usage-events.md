---
description: "SPEC-088: Corporate runtime component-usage events, scoped reports, and bounded export."
last_verified: "2026-09-22"
---

# SPEC-088: Runtime usage events and reporting

## Purpose

Collect factual, coordinate-only component-invocation events on the authenticated
corporate channel and expose tenant- and role-isolated aggregate reporting,
separately permissioned event-level drill-down, and a bounded auditable export.

This specification owns the runtime usage slice. SPEC-013 remains authoritative
for data governance; SPEC-079 and ADR-0179 remain authoritative for
authorization and tenant isolation; SPEC-089 owns retention, revocation, and
policy authority; ADR-0112's anonymous channel is untouched and unrelated.

## Terms

- `Runtime usage event` — one record of one accepted component invocation,
  carrying only the closed field set below.
- `Outbox` — the bounded local buffer on the emitting device.
- `Aggregate report` — grouped counts over a defined window, the default surface.
- `Drill-down` — the redacted event-level page behind its own permission.
- `Export` — a bounded, digested receipt of one aggregate report.

## Scope

This specification owns the authenticated runtime usage outbox, ingestion,
tenant-scoped reports, drill-down, and aggregate export. Heartbeat health is
owned by SPEC-087; retention, revocation, and data rights are owned by
SPEC-089; anonymous telemetry and public catalog counters remain separate.

## Requirements

- `REQ-8801`: The channel is authenticated `/v1` under
  `/corporate/organizations/{organization_id}/telemetry/...`. It never uses the
  anonymous collector, `telemetry.url`, or the `anon` identifier.
- `REQ-8802`: An event carries exactly: schema version, event id (a safe
  correlation identifier), organization, employee, device, project, harness,
  setup coordinate (stable id, exact version, passport digest), component
  coordinate (kind, stable id, version, passport digest), `invoked_at`, and
  outcome (`succeeded`, `failed`, `cancelled`). The contract model forbids
  additional fields.
- `REQ-8803`: Prompts, model inputs or outputs, arguments, MCP payloads, source
  or repository contents, local paths, environment values, credentials, and
  secrets never enter events, outbox rows, reports, exports, audit rows, or
  logs. Tests prove the absence.
- `REQ-8804`: The provider runtime adapter is the only sender. Components never
  emit events and never choose event fields. Heartbeats, provider health
  checks, and lifecycle operations emit no usage event.
- `REQ-8805`: The local outbox deduplicates on the event key across buffering
  and retries, applies bounded backoff with a dead state, and enforces row and
  age limits. A full outbox refuses new events rather than dropping silently.
- `REQ-8806`: Server ingestion deduplicates on `(organization_id, event_id)`.
  An event whose body organization differs from the authenticated path
  organization is rejected, not stored.
- `REQ-8814`: Identity is bound to the caller, never declared by the payload.
  An event is accepted only when `employee_id` is the authenticated account
  and `device_id` is the session's device - or, for a session without a
  device binding, an active device that account holds. `project_id` must
  name an active corporate project in the same tenant. `invoked_at` beyond a
  small clock-skew allowance in the future, or older than the raw retention
  window, is rejected. A revoked or deleted subject cannot emit.
- `REQ-8815`: The retention window and revocation state are the privacy
  authority's (`SPEC-089`). When `telemetry_policy` exists its
  `raw_retention_days` bounds ingest and every read; when it does not, a
  90-day default applies. When `telemetry_revocation` exists, revoked or
  deleted subjects are suppressed from drill-down while aggregate counts are
  preserved.
- `REQ-8807`: Every report and drill-down filter is tenant- and role-isolated.
  An organization-scoped principal sees the whole tenant; a team-scoped
  principal sees its own events plus members of the teams where it holds the
  permission. A filter naming an employee outside the caller's scope narrows
  to empty, never widens.
- `REQ-8808`: Aggregates group by component, setup, employee, device, project,
  harness, or outcome; report invocation count, per-outcome counts, distinct
  employees and devices, and first/last observed use; and are deterministic
  for a defined window and event set.
- `REQ-8809`: The report distinguishes installed objects from invoked ones:
  current catalog assignments appear beside their invocation counts, with
  `not_invoked` for zero.
- `REQ-8810`: Event-level drill-down requires `telemetry_usage.events`,
  separate from aggregate `telemetry_usage.read`. The drill-down view is
  redacted to identities and coordinates.
- `REQ-8811`: Export requires `telemetry_usage.export`, is bounded by
  `EXPORT_ROW_LIMIT`, is idempotent on its key, stores a digested receipt in
  `runtime_usage_export`, and emits an audit row. Exports carry aggregate rows
  only - never raw events.
- `REQ-8812`: Permission keys `telemetry_usage.ingest`, `.read`, `.events`, and
  `.export` are seeded as data into the ADR-0179 policy table by migration;
  no authorization code changes.
- `REQ-8813`: Corporate runtime events stay separate from public catalog
  counters and anonymous installation telemetry.
- `REQ-8816`: The installed-vs-invoked comparison respects the caller's
  scope: a team-scoped principal sees only assignments addressed to their
  employees, their permitted teams, or the whole organization.

## States and errors

Outbox rows move through queued, sent, retryable, and dead states; duplicate
events are successful idempotent no-ops. Ingestion rejects foreign identity,
invalid coordinates, stale or future timestamps, revoked subjects, and full
outboxes with stable typed errors. Reports and exports are deterministic for a
defined tenant, scope, and time window.

## Security and privacy

All routes require corporate authentication, tenant membership, and the
matching `telemetry_usage.*` permission. Payloads are closed and coordinate-
only; prompts, model traffic, arguments, paths, secrets, and source contents
are excluded from storage, reports, exports, and logs. Export receipts and
privileged reads are auditable.

## Compatibility and migration

Outbox, event, report, export, and permission tables are additive migrations.
Existing clients may omit usage fields and continue using existing catalog and
anonymous telemetry routes. Schema v1 remains machine-contract compatible;
rollback disables usage routes while retaining receipts and audit evidence.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-8801` | Runtime usage API and contract tests prove the authenticated corporate channel and reject anonymous routing. |
| `REQ-8802` | Contract and wire-object tests prove the exact event field set and coordinate validation. |
| `REQ-8803` | Boundary and serialization tests scan events, reports, exports, audit rows, and logs for forbidden data. |
| `REQ-8804` | Runtime adapter tests prove only the provider adapter emits events and lifecycle or heartbeat paths emit none. |
| `REQ-8805` | Outbox tests cover deduplication, bounded retry, dead state, row or age limits, and full refusal. |
| `REQ-8806` | Ingestion tests cover organization mismatch rejection and `(organization_id, event_id)` idempotency. |
| `REQ-8814` | Identity, project, clock-skew, retention, revocation, and device-binding tests cover accepted and rejected events. |
| `REQ-8815` | Runtime usage tests verify policy-derived retention and revocation suppression while preserving aggregates. |
| `REQ-8807` | Report and drill-down authorization tests cover organization, team, employee, and out-of-scope filters. |
| `REQ-8808` | Report tests cover every grouping, outcome counts, distinct identities, and deterministic windows. |
| `REQ-8809` | Installed-vs-invoked tests cover zero-count `not_invoked` assignments and current catalog joins. |
| `REQ-8810` | Permission and redaction tests require `telemetry_usage.events` and expose coordinates only. |
| `REQ-8811` | Export tests cover permission, row bounds, idempotency, aggregate-only payloads, digests, and audit rows. |
| `REQ-8812` | Migration and policy-table tests verify all four seeded `telemetry_usage.*` permissions. |
| `REQ-8813` | Isolation tests prove corporate runtime events do not affect public or anonymous counters. |
| `REQ-8816` | Scope tests prove installed assignments are limited to the caller's employees, teams, or organization. |
