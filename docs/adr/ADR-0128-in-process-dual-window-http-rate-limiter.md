---
description: "Decision to enforce a single node's HTTP rate limit with two sliding windows in the API process rather than Redis, SlowAPI, or Caddy."
last_verified: "2026-08-28"
---

# ADR-0128: Single-node HTTP limiter — two in-process sliding windows

Status: accepted. Clarifies `SPEC-010` `REQ-1015`. The proxy named in its context changed with `ADR-0135-nginx-is-the-only-edge-proxy.md`; the fact the decision rests on did not, because `request.client.host` is still the adjacent peer rather than the public client, and is now the host's nginx.

## Context

Public `/v1` already rejects excess requests with the `AI_STP_RATE_LIMITED`
code and the `Retry-After` header. There used to be one policy: 120 requests
per 60 seconds for each tuple of HTTP method, route template, and transport
address. This provides neither a process-wide ceiling nor an hourly budget per
address: one client can pass through many templates, while one hundred clients
on one template share a single bucket.

The MVP needs two independent budgets: no more than 100 requests per minute
for the whole node and no more than 1000 requests per hour from one transport
address. The operator must be able to configure both counts and both windows
without a new code release. Missing variables must not restore unlimited
access: `maximum=0` in the existing `SlidingWindowLimiter` allows everything.

`SPEC-010` still excludes Redis from the MVP. The `ADR-0040` topology keeps
Caddy as the sole public endpoint, while uvicorn does not enable
`proxy-headers`: today `request.client.host` is the adjacent peer (Caddy or
`web`), not the public client.

## Options

1. **SlowAPI** with `application_limits` (global budget) and `default_limits`
   (by `key_func`, usually IP). Its documented model has exactly two buckets;
   the in-memory backend is for one process. Rejected: a new dependency, a
   separate error path instead of the existing envelope, and its documentation
   introduces Redis as soon as there is a second worker—which `SPEC-010` does
   not promise anyway.
2. **fastapi-limiter / Redis.** An exact counter across multiple replicas.
   Rejected: Redis is outside the MVP boundary and deployment has one API
   process.
3. **Caddy `rate_limit` or a separate proxy container.** A limit at the system
   boundary. Rejected for the MVP: a second mechanism, a second set of values,
   and rejection no longer passes through the `AI_STP_RATE_LIMITED` envelope.
4. **Two sliding windows on the existing in-process limiter.** Accepted. The
   algorithm, key eviction, and `now=` injection are already in the tree; only
   *what* is counted changes.

## Decision

The API process HTTP gate consists of two independent sliding windows ahead of
the route handler:

- a process-wide window with one key for all requests, defaulting to 100 per 60 seconds;
- a transport-peer window (`request.client.host`, otherwise `unknown`),
  defaulting to 1000 per 3600 seconds.

Both limits and both windows are configured through env
(`AI_STP_API_RATE_LIMIT_OVERALL_*`, `AI_STP_API_RATE_LIMIT_IP_*`). Missing
variables retain these values. An explicit `0` disables only that dimension.
Both windows are checked before either is recorded, so a rejection does not
consume the other budget. Method and route template are not part of the key:
the old 120/route/minute policy is replaced, not added. `X-Forwarded-For` and
`Forwarded` headers are not treated as the address until a separate trusted
proxy decision exists. The error code and dependency do not change: `429`,
`AI_STP_RATE_LIMITED`, and `Retry-After` for the window that rejected.

## Consequences

- `REQ-1015`, `docs/contracts/http-api.md`, and
  `docs/operations/production-readiness.md` state the same values.
- The old `AI_STP_API_RATE_LIMIT_REQUESTS` /
  `AI_STP_API_RATE_LIMIT_WINDOW_SECONDS` are no longer read: service settings
  use `extra=ignore` so that a previous `0` cannot expose the public API.
- While uvicorn lacks `proxy-headers`, “one IP” means the Caddy/`web` peer. This
  is a limitation of the decision, not a hidden `X-Forwarded-For` behavior.
- 100 requests per minute for the whole process is stricter than the previous
  120 per template: health, web SSR, and CLI share one bucket. Routes have no
  exceptions until measurement shows that probes themselves exhaust the budget.
- A second worker or replica again makes the in-memory counter local; this was
  already true and remains a reason to revisit the decision.

## Revisit conditions

- A second replica or multiple uvicorn workers are introduced while retaining one logical budget.
- A decision is accepted to trust a hop-by-hop identifier behind Caddy
  (`Forwarded` / `X-Forwarded-For` only from a named proxy).
- Readiness probes themselves hit the global budget in the deployed environment.
- A separate policy class is needed for ingress, reporting, or writes.
