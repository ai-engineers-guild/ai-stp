---
description: "Operator notes for the telemetry privacy boundary: storage, retention sweeps, subject rights, and audit."
last_verified: "2026-09-24"
---

# Engineering: telemetry privacy

## Layout

- `ai_stp_platform.telemetry_policy_models` — `TelemetryEvent`,
  `TelemetryPolicy`, `TelemetryRevocation`, `TelemetryAudit` (RLS-protected).
- `ai_stp_platform.telemetry_privacy_service` — closed boundary validation,
  ingest/dedup, list/aggregate/export, rights transitions, privileged-access
  audit records.
- `ai_stp_platform.telemetry_retention` — `apply_retention` (per tenant),
  `apply_retention_all` (sweep), `DEFAULT_RAW_RETENTION_DAYS = 90`; the sweep
  covers `telemetry_event`, `runtime_usage_event`, and expired
  `installation_heartbeat` snapshots by `received_at`.
- `ai_stp_api.slices.corporate.telemetry_policy` — events, aggregates,
  export, policy, audit endpoints.
- `ai_stp_api.slices.corporate.telemetry_rights` — rights, revocation,
  deletion endpoints.
- `ai_stp_worker.handlers.telemetry_retention` — retention job handler.

## Running retention locally

```python
await apply_retention(session, organization_id=org_id, now=datetime.now(UTC))
```

The worker handler accepts `{"organization_id": "..."}` for one tenant or an
empty payload for a full sweep. Job registration is applied at integration.
Tenants with heartbeat-only data are discovered by the sweep. An expired
coalesced row is deleted (and later reads as `unknown`); retention does not
change a row to `stale`.

Migration `0094_heartbeat_policy` adds organization heartbeat enablement,
cadence, retry bounds, and stale threshold to `telemetry_policy`. When an older
client updates a policy without those optional fields, the service preserves
their current values.

## Permissions

`telemetry.write`, `telemetry.read`, `telemetry.list`, `telemetry.export`,
`telemetry.manage`, `telemetry.delete` are seeded for `superadmin` by
migration `0090_telemetry_privacy`.
