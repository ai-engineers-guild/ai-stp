---
description: "SPEC-088: Corporate runtime component-usage events, scoped reports, and bounded export."
last_verified: "2026-09-25"
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
  setup coordinate (stable id, exact version, passport digest) when the
  relationship is known, component
  coordinate (kind, stable id, version, passport digest), `invoked_at`, and
  outcome (`succeeded`, `failed`, `cancelled`), evidence source
  (`native_hook` or `agent_reported`), and activity kind (`invocation` or
  `load`). Omitted source on older clients defaults to `agent_reported`.
  The contract model forbids
  additional fields.
- `REQ-8818`: Direct component invocations carry `setup: null`; a partial or
  ambiguous setup coordinate is rejected rather than assigned. Setup-grouped
  counts exclude direct invocations while component and employee counts retain
  them.
- `REQ-8819`: Organization policy controls usage collection separately from
  inventory scanning and heartbeat. Intake rejects events when the usage
  policy is absent or collection is disabled. Local registration can be made
  mandatory only while collection is enabled; network delivery remains queued.
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
  Ingestion receipts identify accepted, duplicate, and rejected event IDs.
  The outbox removes only accepted and duplicate IDs; rejected or unacknowledged
  events remain for retry or inspection. Local queues are isolated by the
  authenticated account and organization, so changing either cannot send old
  events under the new identity.
- `REQ-8806`: Server ingestion deduplicates on `(organization_id, event_id)`.
  A native confirmation of the same invocation promotes an earlier
  `agent_reported` event in place, including its confirmed outcome and time.
  Identity, environment, exact setup/component coordinates, and activity kind
  must match; a reused ID with different coordinates is rejected. A later
  agent ping cannot downgrade native evidence. An outbox receipt removes only
  the payload actually sent, retaining a confirmation that arrived during delivery.
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
  for a defined window and event set. The same confirmed event set also produces
  report buckets by local calendar day and by weekday/hour in the organization's
  configured IANA time zone.
- The report includes a separate current inventory coverage summary per visible
  employee when scanning is enabled. It counts distinct managed components
  explicitly observed present or modified in each scope's latest scan, keeps
  the last complete check timestamp, and marks incomplete or stale coverage.
  An incomplete scan never establishes removal; inventory observations never
  increase usage counts.
- The report exposes whether usage collection and inventory scanning are
  enabled. The interface labels disabled, partial, stale, and missing scan
  coverage beside zero counts; zero events alone do not prove non-use.
- Employee rows resolve current corporate assignment precedence, including
  explicit employee revocation and `latest` selectors. Setup assignments expand
  their exact passport component references; direct and setup references to
  the same component count once. Installed and used component counts require
  an assigned stable ID and version to match respectively a fresh managed
  `present` observation or a confirmed invocation in the selected period.
- The Usage filter selects employees with a confirmed invocation in the
  selected period or employees without one. It narrows employee rows, object
  rows, the total, and both chart modes to the same selected employee set.
- Object rows retain the resolved setup-to-component relation and direct
  components as separate rows. They include the exact catalog version's name
  when available and retain the stable identifier as the fallback. A setup's Uses count includes only confirmed
  component invocations carrying that exact setup ID and version; a direct
  invocation never increments a setup. `Assigned to`, `Installed for`, and
  `Used by` count distinct employees. A setup is installed for an employee
  only when every resolved component reference in that setup is freshly
  observed as managed and present under that exact setup ID and version in one
  device, scope, and project. Direct installations or parts spread across
  environments do not establish a complete setup. Object rows keep the selected event filters
  and the organization's calendar-day grouping. When one employee is selected,
  each object row also reports `present`, `modified`, `missing`, or `unknown`
  installation state and the last scan time. Absence is `missing` only after
  complete fresh coverage; partial, stale, disabled, and absent scans remain
  `unknown` unless the object was explicitly observed present or modified.
