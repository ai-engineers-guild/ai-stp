---
description: "Corporate runtime component-usage events: closed coordinates on the authenticated channel, a bounded local outbox, and scoped aggregate reporting."
last_verified: "2026-09-22"
---

# ADR-0201: Runtime usage events and reporting

Status: accepted. Implements GitHub #218 under the #52 seam; coexists with
ADR-0112 by not touching it.

## Context

Corporate Hub needs factual answers about which employee, on which device and
project, invoked which exact setup and component, and with what outcome. The
existing telemetry is a deliberately anonymous consented ping (`ADR-0112`);
bending it toward identified corporate reporting would break both its privacy
posture and its contract. Meanwhile components are untrusted content: giving
them a callback, a destination, or a say in event fields creates an
exfiltration channel (`#52`).

## Decision

A second, separate channel. Events travel as authenticated `/v1` requests under
`/corporate/organizations/{organization_id}/telemetry/...`, resolved against
the existing CLI session - never the anonymous collector, `telemetry.url`, or
`anon`.

The event is a closed field set (`SPEC-088` `REQ-8802`): identities and exact
setup/component coordinates, `invoked_at`, outcome, and a safe correlation id.
The contract model is `extra="forbid"`, the CLI builder's signature is the
field list, and `event_payload` refuses to serialize a dict whose keys are not
exactly the closed set - so a payload field cannot arrive by accident.

The provider runtime adapter is the only sender. It calls
`provider/usage_reporting.record_invocation` after accepting an invocation;
heartbeats, health checks, and lifecycle operations never reach it. Delivery
goes through a bounded SQLite outbox the usage stream owns whole: dedup on the
event key, exponential backoff, a dead state after bounded attempts, row and
age limits, and fail-closed behaviour when full.

Server ingestion deduplicates on `(organization_id, event_id)` so a retried
outbox drain is idempotent, and rejects events whose body names a different
tenant than the authenticated path.

Reporting is aggregates-first: grouped counts with first/last observed use and
distinct employee/device counts, filtered along every event dimension, plus an
installed-vs-invoked comparison against current catalog assignments.
Visibility resolves through the ADR-0179 policy table as data-seeded keys
(`telemetry_usage.ingest/.read/.events/.export`): organization-scoped
principals see the tenant; team-scoped principals see their own events plus
their teams' members; event-level drill-down is separately permissioned and
redacted; export is bounded, idempotent, digested into a durable receipt, and
audited.

## Consequences

Two new tables (`runtime_usage_event`, `runtime_usage_export`) and three
migrations (`0087`-`0089`) own the stream's persistence. New contract, slice,
CLI, provider-seam, and web modules stay inside the stream boundary; wiring
into the app, registry, router, env, and generated indexes is recorded in the
worker receipt for integration. Retention, redaction policy, revocation, and
deletion remain the privacy authority's (`SPEC-089`) responsibility; this
stream stores only what the closed set allows and scopes reads only through
the existing policy table. Rollback removes the new modules, tables, and
permission rows without touching shared code.
