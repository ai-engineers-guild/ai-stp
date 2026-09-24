---
description: "Corporate installation heartbeat HTTP routes, authorization, and the closed health-state set."
last_verified: "2026-09-24"
---

# Corporate installation heartbeat

The requirements owner is `SPEC-087`; the decisions are `ADR-0204`,
`ADR-0205`, and `ADR-0208`. All routes are authenticated, under
`/v1/corporate/organizations/{organization_id}/telemetry/`, and tenant-scoped
by row-level security on `installation_heartbeat`.

## Routes

| Method | Path | Purpose | Authorization |
| --- | --- | --- | --- |
| PUT | `…/telemetry/heartbeat` | coalesce one beat | active member; body account/device must equal the session's |
| GET | `…/telemetry/heartbeat` | own installation status | active member with a device-bound session |
| GET | `…/telemetry/heartbeats` | organization health list | own row always; other rows need `telemetry.read` |
| GET | `…/telemetry/heartbeat/policy` | enabled state, interval, retry bounds, stale threshold | active organization member |

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

Closed set: `active`, `partial`, `stale`, `failing`, `disabled`, `unknown`.
Computed at read time (`ADR-0205`): no row → `unknown`; reported `disabled` → `disabled`;
`received_at` older than `stale_after_seconds` → `stale`; reported `failing` →
`failing`; reported `partial` → `partial`; otherwise `active`. Responses echo `stale_after_seconds` and
`evaluated_at` so the applied threshold is visible. The organization telemetry
policy owns enablement, interval, retry bounds, and threshold. Defaults are
enabled, 21600-second interval, retry bounds of 60 and 3600 seconds, and
86400-second staleness. A disabled organization policy rejects new heartbeat
writes; revoked account/device subjects are rejected before coalescing.

`heartbeat send` remains available for explicit writes. Automatic CLI reports
require local opt-in and run opportunistically after a successful ordinary CLI
command, at most one due organization per invocation. The CLI never starts a
provider process for this report.

## Never stored or returned

Prompts, model inputs or outputs, arguments, MCP payloads, repository or
source contents, local paths, environment values, credentials, secrets.
Heartbeats and health reads emit no runtime invocation events.
