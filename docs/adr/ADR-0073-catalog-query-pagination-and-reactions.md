---
description: "Catalog QL, two pagination modes, and isolated reactions."
last_verified: "2026-08-09"
---

# ADR-0073: Catalog query, pagination, and reactions

Status: accepted.

## Context

A cursor-only catalog is safe and suitable for the CLI, but the web must display the number of results and pages. A simple substring does not express logical constraints, and client-only validation does not protect the API. Sorting by likes introduces social state, which was previously excluded from the MVP, and must not be mixed with trust evidence.

## Alternatives

1. Replace cursor pagination with offset/page pagination. This breaks the CLI and reduces stability.
2. Keep cursor-only pagination and calculate pages on the client. An exact total cannot be obtained, and traversing all pages is expensive and unstable.
3. Support mutually exclusive cursor and page modes, a unified AST, and a separate reactions aggregate.

## Decision

Alternative 3 was selected. Catalog QL is parsed by a custom bounded lexer/parser into a typed, allowlisted AST. Structural filters are combined with the AST using `AND`. A plain string remains a full-text term. Cursor mode retains opaque keyset semantics; page mode returns a total only for the already authorized public result set. `cursor` and `page` are incompatible.

The public projection stores only the non-negative `likes_count` aggregate, separately from passports, verification, trust, and support. The source of changes to individual reactions is outside the scope of this decision and is not exposed through the catalog API. `likes` sorting has the stable tie-breaker `updated_at, stable_id`.

## Consequences

OpenAPI and fixtures receive additive fields/parameters. Indexes are required for the public projection, filters, full-text/trigram search, and the reaction aggregate. Count must not include hidden/private rows. The frontend parser is a UX aid, but the backend repeats all validation. Any grammar extension requires a version and a golden corpus.

## Reconsideration Criteria

This decision will be reconsidered if exact count does not fit within the performance budget, if the catalog moves to an external search engine, or if social functionality is again excluded by a product decision.
