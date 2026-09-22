---
description: "Operator notes for the telemetry privacy boundary: storage, retention sweeps, subject rights, and audit."
last_verified: "2026-09-22"
---

# Engineering: telemetry privacy

## Layout

- `ai_stp_platform.telemetry_policy_models` — `TelemetryEvent`,
  `TelemetryPolicy`, `TelemetryRevocation`, `TelemetryAudit` (RLS-protected).
- `ai_stp_platform.telemetry_privacy_service` — closed boundary validation,
  ingest/dedup, list/aggregate/export, rights transitions, privileged-access
  audit records.
- `ai_stp_platform.telemetry_retention` — `apply_retention` (per tenant),
  `apply_retention_all` (sweep), `DEFAULT_RAW_RETENTION_DAYS = 90`.
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

## Permissions

`telemetry.write`, `telemetry.read`, `telemetry.list`, `telemetry.export`,
`telemetry.manage`, `telemetry.delete` are seeded for `superadmin` by
migration `0090_telemetry_privacy`.
