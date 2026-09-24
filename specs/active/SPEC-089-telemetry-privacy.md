---
description: "SPEC-089: Corporate telemetry privacy boundary, retention, access, and data rights."
last_verified: "2026-09-24"
---

# SPEC-089: Telemetry privacy and governance

## Purpose

Give corporate tenants one enumerable, tenant-isolated telemetry governance
surface: a closed event boundary, per-tenant retention and legal-basis policy,
subject rights (notice, revocation, anonymization, deletion), and an
append-only audit of every privileged access. This surface is the authority
that heartbeat (#215) and runtime usage (#218) streams obey.

## Scope

Owns milestone B2B-04 issue #219: the closed event/heartbeat boundary,
`telemetry_event`/`telemetry_policy`/`telemetry_revocation`/`telemetry_audit`
storage, retention execution, data rights, privileged-access audit, and the
governed HTTP surface under `/v1/corporate/organizations/{id}/telemetry/*`.

## Terms

- `Telemetry event` — one retained row of kind `heartbeat` or `invocation`,
  identified by `(organization_id, event_id)`.
- `Boundary` — the closed allowlist of event fields plus the forbidden
  name/value scan; enforced at contract (`extra="forbid"`), platform, and
  storage layers.
- `Policy` — per-tenant `raw_retention_days`, `aggregate_retention_days`,
  `legal_basis`, `notice_text`, `notice_revision`, monotonic `policy_version`.
  It also owns heartbeat enablement, send interval, retry bounds, and the
  read-time stale threshold.
- `Revocation` — per-subject (`account` or `device`) record of notice, legal
  basis, and the `active`/`revoked`/`deleted` state machine.
- `Telemetry audit` — append-only `telemetry_audit` row for every privileged
  read, search, export, policy or rights write, deletion, and retention run;
  carries counts and identifiers, never event payloads.

## Requirements

- `REQ-8901`: Event fields are a closed enumerable set per kind. Unknown keys,
  forbidden names at any nesting depth, absolute local paths, and
  `NAME=value` environment-style values are rejected before storage.
- `REQ-8902`: Stored events carry no prompt, input, output, repository
  content, credential, local path, or environment value; no column exists
  that could hold one.
- `REQ-8903`: Every read, aggregate, export, mutation, and deletion requires
  tenant membership and the matching `telemetry.*` permission; all tables are
  protected by PostgreSQL row-level security on `organization_id`.
- `REQ-8904`: Repeated ingestion of the same `event_id` is idempotent and
  returns the stored row; mutations use the existing idempotency-receipt
  machinery.
- `REQ-8905`: Retention deletes raw events older than the tenant
  `raw_retention_days` (default 90 when no policy exists) across every
  governed raw table: `telemetry_event`, stream-owned `runtime_usage_event`,
  and coalesced `installation_heartbeat` rows. Event tables use their
  occurrence/invocation timestamp; installation heartbeats use `received_at`.
  Tenants with only heartbeat rows are included in the sweep. The pass is
  idempotent and runnable per tenant or as a worker sweep; deleting an old
  installation row makes its
  status project `unknown` and never writes `stale`.
- `REQ-8906`: Revocation of an account or device subject blocks subsequent
  telemetry event and installation-heartbeat writes for that subject; optional
  anonymization strips subject identifiers while preserving aggregate counts.
- `REQ-8907`: Erasure supports `delete` (physical row removal) and
  `anonymize` (identifier stripping); both are idempotent and terminal for
  the subject record. In stream-owned tables whose subject columns are NOT
  NULL (`runtime_usage_event`, `installation_heartbeat`) both modes erase by
  physical row removal; in-place anonymization exists only where the schema
  permits identifier stripping (`telemetry_event`).
- `REQ-8908`: Policy writes are optimistic-concurrency checked through
  `expected_policy_revision`; `notice_revision` and `notice_text` bind the
  employee notice shown for the telemetry context.
- `REQ-8909`: Every privileged operation appends both a platform `audit_event`
  row and a `telemetry_audit` row whose detail contains only counts, kinds,
  and identifiers. An audit-list read records its own access before selecting
  the page, so its first page includes that read event.

## Boundaries

- The anonymous consented ping of ADR-0112 is untouched; corporate telemetry
  is an authenticated, tenant-scoped channel under `/v1`.
- Heartbeats and provider health checks emit no usage events.
- General telemetry aggregates group by day/kind/outcome only. The Corporate
  dashboard's separately authorized health query (SPEC-091) may group by
  permissioned account/device/team IDs; it audits each read and never returns
  event payloads.

## States and errors

Policies use monotonically increasing revisions. Subjects move from `active` to
`revoked` or terminal `deleted`; repeated rights requests are idempotent.
Retention, policy, authorization, boundary, and revision failures reject
before protected data changes and preserve the append-only audit trail. A
heartbeat policy update preserves any field omitted by a legacy client; the
heartbeat defaults are enabled, 21600-second interval, retry delays of 60 to
3600 seconds, and a 86400-second stale threshold.

## Security and privacy

Every governed operation requires tenant membership and its specific
`telemetry.*` permission, with organization row-level isolation. Closed event
validation runs before storage, and audit details contain only counts, kinds,
and identifiers. Secrets, prompts, paths, and payload contents are never
returned by governance endpoints.

## Compatibility and migration

Privacy tables, policies, permissions, and audit columns are additive
migrations. Migration 0094 adds heartbeat settings to `telemetry_policy` with
defaults that preserve existing behavior. Tenants without a policy use the
90-day retention default and heartbeat defaults, so existing data remains
readable under bounded retention. Rollback refuses customized heartbeat policy
values before removing those fields.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-8901` | Privacy and contract tests reject unknown keys, forbidden names, paths, and environment-style values. |
| `REQ-8902` | Storage and response tests prove forbidden prompt, model, repository, credential, path, and environment data is absent. |
| `REQ-8903` | API authorization and migration tests cover tenant membership, permission checks, and organization isolation. |
| `REQ-8904` | Ingestion and idempotency tests prove repeated event identifiers return the stored row without duplication. |
| `REQ-8905` | Retention tests cover default and tenant windows, all raw tables, heartbeat rows, repeat runs, and sweep tenant discovery. |
| `REQ-8906` | Revocation tests block subsequent event and heartbeat writes and preserve aggregate counts during anonymization. |
| `REQ-8907` | Rights tests cover terminal delete and anonymize behavior, including stream-owned physical erasure. |
| `REQ-8908` | Policy API tests cover expected revision, notice text, notice revision, heartbeat settings, and optimistic conflicts. |
| `REQ-8909` | Audit tests prove every privileged operation writes both platform and telemetry audit rows with redacted details. |
