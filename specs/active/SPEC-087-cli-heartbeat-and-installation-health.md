---
description: "SPEC-087: Authenticated CLI installation heartbeats and read-time installation health for corporate tenants."
last_verified: "2026-09-24"
---

# SPEC-087: CLI heartbeat and installation health

## Purpose

Give a corporate tenant a governed view of which CLI installations are alive,
which are silent, and which have reported failure — without collecting prompts,
model traffic, arguments, paths, environment values, or secrets.

## Scope

This specification owns the authenticated installation heartbeat write, its
coalescing and ordering semantics, the closed health-state projection, the
role-gated reads, and the CLI's opt-in automatic sender. SPEC-013 remains
authoritative for data governance; the anonymous consented ping
(`REQ-1316`–`REQ-1319`, `ADR-0112`) is a separate channel and is untouched.
Runtime component invocation and usage reporting belong to the usage stream and
are out of scope here. Tenant privacy policy, retention, and revocation values
are owned by SPEC-089.

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
- `Subscription` — this CLI installation's explicit local opt-in for one
  organization, bound to the account and device used to enroll it.

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
- `REQ-8704`: Health is a deterministic read-time projection using the
  organization's `heartbeat_stale_after_seconds` (default 86400): `disabled` is
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
- `REQ-8709`: The CLI exposes `heartbeat send`, `heartbeat status`,
  `heartbeat installations`, `heartbeat enable`, and `heartbeat disable`.
  Explicit writes and reads use the held device-bound session. Automatic
  reporting is off until `heartbeat enable --organization <id>` succeeds for
  an organization whose policy permits reporting. `heartbeat disable` removes
  local opt-in without network access.
- `REQ-8710`: After a successful ordinary CLI command, the CLI may claim at
  most one due local subscription, oldest due first. It builds a fresh report
  and attempts policy lookup and write with one bounded network attempt each;
  heartbeat and auth commands do not invoke the sender. A claimed lease expires
  so a stopped process does not strand a subscription. Any automatic-send
  failure leaves the primary command result unchanged and schedules a bounded
  exponential retry using the organization retry policy when available.
- `REQ-8711`: The organization policy owns enablement, send interval, retry
  bounds, and staleness. Disabled policy rejects explicit writes and defers
  automatic checks until the configured interval. The defaults are enabled,
  21600 seconds, 60 seconds, 3600 seconds, and 86400 seconds respectively.
- `REQ-8712`: The CLI reports only harnesses detected as locally installed.
  Provider availability and version are reported only when the locally
  resolved provider executable is present and its bytes match its release
  manifest. The heartbeat path never runs provider code. `active` means no
  installed harness needs a provider or all detected providers pass that
  check; `partial` means some pass; `failing` means none pass.
- `REQ-8713`: The automatic sender persists only organization/account/device
  identifiers and bounded schedule metadata locally. It retains no request
  payload or credentials, and sends the last successful sync time only when it
  exists in the local sync cursor. A subscription is discarded if the held
  account or device no longer matches its opt-in identity.

## States and errors

Reported states are `active`, `partial`, `failing`, and `disabled`; reads additionally
project `stale` and `unknown`. Invalid identity, capability, timestamp, or
permission input is rejected before mutation. Equal or older heartbeats are
successful no-ops, while offline writes return the existing typed transport
failure. Automatic reporting is best-effort and does not change the result of
the ordinary command that triggered it. Local opt-in is explicit; a CLI that is
not invoked cannot report and eventually projects `stale`.

## Security and privacy

The route requires an authenticated corporate session and binds account and
device identifiers to that session. Authorization is evaluated before tenant
reads, and the closed payload excludes secrets, prompts, paths, and invocation
data. Local automatic reporting requires explicit opt-in, is bound to the
enrolled account and device, and does not run provider code. Heartbeats are not
runtime usage events.

## Compatibility and migration

Heartbeat storage and permission seeds are additive migrations. Migration 0094
adds organization heartbeat policy fields; the CLI local registry migration 46
adds opt-in and bounded retry state. Existing rows remain valid when migration
0093 adds `partial` to the heartbeat check.
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
| `REQ-8709` | CLI command and transport tests cover the explicit lifecycle commands and typed offline failure. |
| `REQ-8710` | Local schedule tests cover single claims, lease recovery, and retry backoff; the CLI entrypoint test proves sender failure does not change a successful command. |
| `REQ-8711` | Policy contract, API, and health projection tests cover defaults, bounds, enablement, and configurable staleness. |
| `REQ-8712` | Provider installation tests cover resolved digest-matched manifests and payload redaction. |
| `REQ-8713` | CLI tests prove idempotent opt-in, account/device rebinding, opt-out, and the absence of a stored payload. |
