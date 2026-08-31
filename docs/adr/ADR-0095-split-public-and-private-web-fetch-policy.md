---
description: "ADR-0095: Split public cacheable and private request-scoped web fetch policy."
last_verified: "2026-08-15"
---

# ADR-0095: Split public and private web fetch policy

Status: proposed.

## Context

The locale layout forces the entire tree to be dynamic. At the same time, the
shared `apiRequest` reads `cookies()` and sets `cache: "no-store"` even for the
anonymous catalog. This prevents Next.js from safely caching public RSC reads,
creates unnecessary server work during navigation, and mixes two distinct trust
boundaries. The catalog page also performs independent loads sequentially, while
explicit prefetch starts expensive RSC routes before the user expresses intent.

## Options

1. Keep one helper and add a `public/cache` flag. The change is compact, but the
   default is easy to choose incorrectly, while credential-bearing options stay
   next to the shared cache and make a privacy mistake too easy.
2. Cache the entire locale tree. This provides a high hit rate but is
   incompatible with request-dependent projection and private routes.
3. Split typed entry points and cache only confirmed public GET calls, leaving
   dynamic state in minimal boundaries. This adds explicit code, but makes
   cacheability and the credential boundary verifiable.

## Decision

Option 3 is selected.

- Introduce a separate public GET helper without cookies/session access and a
  separate private request helper with `no-store`.
- The public helper uses one short named `revalidate` policy only for confirmed
  anonymous catalog/public-profile callers. Do not apply the cache to private,
  mutation, binary, or operation-meta paths.
- Remove the shared `force-dynamic`; keep projection/canonical request state in
  the smallest dynamic boundary so it does not contaminate data-page caching
  policy.
- Parallelize independent catalog reads; constrain publisher-profile fan-out to
  unique IDs and controlled concurrency/deduplication.
- Do not force prefetch for heavy, private, or high-cardinality routes. Explicit
  prefetch is allowed only for a small stable navigation allowlist.

## Consequences

The public catalog may be stale for no longer than the accepted short TTL;
`revalidatePath` after public mutations remains an accelerated convergence path.
Private UI remains request-scoped. New public endpoints must explicitly pass a
privacy review before using the public helper. Tests must pin the allowed-path
list, TTL, absence of credentials, concurrency, and hydration output.

No data migration is required. Rollback consists of returning public callers to
the private/no-store helper and dynamic override; wire contracts do not change.

## Reconsideration conditions

The decision is reconsidered if the API adds a personalized catalog response,
Next.js changes the cache/dynamic semantics of the runtime baseline in use, a
tag-based invalidation contract appears, or measurements show that the selected
TTL violates the product freshness SLO.
