---
description: "SPEC-076: Versioned context capability projection for FastAPI and Next.js."
last_verified: "2026-09-09"
---

# SPEC-076: Context capability projection

## Purpose

Give API and Next.js one compact, versioned description of what the current
actor may attempt in the server-resolved context while keeping every
authorization decision server-side.

## Scope

This specification owns issue #227. It defines the capability identifier
grammar, projection fields, local and remote projection endpoints, cache
invalidation, and stale-request behavior.

It does not define the corporate role hierarchy or policy engine; issue #200
owns those decisions. It does not make UI visibility an authorization boundary
or serialize the complete RBAC graph into the browser.

## Terms

- **Context capability** — a closed `resource.action` identifier describing an
  action available in one resolved context.
- **Capability projection** — a bounded response containing context metadata and
  the effective context capabilities.
- **Authorization revision** — a monotonic opaque value changed whenever facts
  that can alter the projection change.
- **CRUDL** — separate `create`, `read`, `update`, `delete`, and `list` actions;
  `list` never follows automatically from `read`.

## Requirements

- `REQ-7601`: `ContextCapabilityProjection` is a versioned response containing
  `schema_version`, `mode`, `context_kind`, optional `organization_id`, opaque
  `authorization_revision`, `generated_at`, and a sorted duplicate-free list of
  capability identifiers.
- `REQ-7602`: A capability identifier follows the closed
  `<resource>.<action>` grammar. The initial action vocabulary is `create`,
  `read`, `update`, `delete`, `list`, `link`, `unlink`, `publish`, `assign`,
  `revoke`, `manage`, and `operate`; an unknown resource or action is rejected.
- `REQ-7603`: The initial resource families are `project`, `technology`,
  `landscape`, `catalog_object`, `organization`, `member`, `team`, `assignment`,
  `audit`, `telemetry`, `invitation`, `saml`, and `deployment`. A family becomes
  effective only when its owning specification and server implementation exist.
- `REQ-7604`: Remote clients read the projection from
  `GET /v1/organizations/{organization_id}/capabilities`; the server derives the
  mode and capabilities from the authenticated account, organization kind,
  active membership, policy, and resource constraints.
- `REQ-7605`: Local clients read the same response family from the explicit
  loopback local API context without authentication or a remote organization.
  The local projection contains no corporate capability family.
- `REQ-7606`: Every protected API route and application scenario performs its
  own current authorization and resource-scope check. Possession of a projection
  or capability string grants no authority.
- `REQ-7607`: Collection `list` and object `read` are independent capabilities.
  A caller permitted to read one known object does not gain discovery of the
  collection, counts, search results, or foreign identifiers.
- `REQ-7608`: A mutating request carries the projection's
  `authorization_revision` as a precondition. If authorization-relevant state
  changed, the server returns `capability_stale` before side effects and the
  client fetches a fresh projection.
- `REQ-7609`: Permission, membership, organization status, or policy changes
  advance the affected authorization revision and invalidate server and Web
  caches. Responses use `Cache-Control: private, no-store` unless a later
  contract proves a safe revision-keyed cache.
- `REQ-7610`: The projection is bounded to 256 capability identifiers and 16 KiB
  canonical JSON. Exceeding either bound is a server contract failure; it is not
  truncated into a weaker or ambiguous projection.
- `REQ-7611`: The projection contains no role graph, policy expression, email,
  provider token, hidden resource identifier, cross-organization count, or
  resource payload.
- `REQ-7612`: Next.js may use the projection for server-provided navigation,
  page/action visibility, and request preconditions. It never lets a browser
  selector, stale cookie, or client header choose the product mode or
  organization. An absent capability renders forbidden or unavailable according
  to the response reason and never sends a speculative mutating request.
- `REQ-7613`: Deployment build profiles do not add, remove, or override context
  capabilities. Unknown feature-profile keys and unknown capability identifiers
  both fail closed in their separate registries.
