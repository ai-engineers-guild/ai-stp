---
description: "Engineering notes for the corporate installation heartbeat stream (t-heartbeat, GitHub #215)."
last_verified: "2026-09-24"
---

# Telemetry heartbeat engineering

## Layout

- `packages/contracts/src/ai_stp_contracts/heartbeat.py` — closed request,
  stored-row view, own-status view, list view, and organization policy view;
  capability-token and CLI-version alphabets.
- `apps/platform/src/ai_stp_platform/heartbeat_models.py` — the
  `installation_heartbeat` table model, one row per `(organization, device)`.
- `apps/platform/src/ai_stp_platform/heartbeat_service.py` — coalescing write,
  ordering guard, read-time health projection.
- `apps/api/src/ai_stp_api/slices/corporate/heartbeat.py` — write, own status,
  list, and organization policy routes.
- `apps/cli/src/ai_stp_cli/heartbeat.py` — payload vocabulary and token
  validation; `application/heartbeat.py` — report assembly, provider evidence,
  policy lookup, local subscription scheduling, and transport;
  `commands/heartbeat.py` — `send`, `enable`, `disable`, `status`, and
  `installations` handlers. `app.py` invokes the sender after a successful
  non-auth, non-heartbeat CLI command.
- `apps/cli/src/ai_stp_cli/local/provider_installations.py` — resolves provider
  identity only when executable bytes match its local release manifest;
  heartbeat collection never executes provider code.
- `apps/platform/src/ai_stp_platform/telemetry_retention.py` — removes old
  heartbeat snapshots with the same tenant raw-retention policy.
- `migrations/versions/0094_heartbeat_policy.py` — adds organization-owned
  enablement, interval, retry bounds, and stale threshold.
- CLI local database migration 46 — stores one organization subscription,
  bound account/device identity, retry count, timestamps, and lease token; it
  stores no heartbeat body or credentials.
- `migrations/versions/0084_installation_heartbeat.py` — table plus tenant RLS
  and the shared `ai_stp_reject_tenant_change` trigger;
  `0085_heartbeat_permissions.py` — seeds `telemetry.read`.

## Ordering

`checked_at` is the client-declared ordering key: a beat applies only when
strictly newer. `received_at` is the server write moment and drives staleness.
A `checked_at` more than `MAX_FUTURE_SKEW` (5 minutes) ahead of the server is
rejected so a skewed client cannot wedge the ordering key. Concurrent beats
serialize on `SELECT … FOR UPDATE` of the coalescing row.

The organization policy defaults to an enabled 6-hour interval, a 60-second
retry base, a 1-hour retry maximum, and a 24-hour stale threshold. The local
sender tries one due organization after a successful ordinary invocation,
oldest first. A 120-second lease lets another invocation recover after a
process stops during a send. Policy lookup and send each use one attempt with
a two-second timeout. A fresh report is built for each attempt, and exponential
retries are capped by the organization retry maximum. Session or network
failure leaves the primary command result unchanged. There is no daemon or OS
scheduler, so a CLI that is not invoked eventually becomes stale.

`heartbeat enable` requires a device-bound authenticated session and an
enabled organization policy. `heartbeat disable` removes the local row without
network access. If the held account or device differs from the enrolled
identity, the subscription is removed and must be explicitly enabled again.

## Health

Computed in `evaluate_health` — declared `disabled` first, then freshness over
`received_at`, then the reported `failing`/`partial`/`active`; no row is
`unknown`. The threshold comes from the organization telemetry policy and
defaults to `DEFAULT_STALE_AFTER` (24h).

## Integration-owned wiring recorded for the orchestrator

- `slices/corporate/router.py`: import `heartbeat`, `include_router`.
- `migrations/env.py`: import `heartbeat_models` for metadata registration.
- CLI dispatch/registry: map `heartbeat send|enable|disable|status|installations`.
- `service.py` role matrix: add `telemetry.read` to seeded superadmin/lead
  permissions for organizations bootstrapped after 0085.
- contracts `__init__` / generated schema exports for the new module.
