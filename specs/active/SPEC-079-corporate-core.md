---
description: "SPEC-079: Corporate bootstrap, scoped RBAC, tenant isolation, and audit journal."
last_verified: "2026-09-12"
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
invitations, SAML, private telemetry, and dashboards remain owned by later
milestones.

## B2B-01 boundary and issue alignment

B2B-01 covers the corporate surfaces introduced by this implementation: bootstrap,
the seeded role catalog plus custom role-definition CRUD and permission bindings,
member/team/project and assignment lifecycle, tenant-owned service principals,
effective context and capabilities, the corporate audit journal, and the generic
queue/object tenant conventions used by those surfaces.

Search indexes (#212), application caches and non-audit product exports (#247),
private/runtime telemetry (#52, #218, #219), GitLab integration (#18, #213), and
feature-specific technology/background handlers (#207, #208, #222, #215, #230)
are not introduced by B2B-01. Their tenant-isolation, denied/replay audit,
filtering, redaction, storage, and export acceptance criteria belong to those
owning follow-up issues and must be written there before the features are treated
as milestone-complete. The acceptance criteria for issues #200, #202, and #203
must use this boundary or explicitly include those follow-up scopes before closure
of those issues is considered.

The issue boundary is explicit: #200 retains corporate administration over the
implemented role, member, team, project, assignment, binding, and service-principal
surfaces plus verified identity linking during first login; IdP administration,
invitations, and directory synchronisation are follow-up scope. #202 retains the
introduced corporate journal, bounded filters, safe redaction, audit-of-audit reads,
and bounded portable export; product-wide audit coverage, retention, and deletion are
follow-up scope. #203 retains tenant isolation for the introduced API, database
relationships, generic queue/object paths, and service principals; search (#212),
cache and non-audit product-export (#247), telemetry (#52, #218, #219), GitLab
(#18, #213), and feature-specific background paths (#207, #208, #222, #215, #230)
are follow-up scope.

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
  decision distinguishes create, read, update, delete, and list. Binding lifecycle
  operations are independently exposed and tenant-compatible account relationships
  are enforced by database constraints.
- `REQ-7903`: One server evaluator authorizes every introduced corporate API route,
  application service, collection filter, generic background job, and capability
  projection from current membership, binding, resource scope, and organization
  policy revision.
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
  Cross-tenant relationships, identifiers, reads, writes, lists, counts, introduced
  jobs, audit reads, and object keys are rejected or partitioned before protected
  data is returned. Search, application-cache, product-export, telemetry,
  GitLab-integration, and feature-specific background boundaries are follow-up
  acceptance criteria and are not claimed by B2B-01 until their owning issue ships.
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
- `REQ-7911`: Every introduced privileged read, mutation, delete, and security-relevant
  denial appends an organization-scoped audit event containing actor, action, target,
  outcome, reason code, request correlation identifier, and time. The bounded audit
  export uses the same authorization, filtering, and redaction rules.
- `REQ-7912`: Audit events are append-only, ordered by `(created_at, id)`, bounded when
  listed, separately permissioned, and themselves audited. Stored and returned audit
  data contains no credential, token, assertion, secret, repository content, raw
  private telemetry, or foreign-tenant identifier. Follow-up feature issues
  (#212, #247, #52, #218, #219, #18, #213, #207, #208, #222, #215, #230)
  must add equivalent guarantees before claiming those surfaces.
- `REQ-7913`: The corporate capability projection exposes only implemented effective
  capabilities and current authorization revision. Web navigation and actions follow
  this projection while every API request remains independently authorized.
  Applicable active bindings contribute the union of their inherited permissions;
  binding order and the membership's role label do not override effective grants.
  The shared organization projection uses organization-scoped decisions: a resource
  binding does not grant organization administration. Suspended principals, revoked
  bindings, and stale revisions remain denied.
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
bounded, filterable journal read and a bounded portable export; both use the stable
`(created_at, id)` cursor (`before_created_at` plus `before_id`) and there is no deletion
endpoint. Operational database backup and restore remains the recovery path until a
versioned retention policy under SPEC-013 defines deletion behavior.
Journal ordering, cursor comparisons, and time filters use canonical UTC millisecond
precision, matching the public timestamp representation, including existing rows
stored with PostgreSQL microsecond precision.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-7901` | Concurrent and replayed bootstrap tests create one organization and one active superadmin; a different request fails closed. |
| `REQ-7902` | Migration and evaluator tests cover every initial role, permission, CRUDL action, scope, and deny-by-default result. |
| `REQ-7903` | One authorization matrix exercises routes, direct services, collection filters, delayed jobs, and projections with the same fixtures. |
| `REQ-7904` | API tests execute the role, member, binding, team, project, assignment, and service-principal lifecycle as a superadmin. |
| `REQ-7905` | Lead and staff tests prove scoped allowance and organization-wide denial. |
| `REQ-7906` | Concurrency, stale-revision, idempotency, and last-superadmin tests observe no partial mutation. |
| `REQ-7907` | A provisioned account's first context response contains only its organization, scopes, and visible projects; identity linking preserves them. |
| `REQ-7908` | Database constraints, a non-privileged FORCE-RLS probe, and hostile integration tests cover cross-tenant read, write, relationship, list, count, introduced-job, audit-read, and object-key boundaries. #212, #247, #52, #218, #219, #18, #213, #207, #208, #222, #215, and #230 add equivalent hostile tests for their follow-up surfaces before claiming them. |
| `REQ-7909` | Unknown and foreign identifiers return the same public envelope without protected fields or counts. |
| `REQ-7910` | Every authorization mutation changes the revision and rejects the previous revision before effects. |
| `REQ-7911` | Success, denial, and bounded export tests assert transactional audit rows with the required safe fields and no secrets. |
| `REQ-7912` | Append-only, pagination, access-control, self-audit, and forbidden-field tests pass. |
| `REQ-7913` | API and Web tests expose only effective implemented capabilities and reject forged or stale mutations. |
| `REQ-7914` | OpenAPI drift, generated-client, contract-lint, and stable-error tests pass. |
