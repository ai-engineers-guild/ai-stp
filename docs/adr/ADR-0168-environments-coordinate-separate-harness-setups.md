---
description: "ADR-0168: Project environments coordinate separate harness setup operations."
last_verified: "2026-09-07"
---

# ADR-0168: Environments coordinate separate harness setups

Status: accepted

## Context

Projects can use several harnesses. Their environment is not a setup shared between
products: a setup belongs to one harness. The existing multi-root coordinator records
ordered application and reverse recovery but requires one SetupVersion and disjoint
whole target roots.

## Decision

Extend the coordinator with an environment transaction kind composing exact child
plans for separate harnesses of one project. Children retain setup and provider
identities. Complete native footprints define reservations, allowing disjoint
surfaces in one project and refusing shared or nested contributions before effects.

Approval binds the aggregate and every child plan. Application and compensation
resolve providers independently and retain durable state semantics. SPEC-069 owns
acceptance criteria.

## Consequences

Agents can review one project environment while returning to each harness's saved
original setup. Shared-path conflicts require a revised plan; the coordinator never
chooses a winner implicitly. Existing single-setup multi-root transactions remain
readable with unchanged digests.