- Separately permissioned event detail can narrow to exact setup/component
  versions, direct invocations, and a calendar day in the organization's report time zone. The day
  boundary is converted to UTC before pagination, including daylight-saving
  transitions. Weekday/hour detail uses the same configured time zone and
  applies its filter before page offset and limit.
- `REQ-8817`: Confirmed Uses count only `native_hook` `invocation` events.
  Agent-reported pings and passive loads remain separately visible in event
  drill-down and never increase the confirmed count. Failed and cancelled
  invocations still count after execution began.
- `REQ-8809`: The report lists current catalog assignments beside observed
  invocation counts, with `no_recorded_use` for zero. These rows come from the
  same effective assignment graph as employee and object rows, grouped by
  object ID and exact version across direct and setup contexts. Assignments are never
  presented as evidence of installation.
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
- `REQ-8816`: The assignment-versus-invocation comparison respects the caller's
  scope: a team-scoped principal sees only assignments addressed to their
  employees, their permitted teams, or the whole organization.

## States and errors

The CLI native hook adapter consumes bounded stdin and resolves the deepest
registered project and its current corporate link. Account/device identity,
operation binding, exact passport digest, and unchanged managed files determine
attribution. Provider packaging kinds do not replace the passport's component
kind. Contribution-owned members compare the exact owned key with the pinned
content artifact; changes to unrelated host settings do not invalidate that
component. Whole-file ownership still requires exact file bytes. Missing,
malformed, unsupported, or unverifiable contributions do not gain confirmation.
A verified rollback attributes native usage through the bundle recovered by `REQ-9307`. An unrecoverable rollback drops the observation.
Codex terminal MCP `PostToolUse` results and Grok Build MCP `OkayOutput`
results on `post_tool_use` or `post_tool_use_failure` are supported;
pre-execution and dispatch failure notifications are not invocation evidence.
Grok Build 1.0.41 emits failure hooks without `toolResult`, including when an
MCP server returns `isError`. Such payloads cannot distinguish execution from
dispatch failure and are dropped. They remain an explicit native coverage gap;
an `agent_reported` fallback does not convert them into confirmed Uses.
The local hook path does not refresh credentials or send heartbeats, update
checks, or events over the network. Expired held sessions can queue events;
revoked sessions cannot. Hook installation and native trust remain separate
provider and harness responsibilities (`ADR-0215`).

Outbox rows move through queued, sent, retryable, and dead states; duplicate
events are successful idempotent no-ops except for promotion to native evidence.
Ingestion rejects foreign identity,
invalid coordinates, stale or future timestamps, revoked subjects, and full
outboxes with stable typed errors. Reports and exports are deterministic for a
defined tenant, scope, and time window.

The report's `collection_state` filter narrows employees and all dependent
aggregates by their current inventory coverage: `complete`, `partial`, `stale`,
`unknown` (no retained observation), or `disabled` (inventory policy off).
The default `all` does not narrow. Inventory coverage never implies native
invocation coverage; the UI labels native coverage as partial separately.

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
| `REQ-8809` | Assignment-versus-invocation tests cover zero-count `no_recorded_use` assignments and current catalog joins. |
| `REQ-8810` | Permission and redaction tests require `telemetry_usage.events` and expose coordinates only. |
| `REQ-8811` | Export tests cover permission, row bounds, idempotency, aggregate-only payloads, digests, and audit rows. |
| `REQ-8812` | Migration and policy-table tests verify all four seeded `telemetry_usage.*` permissions. |
| `REQ-8813` | Isolation tests prove corporate runtime events do not affect public or anonymous counters. |
| `REQ-8816` | Scope tests prove assignments are limited to the caller's employees, teams, or organization. |
| `REQ-8817` | Report tests prove agent reports and loads do not increase Uses while event drill-down retains their source and activity kind. |
| `REQ-8818` | Contract and report tests prove direct components have no invented setup and partial coordinates are refused. |
| `REQ-8819` | Policy and ingestion tests prove independent toggles, disabled intake, and the required-registration invariant. |
