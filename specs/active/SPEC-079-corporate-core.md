---
description: "SPEC-079: Corporate bootstrap, scoped RBAC, tenant isolation, and audit journal."
last_verified: "2026-09-11"
---

# SPEC-079: Corporate core

## Purpose

Make one self-hosted installation capable of creating its first corporate tenant and
administering users and projects without permitting cross-tenant access or unaudited
privilege changes.

## Scope

This specification owns milestone B2B-01 and issues #200, #203, and #202. It defines
corporate bootstrap, the initial scoped RBAC model, corporate teams and projects, tenant
isolation, capability invalidation, and the corporate audit journal. Team hierarchy,
invitations, SAML, assignments, telemetry, and dashboards remain owned by later
milestones.

## Terms

- `superadmin` — organization-wide administrator and the only initial bootstrap role.
- `lead` — administrator within explicitly bound team or project scopes.
- `staff` — member with explicitly granted read or work permissions.
- `scope` — one of `system`, `organization`, `team`, `project`, `technology`,
  `catalog_object`, or `telemetry`, optionally naming one resource.
- `authorization revision` — the monotonic organization policy revision used as a
  mutation precondition.

## Requirements

- `REQ-7901`: An installation with no corporate organization accepts one idempotent
  bootstrap request authenticated by the configured bootstrap secret, creates one
  corporate organization and one active `superadmin`, and permanently rejects a
  second distinct bootstrap result.
- `REQ-7902`: Roles, permissions, role-permission relations, and account role bindings
  are persisted. The initial hierarchy is `superadmin`, `lead`, and `staff`; every
  decision distinguishes create, read, update, delete, and list.
- `REQ-7903`: One server evaluator authorizes API routes, application services,
  collection filters, background jobs, and capability projections from current
  membership, binding, resource scope, and organization policy revision.
- `REQ-7904`: A superadmin can create, list, read, update, suspend, and reactivate
  corporate members; change their role bindings; create teams and projects; assign
  members to either; change or remove those memberships; appoint a team lead; and
  archive or restore projects.
- `REQ-7905`: A lead can act only inside explicitly bound team or project scopes. Staff
  cannot mutate organization structure, another member, or another member's access.
- `REQ-7905a`: A superadmin can create and suspend tenant-owned service principals.
  User and service-principal bindings are mutually exclusive and both use the same
  evaluator, permission rows, scopes, policy revision, and audit actor model.
- `REQ-7906`: The last active superadmin cannot be suspended, removed, or demoted, and
  every membership or binding mutation is idempotent and revision-checked. A replay
  with the original idempotency key returns its stored result even after the policy
  revision advances; reusing that key for another request is rejected.
- `REQ-7907`: A provisioned account sees its organization, effective scopes, and
  assigned teams and projects on its first authenticated context read; later identity-provider linking
  preserves the account and bindings rather than creating another member.
- `REQ-7908`: Every corporate row has one immutable non-null `organization_id`.
  Cross-tenant relationships, identifiers, reads, writes, lists, searches, counts,
  jobs, exports, cache entries, object keys, and event ingestion are rejected or
  partitioned before protected data is returned.
  PostgreSQL FORCE RLS uses the transaction-local `ai_stp.organization_id`; trusted
  bootstrap, identity-broker, and queue-claim scans use `*` only until work is bound to
  one tenant. Tenant jobs persist the same identifier plus principal, permission, and
  scope in the payload, revalidate the complete authorization decision immediately
  before execution, and use
  tenant-partitioned idempotency. Private object keys and metadata contain the stable
  organization identifier and cross-tenant reads fail closed.
- `REQ-7909`: Missing, foreign, suspended, and unauthorized organization contexts are
  non-enumerating. An otherwise valid session in another tenant grants no access.
- `REQ-7910`: Authorization-relevant changes atomically increment the organization
  policy revision. A mutation with a stale revision returns `capability_stale` without
  side effects; clients then refresh the capability projection.
- `REQ-7911`: Privileged reads, mutations, exports, deletes, and security-relevant
  denials append an organization-scoped audit event containing actor, action, target,
  outcome, reason code, request correlation identifier, and time.
- `REQ-7912`: Audit events are append-only, ordered by `(created_at, id)`, bounded when
  listed, separately permissioned, and themselves audited. Stored and returned audit
  data contains no credential, token, assertion, secret, repository content, raw
  private telemetry, or foreign-tenant identifier.
- `REQ-7913`: The corporate capability projection exposes only implemented effective
  capabilities and current authorization revision. Web navigation and actions follow
  this projection while every API request remains independently authorized.
- `REQ-7914`: Bootstrap, authorization, tenant ownership, and audit behavior is
  available through the generated `/v1` contract and uses stable error categories and
  idempotency keys.

## States and errors

Organizations are `active` or `suspended`; memberships are `active` or `suspended`;
projects are `active` or `archived`; bindings are `active` or `revoked`. Public errors
are `bootstrap_closed`, `organization_access_denied`, `capability_forbidden`,
`capability_stale`, `last_superadmin`, `revision_conflict`, and `contract_invalid`.
Foreign and unknown protected identifiers share the same non-enumerating response.

## Security and privacy

The bootstrap secret is supplied only through server configuration and a request
header, compared without logging, and never persisted. Authorization defaults to
deny. Tenant scope is checked before resource hydration. Audit payloads pass the
shared recursive redactor and a corporate allowlist. Product superadmins have no
implicit infrastructure-operator authority.

## Compatibility and migration

Add corporate tables and constraints before enabling corporate mutations. Seed the
closed permission matrix idempotently. Existing personal organizations, account
routes, and local operation retain their behavior. Rollback disables corporate routes
but retains tenant and audit rows; it never converts corporate data into personal
ownership.

## Retention and export

Corporate audit events are retained indefinitely in B2B-01. The product exposes a
bounded, filterable journal read but no audit export or deletion endpoint. Operational
database backup and restore is the only export path until a versioned retention policy
under SPEC-013 defines deletion and portable export behavior.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-7901` | Concurrent and replayed bootstrap tests create one organization and one active superadmin; a different request fails closed. |
| `REQ-7902` | Migration and evaluator tests cover every initial role, permission, CRUDL action, scope, and deny-by-default result. |
| `REQ-7903` | One authorization matrix exercises routes, direct services, collection filters, delayed jobs, and projections with the same fixtures. |
| `REQ-7904` | API tests execute the member, binding, and project lifecycle as a superadmin. |
| `REQ-7905` | Lead and staff tests prove scoped allowance and organization-wide denial. |
| `REQ-7906` | Concurrency, stale-revision, idempotency, and last-superadmin tests observe no partial mutation. |
| `REQ-7907` | A provisioned account's first context response contains only its organization, scopes, and visible projects; identity linking preserves them. |
| `REQ-7908` | Database constraints, a non-privileged FORCE-RLS probe, and hostile integration tests cover cross-tenant read, write, relationship, list, count, search, job, export, cache, object-key, and event boundaries. |
| `REQ-7909` | Unknown and foreign identifiers return the same public envelope without protected fields or counts. |
| `REQ-7910` | Every authorization mutation changes the revision and rejects the previous revision before effects. |
| `REQ-7911` | Success and denial tests assert transactional audit rows with the required safe fields. |
| `REQ-7912` | Append-only, pagination, access-control, self-audit, and forbidden-field tests pass. |
| `REQ-7913` | API and Web tests expose only effective implemented capabilities and reject forged or stale mutations. |
| `REQ-7914` | OpenAPI drift, generated-client, contract-lint, and stable-error tests pass. |
