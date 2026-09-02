---
description: "SPEC-010: Server platform and API."
last_verified: "2026-08-28"
---

# SPEC-010: Server platform and API

## Purpose

The minimal platform provides authentication, a public and private registry, devices, synchronization, publication, and administrative operations through a stable API without duplicating the CLI's local business rules.

## Scope

This includes FastAPI `/v1`, PostgreSQL, PostgreSQL-backed jobs, RustFS/S3, Google and GitHub sign-in, a Next.js web interface for the account and public catalog, and Resend. Redis, payments, a browser-based setup editor, a complex marketplace interface, and direct client access to storage are out of scope for the MVP.

The mechanics of the execution layer, background worker, and deployment are detailed in `SPEC-017`, `SPEC-018`, and `SPEC-019`; those rules are not repeated here, and the listed specifications remain their owners.

## Terms

- `API` — a versioned HTTP boundary for the CLI and web interface.
- `Worker` — a job processor with at-least-once delivery and idempotent handlers.
- `RustFS` — S3-compatible storage for immutable artifacts.

## Requirements

- `REQ-1001`: The platform uses FastAPI `/v1`, PostgreSQL, PostgreSQL-backed jobs, and RustFS/S3.
- `REQ-1002`: Sign-in supports Google and GitHub with a separate account-linking flow. OAuth callbacks use an exact same-origin path registered at the provider; the versioned API path is the default, and a deployment may declare a provider-registered compatibility path without accepting a foreign origin, query, fragment, or path separator.
- `REQ-1003`: Authorization is checked for every object and action; an account identifier alone does not grant access.
- `REQ-1004`: Private artifacts are not directly accessible from storage and are served only after object authorization is checked.
- `REQ-1005`: Mutating requests use idempotency keys and optimistic concurrency through a revision or ETag.
- `REQ-1006`: Job processing uses at-least-once delivery, a transactional outbox, bounded retries, and idempotent handlers.
- `REQ-1007`: Administrative reads and changes to verification, visibility, blocking, and permissions create audit events.
- `REQ-1008`: In the MVP, Next.js includes a landing page with the installation command, sign-in, public search, object and version cards, public profiles, an account profile, public profile and privacy settings, devices, the user's own drafts, objects and versions, publication and its state, synchronization state, permissions and invitations, and minimal administrative actions.
- `REQ-1009`: Resend is used only for approved email scenarios, including invitation delivery, and does not become an identity source.
- `REQ-1010`: The API supports the declared CLI and schema version window and returns typed errors.
- `REQ-1011`: The web interface and CLI invoke one application use case and one API; a separate web route is permitted only for a documented security reason.
- `REQ-1012`: Passport creation and modification, project indexing, selection, compilation, validation, and installation have no separate implementation in the web interface.
- `REQ-1013`: The device page shows only the permitted summary from the closed list in `docs/contracts/device-passport.md`; the full device passport is not exposed through the API or web interface.
- `REQ-1014`: A report from the web interface or CLI creates one private `ReportCase` through the shared application use case defined by `SPEC-016`; reports do not automatically create public GitHub issues.
- `REQ-1015`: Single-node HTTP rate limiting consists of two independent sliding windows before the route handler: a process-wide budget (100 requests per 60 seconds by default) and a client-address budget (1,000 requests per 3,600 seconds by default), keyed on the address the edge proxy states in `X-AI-STP-Client-IP` when that parses as an IP and on the transport peer otherwise; the operator configures both through env, absent variables retain these values rather than making them unlimited, and an explicit `0` disables only that dimension; exhaustion of either window responds with `AI_STP_RATE_LIMITED` and does not consume the other; a key with an empty window is evicted, and new keys are not collapsed into a shared overflow bucket; Redis, SlowAPI, a separate proxy, and the edge proxy's own rate limiting are out of scope (`ADR-0128`).

## States and errors

The API distinguishes validation, authentication, authorization, concurrency, rate-limit, unavailable-dependency, and internal-failure errors. A job has the states `queued`, `running`, `retry_scheduled`, `dead_letter`, and `succeeded`. Readiness does not become successful until migrations have been applied and required dependencies are available.

## Security and privacy

PostgreSQL and RustFS are not exposed to the internet. Sign-in and session tokens are stored as secrets and are not returned to the agent. User isolation, rate limits, audit sanitization, and authorization for private objects are verified by negative tests. Administrator access is always recorded in the audit trail.

## Compatibility and migration

Database changes use an expand, migrate, switch, and contract sequence. API fields are initially added as optional. Compatibility of an old client with a new server and a new client with an old supported server is verified by contract tests. A rollback must be able to read data written by the new version within the compatibility window.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-1001` | A clean integration environment starts the API, database, job processor, and object storage. |
| `REQ-1002` | Authentication tests cover sign-in, linking, conflict, revocation, sign-out, exact redirect construction, and a configured same-origin compatibility callback path. |
| `REQ-1003` | The authorization matrix covers the owner, a permission recipient, an unrelated user, and an administrator. |
| `REQ-1004` | A direct object address without an authorized API request is rejected. |
| `REQ-1005` | A repeated request and stale ETag do not create duplicate effects. |
| `REQ-1006` | Failure and retry tests confirm the outbox and handler idempotency. |
| `REQ-1007` | An audit test records the actor, reason, target, and result without secrets. |
| `REQ-1008` | Route inventory covers every declared area and contains no functionality outside the web-interface scope. |
| `REQ-1009` | Mail adapter tests verify the template, sanitization, and retry classification. |
| `REQ-1010` | OpenAPI and mixed-version tests verify the compatibility window. |
| `REQ-1011` | A contract test proves that the web interface and CLI invoke one use case and one route for each shared operation. |
| `REQ-1012` | A negative test rejects passport writes and compilation through a handler unavailable to the CLI. |
| `REQ-1013` | The golden device response contains only fields from the permitted summary, and a request for the full device passport is rejected. |
| `REQ-1014` | A contract test proves there is one reporting use case for the web interface and CLI and no integration with public issues. |
| `REQ-1015` | A clock is injected into the shipped limiter: the 101st request in the shared 60-second window is rejected and the 100th passes; the 1,001st request from one address in 3,600 seconds is rejected while another address passes under the hourly window; many addresses together exhaust the shared budget; rejection by one window does not change the other's counter; settings without env are bounded at 100/minute and 1,000/hour; an explicit `0` disables a dimension. A key with an empty window releases its slot, and there is no shared overflow bucket. With a low limit, the ASGI factory responds with `429` / `AI_STP_RATE_LIMITED` / `Retry-After`. |
