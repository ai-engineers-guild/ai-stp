---
description: "Installation health is a deterministic read-time projection with an injectable clock; nothing mutates rows to mark them stale."
last_verified: "2026-09-22"
---

# ADR-0200: Read-time installation health

Status: accepted. Builds on ADR-0199.

## Context

Health states `active`, `stale`, `failing`, `disabled`, `unknown` must be
deterministic and testable. The obvious implementation — a worker that scans
and marks rows stale — adds a clock dependency inside storage, races with
late-arriving beats, and makes every answer depend on when the scanner last
ran.

## Options

- Worker marks stale rows — rejected: state in the row can disagree with the
  answer the read should give, and the sweep interval becomes part of the
  contract.
- Stored health column updated on write — rejected: freshness changes between
  writes; a stored `active` silently becomes false.
- Read-time projection — chosen.

## Decision

The row stores only reported facts (`reported_state`, `checked_at`,
`received_at`). Health is computed at read time: `disabled` wins as a
declaration, then freshness over the server's `received_at` against an
injectable staleness threshold (default 24 hours) projects `stale`, then the
reported `failing` or `active` applies, and no row is `unknown`. The clock and
threshold are parameters of the service functions, so tests are deterministic
and the privacy stream's organization policy can inject its override without
touching this module.

## Consequences

Every answer carries `evaluated_at` and `stale_after_seconds`, so callers can
verify which threshold produced it. `received_at` — not client `checked_at` —
drives staleness, because a client cannot push the server clock into the
future. No worker handler exists for staleness.

## Revisit conditions

Per-installation thresholds; health-driven alerting that needs a stored
transition edge rather than a projection.
