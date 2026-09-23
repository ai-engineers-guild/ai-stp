---
description: "SPEC-087: Authenticated CLI installation heartbeats and read-time installation health for corporate tenants."
last_verified: "2026-09-22"
---

# SPEC-087: CLI heartbeat and installation health

## Purpose

Give a corporate tenant a governed view of which CLI installations are alive,
which are silent, and which have reported failure — without collecting prompts,
model traffic, arguments, paths, environment values, or secrets.

## Scope

This specification owns the authenticated installation heartbeat write, its
coalescing and ordering semantics, the closed health-state projection, and the
role-gated reads that expose it. SPEC-013 remains authoritative for data
governance; the anonymous consented ping (`REQ-1316`–`REQ-1319`, `ADR-0112`) is
a separate channel and is untouched. Runtime component invocation and usage
reporting belong to the usage stream and are out of scope here. Tenant privacy
policy, retention, and revocation surfaces belong to the privacy stream.

## Terms

- `Installation` — one CLI device registration, identified by its stable
  `device` id bound to the authenticated session.
- `Heartbeat` — one write of the closed installation fact set: account and
  device references, `cli_version`, `capabilities`, `last_sync_at`, reported
  `health_state`, and `checked_at`.
- `Reported state` — what the installation declares: `active`, `partial`, `failing`, or
  `disabled`. `stale` and `unknown` are never reported.
- `Health state` — the read-time projection: `active`, `partial`, `stale`, `failing`,
  `disabled`, or `unknown`.
- `Staleness threshold` — the duration after which an installation that has not
  reported is projected `stale`; organization-configurable, default 24 hours.

## Requirements

- `REQ-8701`: A heartbeat is written only through the authenticated corporate
  route `PUT /v1/corporate/organizations/{organization_id}/telemetry/heartbeat`.
  The anonymous telemetry endpoint, `telemetry.url`, and the `anon` identifier
  are never used for it.
- `REQ-8702`: The heartbeat request field set is closed. `account_id` and
  `device_id` must equal the authenticated session's account and device; a
  session without a bound device cannot heartbeat. A claim of another account
  or device is rejected.
- `REQ-8703`: Writes coalesce onto one row per `(organization_id, device_id)`.
  An incoming heartbeat is applied only when its `checked_at` is strictly newer
  than the stored one; equal or older beats return success without mutation.
  A `checked_at` ahead of the server clock by more than the accepted skew is
  rejected.
- `REQ-8704`: Health is a deterministic read-time projection: `disabled` is
  reported state and survives the stale window; a `received_at` older than the
  staleness threshold projects `stale`; a fresh `failing` report projects
  `failing`; a fresh `partial` report projects `partial`; a fresh `active`
  report projects `active`; no row projects
  `unknown`. No worker job rewrites rows to `stale`.
- `REQ-8705`: Stored and returned fields carry no secrets, credentials, local
  paths, prompts, model inputs or outputs, or invocation payloads. Capability
  entries are restricted to a token alphabet (`name` or `name@version`) that
  cannot express paths or arguments.
- `REQ-8706`: A heartbeat is not a component invocation and emits no runtime
  usage event.
- `REQ-8707`: Reads are tenant-scoped. A member reads its own installation
  status. Organization-wide or member-scoped listing requires the
  `telemetry.read` permission, evaluated through the existing corporate
  authorization seam; callers without it see only their own rows.
- `REQ-8708`: The `telemetry.read` permission is seeded as data in the
  migration for `superadmin` and `lead` roles; the authorization evaluator is
  unchanged.
- `REQ-8709`: The CLI exposes the heartbeat as explicit commands —
  `heartbeat send`, `heartbeat status`, and `heartbeat installations` — over
  the held authenticated session. Offline failure is a typed transport
  failure; the caller retries on its own schedule.

## States and errors

Reported states are `active`, `partial`, `failing`, and `disabled`; reads additionally
project `stale` and `unknown`. Invalid identity, capability, timestamp, or
permission input is rejected before mutation. Equal or older heartbeats are
successful no-ops, while offline writes return the existing typed transport
failure.

## Security and privacy

The route requires an authenticated corporate session and binds account and
device identifiers to that session. Authorization is evaluated before tenant
reads, and the closed payload excludes secrets, prompts, paths, and invocation
data. Heartbeats are not runtime usage events.

## Compatibility and migration

Heartbeat storage and permission seeds are additive migrations. Existing
rows remain valid when migration 0093 adds `partial` to the heartbeat check.
Downgrade rejects while partial rows exist rather than changing their meaning.
Clients may omit the heartbeat surface and continue using the anonymous
consented ping unchanged. Rollback disables the new routes and controls while
preserving existing installation data and audit history.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-8701` | Heartbeat unit and corporate API tests prove the authenticated route is separate from anonymous telemetry. |
| `REQ-8702` | Authorization tests reject foreign account, device, and unbound-session claims. |
| `REQ-8703` | Platform tests cover coalescing, ordering, clock skew, and no-op replay. |
| `REQ-8704` | Health projection tests cover active, partial, failing, disabled, stale, and unknown semantics without worker mutation. |
| `REQ-8705` | Contract and heartbeat tests reject extra fields and unsafe capability or payload values. |
| `REQ-8706` | Usage integration tests prove heartbeat writes do not create runtime usage events. |
| `REQ-8707` | Authorization tests cover member self-read and permission-gated organization listings. |
| `REQ-8708` | Migration and permission-seed tests verify `telemetry.read` for the required roles. |
| `REQ-8709` | CLI command and transport tests cover all three commands and typed offline failure. |