- `REQ-7614`: Background jobs and service principals evaluate the same resource
  and organization permissions at execution time; they do not reuse the
  initiating browser's capability projection as authority.

## States and errors

Projection reads return `ready`, `unauthenticated`, `context_not_found`,
`context_forbidden`, or `unavailable`. Mutations may additionally return
`capability_stale` or `capability_forbidden`. Unknown identifiers and oversized
projections are `contract_invalid` and fail closed.

## Required authorization matrix

The API acceptance suite keeps this matrix explicit for every protected route,
rather than treating a successful projection read as route authorization:

| Actor/context fact | Projection read | Known-object read | Collection/list/search/count | Mutation with a forged projection |
|---|---|---|---|---|
| Personal owner | allowed | capability-specific | `list` is independent of `read` | server rechecks and rejects absent/stale capability |
| Corporate owner/admin | allowed | capability-specific | `list` is independent of `read` | server rechecks role, membership, resource and revision |
| Corporate active member | allowed | only member capabilities | only independently granted CRUDL actions | admin-only or forged actions are rejected |
| Outsider | denied, non-enumerating | denied | denied, including counts/search | denied without revealing foreign identifiers |
| Suspended member | denied after revision change | denied | denied | denied before side effects |
| Foreign organization in an otherwise valid session | denied | denied | denied | denied without using the caller's other-tenant projection |

The matrix is exercised against each protected route, including direct URL
entry, and includes forged projection strings, stale authorization revisions,
and delayed job execution. Boundary fixtures accept 256 identifiers and a
canonical payload at or below 16 KiB, while rejecting the first item over
either limit without truncation. Membership, role, organization status, policy,
device/session, and resource-scope changes each advance or invalidate the
affected authorization revision.

## Security and privacy

The projection is least-information guidance. Authorization happens before
projection construction and again before each protected operation. Organization
scope is explicit, cross-tenant identifiers are non-enumerating, and audit/log
records contain only the actor, safe context ID, revision, requested capability,
and outcome. Local loopback responses never expose local paths or private bytes.

## Compatibility and migration

Publish the response schema and generated Web client before serving projections.
Existing clients ignore the additive discovery link and continue current routes.
Capability additions require a registry version and owner specification;
renaming or changing semantics requires a new response schema version. Rollback
disables projection-driven corporate UI while API authorization remains active.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-7601` | Contract fixtures verify every field, canonical order, duplicate rejection, and all three modes. |
| `REQ-7602` | Registry tests accept the closed action grammar and reject unknown, malformed, or case-varied identifiers. |
| `REQ-7603` | Every resource family points to an owning specification and remains absent until its implementation is enabled. |
| `REQ-7604` | `tests/api/platform/test_context_capability_matrix.py` derives different projections for owner, member, outsider, suspended member, and foreign organization. |
| `REQ-7605` | Network-disabled loopback tests return the same schema without an account and without corporate capabilities. |
| `REQ-7606` | `tests/api/platform/test_context_capability_matrix.py` calls every protected route with a forged projection and observes server authorization failure. |
| `REQ-7607` | The same matrix keeps known-object `read` separate from collection `list`, search, and count. |
| `REQ-7608` | A permission change between projection read and mutation returns `capability_stale` with no side effect. |
| `REQ-7609` | Matrix fixtures advance revision for membership, role, organization status, policy, device/session, and resource-scope changes. |
| `REQ-7610` | Boundary fixtures pass at 256 identifiers/16 KiB and fail without truncation above either limit. |
| `REQ-7611` | Schema and privacy scans reject policy graphs, PII, tokens, hidden IDs, and payload fields. |
| `REQ-7612` | Web shell tests prove there is no context selector or client-selected scope; API tests prove capability denial and request preconditions remain server-side. |
| `REQ-7613` | The web-profile matrix proves build configuration cannot change the capability response or API verdict. |
| `REQ-7614` | Delayed-job tests revoke permission after enqueue and observe denial at execution without cross-tenant effects. |
