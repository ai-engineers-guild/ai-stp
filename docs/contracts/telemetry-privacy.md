---
description: "Telemetry privacy contract: closed event boundary, policy, rights, retention, audit, and deletion routes."
last_verified: "2026-09-24"
---

# Contract: telemetry privacy

HTTP surface: `/v1/corporate/organizations/{organization_id}/telemetry/*`,
authenticated bearer sessions, tenant-scoped, permission-gated.

## Endpoints

| Method | Path | Permission | Purpose |
| --- | --- | --- | --- |
| POST | `/events` | `telemetry.write` | Ingest one heartbeat/invocation event |
| POST | `/events/batch` | `telemetry.write` | Ingest a deduplicated batch (distinct ids) |
| GET | `/events` | `telemetry.list` | Bounded raw event page, audited |
| GET | `/aggregates` | `telemetry.read` | Day/kind/outcome counts, audited |
| GET | `/export` | `telemetry.export` | Bounded export (max 1000 rows), audited |
| GET | `/audit` | `telemetry.list` | Governance audit trail page |
| GET | `/policy` | `telemetry.read` | Current tenant policy |
| PUT | `/policy` | `telemetry.manage` | Optimistic-locked policy write |
| POST | `/rights` | `telemetry.manage` | Record notice/legal basis for a subject |
| POST | `/rights/{subject_kind}/{subject_id}/revocation` | `telemetry.delete` | Revoke subject, optional anonymization |
| POST | `/deletions` | `telemetry.delete` | Erasure: `delete` or `anonymize` |

## Boundary rules

Event `kind` is `heartbeat` or `invocation`; the field set per kind is closed.
Forbidden at any depth: credentials, secrets, tokens, prompts, payloads,
content, local paths, environment values, repository identifiers. Rejection
is `422` at contract validation or `400` at the platform boundary; a revoked
or erased subject yields `409`.

## Idempotency

All mutations carry `idempotency_key` and `authorization_revision`; replays
return the stored receipt body. Event ingestion deduplicates on
`(organization_id, event_id)`.

## Policy fields

The policy also governs installation heartbeats:

| Field | Default | Bounds |
| --- | ---: | ---: |
| `heartbeat_enabled` | `true` | boolean |
| `heartbeat_interval_seconds` | 21600 | 300–2592000 |
| `heartbeat_retry_base_seconds` | 60 | 30–86400 |
| `heartbeat_retry_max_seconds` | 3600 | 60–604800 and at least the retry base |
| `heartbeat_stale_after_seconds` | 86400 | 60–31536000 |

Old policy clients may omit these fields; an update preserves current values.
The CLI's automatic sender requires its separate local opt-in. A disabled
organization rejects new heartbeat writes. Retention deletes coalesced
`installation_heartbeat` rows using `received_at` and the same raw retention
window; a deleted row reads as `unknown`.
