---
description: "Engineering notes for the corporate installation heartbeat stream (t-heartbeat, GitHub #215)."
last_verified: "2026-09-22"
---

# Telemetry heartbeat engineering

## Layout

- `packages/contracts/src/ai_stp_contracts/heartbeat.py` — closed request,
  stored-row view, own-status view, list view; the capability-token and
  cli-version alphabets.
- `apps/platform/src/ai_stp_platform/heartbeat_models.py` — the
  `installation_heartbeat` table model, one row per `(organization, device)`.
- `apps/platform/src/ai_stp_platform/heartbeat_service.py` — coalescing write,
  ordering guard, read-time health projection.
- `apps/api/src/ai_stp_api/slices/corporate/heartbeat.py` — the three routes.
- `apps/cli/src/ai_stp_cli/heartbeat.py` — payload vocabulary and token
  validation; `application/heartbeat.py` — report assembly and transport;
  `commands/heartbeat.py` — `send`, `status`, `installations` handlers.
- `migrations/versions/0084_installation_heartbeat.py` — table plus tenant RLS
  and the shared `ai_stp_reject_tenant_change` trigger;
  `0085_heartbeat_permissions.py` — seeds `telemetry.read`.

## Ordering

`checked_at` is the client-declared ordering key: a beat applies only when
strictly newer. `received_at` is the server write moment and drives staleness.
A `checked_at` more than `MAX_FUTURE_SKEW` (5 minutes) ahead of the server is
rejected so a skewed client cannot wedge the ordering key. Concurrent beats
serialize on `SELECT … FOR UPDATE` of the coalescing row.

## Health

Computed in `evaluate_health` — declared `disabled` first, then freshness over
`received_at`, then the reported `failing`/`active`; no row is `unknown`. The
threshold is an injectable parameter (`DEFAULT_STALE_AFTER` = 24h) so the
privacy stream can supply the organization override without changing this
module.

## Integration-owned wiring recorded for the orchestrator

- `slices/corporate/router.py`: import `heartbeat`, `include_router`.
- `migrations/env.py`: import `heartbeat_models` for metadata registration.
- CLI dispatch/registry: map `heartbeat send|status|installations`.
- `service.py` role matrix: add `telemetry.read` to seeded superadmin/lead
  permissions for organizations bootstrapped after 0085.
- contracts `__init__` / generated schema exports for the new module.
