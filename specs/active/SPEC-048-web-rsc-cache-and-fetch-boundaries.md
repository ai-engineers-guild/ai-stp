---
description: "SPEC-048: Fast RSC catalog, explicit public/private fetch boundaries, and controlled prefetch."
last_verified: "2026-08-15"
---

# SPEC-048: Web RSC cache and fetch boundaries

## Purpose

Speed up the public web catalog and eliminate stale or unnecessary RSC transitions:
public data receives a short bounded cache, private requests remain strictly
request-scoped, independent loads run in parallel, and router prefetch does not
create expensive RSC requests without explicit user benefit.

## Scope

Issue #354 includes:

- removing the global `force-dynamic` from the locale layout;
- explicitly separating public and private server API helpers;
- a short Next.js `fetch` cache for anonymous catalog reads;
- parallel loading of independent catalog resources and publisher profiles;
- disabling unnecessary prefetch for expensive, private, and high-cardinality links;
- regression tests for cache policy, session isolation, parallelism, and navigation.

Changes to API schemas, the domain-level freshness of catalog records, CDN policy,
catalog redesign, a new client-side data layer, or relaxed authorization are out
of scope.

## Terms

- **Public fetch** — a server-side GET to a documented anonymous endpoint that
  does not read cookies, does not forward session/CSRF data, and permits a shared cache.
- **Private fetch** — a request that depends on an account/session or modifies data;
  it always runs with `no-store` and is never shared across requests.
- **Short catalog cache** — a bounded `revalidate` interval for public catalog
  reads; the exact value is defined by a single named constant and covered by a test.
- **Expensive prefetch** — automatic RSC prefetch of a route that triggers a
  catalog search, private read, or another multi-resource server-side load.

## Requirements

- `REQ-4801`: The global locale layout does not declare `dynamic = "force-dynamic"`.
  Request-dependent projection/canonical state is isolated within the smallest
  dynamic boundary so that public pages determine their own caching mode.

- `REQ-4802`: Public and private API helpers have separate typed entrypoints.
  The public helper accepts only `GET`, does not call `cookies()`, and does not
  accept a session token, Cookie, Authorization, or CSRF headers. The private
  helper retains request-scoped headers and `cache: "no-store"`; mutation/binary/meta
  paths remain private.

- `REQ-4803`: Only confirmed anonymous catalog/public-profile GET endpoints use
  a short cache through `next.revalidate` with stable cache semantics.
  Auth/account/devices/objects/grants/reports/staff and all mutations are not cached.

- `REQ-4804`: The catalog page starts independent reads concurrently. Components
  and setups when `resource=all`, external products, and the subsequent batch of
  unique publisher profiles do not form an artificial sequential waterfall.
  Partial failure preserves the existing safe UI semantics.

- `REQ-4805`: Explicit router prefetch remains only for inexpensive, bounded,
  and likely transitions. Links to private pages, high-cardinality object/version
  pages, and catalog filter/pagination routes specify `prefetch={false}` or do not
  force prefetch, according to a single documented rule.

- `REQ-4806`: Cache invalidation after publication and changes to public presentation
  does not promise immediate global consistency: the current `revalidatePath`
  calls remain, and public results converge no later than the short TTL. Private UI
  does not receive a cached response after a mutation.

- `REQ-4807`: The change does not introduce hydration warnings or stale cross-account UI.
  The production build, unit/component tests, and browser smoke tests contain no new
  hydration mismatch messages; two different session contexts do not share data.

## States and errors

- `public_fresh` — the public fetch was served from the network or a valid short cache;
- `public_revalidating` — an expired entry is being refreshed by Next.js;
- `public_unavailable` — the existing typed API/UI error is preserved;
- `private_ready` — the response belongs to the current request/session;
- `private_unauthorized` — the non-enumeration/auth error is preserved without a cache fallback.

The public cache does not turn a transport failure into a successful empty catalog.
The private helper does not fall back to the public helper.

## Security and privacy

- The cache key never contains, and the cache entry never stores, Cookie,
  Authorization, CSRF, an account-scoped response, or the existence of a private object.
- The public helper rejects credential-bearing options at the TypeScript API level
  and is verified by negative tests.
- Separating the helpers does not change server-side authorization or non-enumeration.
- Logs and test fixtures do not contain session/cookie values.

## Compatibility and migration

The change does not modify wire contracts and does not require data migration. Rollout:
first add helper functions and policy tests, then migrate confirmed public calls,
then remove the global dynamic override, introduce parallel loading, and clean up prefetch.
Rollback returns callers to the private/no-store helper and global dynamic rendering;
the data and API remain compatible.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-4801` | A static source test prohibits the global `force-dynamic`; the production build successfully builds the public and private route trees. |
| `REQ-4802` | Unit tests prove the absence of `cookies()` and credential headers in the public path and the presence of `no-store` in private/mutation paths. |
| `REQ-4803` | Fetch-spy tests verify a single short `revalidate` policy only for allowlisted anonymous endpoints. |
| `REQ-4804` | A deferred-promise test proves the concurrent start of component/setup/services reads and bounded parallel profile reads. |
| `REQ-4805` | Component/source tests verify `prefetch={false}` on expensive/private/high-cardinality links and the absence of forced prefetch without an allowlist. |
| `REQ-4806` | Mutation tests preserve the required `revalidatePath` calls; a cache-policy test establishes TTL convergence and private no-store behavior. |
| `REQ-4807` | `just web-check` and browser smoke tests for catalog/login-account transitions pass without hydration mismatch; the isolation test uses two session contexts. |
