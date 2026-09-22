---
description: "Runtime usage visibility: identity bound to the caller, team-scoped narrowing, separately permissioned drill-down, digested export receipts, and the retention seam delegated to SPEC-089."
last_verified: "2026-09-22"
---

# ADR-0202: Runtime usage visibility and governance seam

Status: accepted. Implements GitHub #218 under the #52 seam; companion to
ADR-0201, which owns the event boundary and the outbox.

## Context

Usage events are sensitive twice over: they name an employee, a device, and a
project, and they accumulate a per-person record of what was run. Three
questions needed a decision that the event format alone does not answer.

First, who an event is about. A payload-declared `employee_id` or `device_id`
is attacker-controlled input: a forged identity would let one device write
usage history for another employee, or place events under a project that does
not exist.

Second, who may read what. An organization lead legitimately needs the
tenant's aggregate picture; a team lead needs their own team's; neither needs
raw event rows, and event-level detail is a materially different disclosure
than a count.

Third, how long raw events live. Retention, revocation, and redaction belong
to the telemetry-privacy authority (SPEC-089), which lands on a different
branch - but usage reads and writes must already behave as if that boundary
exists.

## Options

- *Trust the payload's identities.* Simplest; also makes every event
  forgeable, and the report answers become fiction.
- *A dedicated usage RBAC layer.* Duplicates the ADR-0179 scoped-policy
  machinery that already resolves organization/team authority.
- *Hard dependency on the privacy tables.* Correct end state, but couples
  this stream's merge order to the privacy stream's and breaks independent
  verification.
- *Identity binding + scoped resolution + an optional governance seam.*
  Events bind to the authenticated caller; visibility resolves through the
  existing policy table; the privacy tables are read when present and a
  documented default applies when absent.

## Decision

Identity is bound, never declared. Ingestion accepts an event only when its
`employee_id` is the caller's account and its `device_id` is the session's
device - or, for a session without a device binding, an active device the
caller's own account holds. `project_id` must name an active corporate
project in the same tenant. Anything else is rejected, counted, and never
stored.

Visibility resolves through `has_corporate_permission` with the four
data-seeded keys. An organization-scoped grant is unrestricted; otherwise the
caller sees their own events plus active members of the teams where a
team-scoped binding grants the permission. Requested `employee_id`/`team_id`
filters intersect with that scope - a filter can narrow to empty, never
widen. The installed-vs-invoked section shows a scoped caller only the
assignments addressed to their employees, their teams, or the whole
organization.

Three permissions, three surfaces: `telemetry_usage.read` for aggregates,
`telemetry_usage.events` for the redacted drill-down page, and
`telemetry_usage.export` for the bounded export. Exports carry aggregate rows
only, are idempotent on their key, and persist a digested receipt plus an
audit row.

The retention seam is read, not owned. When `telemetry_policy` exists, its
`raw_retention_days` bounds both ingest acceptance (older events are
rejected) and every read (the window is a read-time clause, so a report can
never surface an event the privacy executor has not yet swept). When
`telemetry_revocation` exists, revoked or deleted subjects are refused at
ingest and suppressed from drill-down while aggregate counts are preserved -
anonymization keeps the numbers, per SPEC-089. Absent either table, the
documented 90-day default applies and nothing is suppressed.

## Consequences

The service accepts `now` so window behaviour is testable deterministically.
The seam means usage tests run green before the privacy merge, and merge order
between the two streams stays free. The migration seeds permission rows for
orgs that exist; new-tenant seeding through the bootstrap role matrix is
recorded in the worker receipt as integration wiring. A payload identity is
treated as a claim to verify, which is the rule the binding enforces.

## Revisit conditions

- The privacy stream lands and owns the policy/revocation tables: the stub
  reads become its authoritative contract and the default disappears.
- A subject kind beyond employee/device appears (service principals emitting
  runtime usage): the binding rule needs a principal-type branch.
