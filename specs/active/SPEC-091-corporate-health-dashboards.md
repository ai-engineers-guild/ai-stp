---
description: "SPEC-091: Authorized Corporate Hub health aggregation and saved dashboard views."
last_verified: "2026-09-22"
---

# SPEC-091: Corporate health dashboards

## Purpose

Provide a bounded dashboard constructor over the latest managed CI verdict per
project/device/harness, the canonical installation heartbeat health projection,
and the latest governed provider heartbeat per account/device/harness/provider.
The dashboard does not manage installations or providers.

## Scope

This specification owns the CI summary write, constrained aggregation endpoint,
saved dashboard queries, and web constructor. SPEC-087 owns installation
heartbeat state, SPEC-089 owns provider telemetry and privileged-access audit.

## Terms

- `CI check` — the latest managed verification verdict for one tenant,
  project, device, and harness.
- `Saved view` — a validated query definition with a user, team, or
  organization sharing scope; it contains no result rows.
- `Dashboard cell` — one bounded group of dimension values and integer
  measures returned by the query endpoint.

## Requirements

- `REQ-9101`: A CI check uses the closed `ManagedVerification.status` verdict
  set and a closed, redacted reason set. The account and device match the held
  session; the project is active and readable. Writes accept strictly newer
  `checked_at` values and coalesce equal or older reports. No prompt, source
  content, path, credential, or environment value is accepted.
- `REQ-9102`: Reads require active tenant membership and a `lead` or
  `superadmin` role. A superadmin with `telemetry.read` sees the organization.
  A lead sees only members for whom `telemetry.read` is granted in a team for
  which `team.read` is granted, and CI rows also require `project.read`.
- `REQ-9103`: The query contract permits only the `ci`, `heartbeat`, and
  `provider` datasets, their explicit dimension and measure allowlists,
  equality filters, grouping, sort, and pivot axes. It rejects unknown fields,
  invalid combinations, more than 1,000 source rows, cost above 5,000, and
  returns at most 200 groups. There is no arbitrary SQL or source payload.
- `REQ-9104`: CI state retains `pass`, `fail`, `outdated`, `revoked`,
  `unsupported`, `not_enrolled`, and `unverifiable`; heartbeat/provider health
  retains `active`, `stale`, `failing`, `disabled`, and `unknown`. Staleness is
  evaluated at read time from server receipt time. An empty selection returns
  an empty result. A partial install is not fabricated as a CI verdict.
- `REQ-9105`: `reason` selection or filtering requires `audit.read`; all
  dashboard queries emit platform audit and telemetry privileged-access audit.
  Returned rows contain IDs and closed states only. No export route exists.
- `REQ-9106`: Saved queries use user, team, or organization scope. A team lead
  may manage a team view with `team.read`; a superadmin may manage organization
  views. Scope is immutable; writes require current authorization revision,
  expected view revision, and idempotency key. Opening a view reruns the current
  authorization checks over current source records.
- `REQ-9107`: The web constructor exposes datasets, dimensions, measures,
  exact filters, grouping, sorting, pivot axes, and bounded table, bar, line,
  pie, and heatmap views. Controls and colors use the existing web kit.

## States and errors

CI and heartbeat/provider states remain their owners' closed state sets.
Unknown dimensions, forbidden diagnostics, excessive cost, stale revisions,
and revoked access reject with the existing typed API error envelope. The
empty state has zero cells; source rows are never silently truncated.

## Security and privacy

The API scopes each source row to the tenant and current member permissions
before grouping. Diagnostic reads require `audit.read` and every query records
both platform and privileged telemetry audit. Requests and stored rows have no
secret, prompt, source content, local path, or environment field.

## Compatibility and migration

Migration 0092 adds a tenant-isolated latest CI check table and saved query
table with RLS. It does not duplicate heartbeat or provider health state.
Rollback disables the dashboard routes and UI; retaining 0092 data preserves
reports and saved views. A database downgrade drops the two tables only after
a backup and explicit operational decision.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-9101` | API tests reject unsafe fields and another device, and coalesce equal check time. |
| `REQ-9102` | API tests reject another tenant and unauthorized membership/scope. |
| `REQ-9103` | Contract and API tests reject unknown dimensions and cost limits. |
| `REQ-9104` | API tests observe stale installation and failing provider health plus empty selection. |
| `REQ-9105` | API tests assert reason permission and privileged audit. |
| `REQ-9106` | API tests assert saved-view replay, scope immutability, and revision checks. |
| `REQ-9107` | Browser scenario exercises dataset switch, result, filter, empty state, and save. |
