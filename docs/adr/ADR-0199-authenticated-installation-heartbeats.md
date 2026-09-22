---
description: "Installation heartbeats ride the authenticated corporate channel; identity comes from the session, writes coalesce by checked_at."
last_verified: "2026-09-22"
---

# ADR-0199: Authenticated installation heartbeats

Status: accepted. Relates to ADR-0112 (anonymous ping), ADR-0039 (corporate
authorization).

## Context

Corporate tenants need installation liveness that the anonymous, consented
telemetry ping cannot provide: it is unauthenticated, untyped per device, and
deliberately carries no identity. A second channel must be authenticated,
tenant-scoped, and idempotent — retries, clock skew, and queued writes are the
normal case for a periodic CLI beat.

## Options

- Extend the anonymous ping with identity — rejected: it would weaken the
  privacy posture of a channel whose value is precisely that it holds none.
- Append-only heartbeat log — rejected: liveness asks for the latest state, an
  append log buys storage cost and read complexity for history nobody reads.
- One coalescing row per `(organization, device)` over the authenticated
  `/v1/corporate` surface — chosen.

## Decision

The heartbeat is `PUT /v1/corporate/organizations/{organization_id}/telemetry/heartbeat`.
The request carries the closed field set (`account_id`, `device_id`,
`cli_version`, `capabilities`, `last_sync_at`, `health_state`, `checked_at`);
the handler additionally binds both identifiers to the authenticated session,
so a body cannot claim another identity. Ordering and idempotency share one
key: a beat lands only when its client-declared `checked_at` is strictly newer
than the stored one. Replays and delayed writes return the stored state
unchanged; beats ahead of the server clock beyond five minutes are rejected so
a skewed client cannot poison the ordering key.

## Consequences

One row per installation; no cleanup job. Concurrency is serialized by
`SELECT ... FOR UPDATE` on the coalescing row. New permission `telemetry.read`
is seeded as data; the evaluator is unchanged. Rollback is `downgrade()` of
migrations 0084–0085 plus removing the router include.

## Revisit conditions

An organization-level override of the staleness threshold lands in the privacy
stream's policy surface; multi-installation-per-device reporting; or a second
writer kind (service principal) that needs a different identity binding.
