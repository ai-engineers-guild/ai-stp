---
description: "Corporate installation heartbeat HTTP routes, authorization, and the closed health-state set."
last_verified: "2026-09-22"
---

# Corporate installation heartbeat

The requirements owner is `SPEC-087`; the decisions are `ADR-0199` and
`ADR-0200`. All routes are authenticated, under
`/v1/corporate/organizations/{organization_id}/telemetry/`, and tenant-scoped
by row-level security on `installation_heartbeat`.

## Routes

| Method | Path | Purpose | Authorization |
| --- | --- | --- | --- |
| PUT | `…/telemetry/heartbeat` | coalesce one beat | active member; body account/device must equal the session's |
| GET | `…/telemetry/heartbeat` | own installation status | active member with a device-bound session |
| GET | `…/telemetry/heartbeats` | organization health list | own row always; other rows need `telemetry.read` |

`telemetry.read` is seeded for `superadmin` and `lead` (migration 0085) and
evaluated at member scope, so a lead bound to a team sees that team's
installations while an org-scoped grant sees all.

## Write semantics

One row per `(organization_id, device_id)`. A beat applies only when its
`checked_at` is strictly newer than the stored one — replays and delayed
writes are acknowledged without mutation. `checked_at` more than five minutes
ahead of the server clock is rejected (`400`). The response is the stored row
plus the evaluated `health_state`.

## Health states

Closed set: `active`, `stale`, `failing`, `disabled`, `unknown`. Computed at
read time (`ADR-0200`): no row → `unknown`; reported `disabled` → `disabled`;
`received_at` older than `stale_after_seconds` → `stale`; reported `failing` →
`failing`; otherwise `active`. Responses echo `stale_after_seconds` and
`evaluated_at` so the applied threshold is visible. The organization-level
threshold override is owned by the privacy stream's policy surface; the
default is 86400 seconds.

## Never stored or returned

Prompts, model inputs or outputs, arguments, MCP payloads, repository or
source contents, local paths, environment values, credentials, secrets.
Heartbeats and health reads emit no runtime invocation events.
