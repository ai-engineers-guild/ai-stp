---
description: "Corporate authorization uses persisted tenant-scoped role bindings, one server evaluator, and transactional audit."
last_verified: "2026-09-12"
---

# ADR-0179: Corporate authorization is a tenant-scoped policy table

Status: accepted.

## Context

B2B-01 must bootstrap a corporate organization, enforce dynamic CRUDL permissions,
isolate every tenant-owned row, and audit privileged or denied operations. B2B-00
already established `Organization` as the only remote ownership aggregate and a
server-owned capability projection. A second policy service or a client-side role
matrix would duplicate those authority boundaries.

## Options

1. Hard-code role checks in each route. This is small initially but cannot express
   scoped bindings or keep collection filtering consistent with object checks.
2. Add an external policy engine and its own policy language. This adds a runtime
   dependency and another migration surface before the closed initial matrix needs it.
3. Persist roles, permissions, and scoped bindings in PostgreSQL and evaluate them
   through one application function used by routes, services, jobs, and capability
   projection.

## Decision

Option 3 is selected.

Corporate roles are `superadmin`, `lead`, and `staff`. Permissions are closed
`resource.action` identifiers whose actions include distinct CRUDL operations.
Roles inherit permissions through persisted rows; bindings grant one role to one
user or tenant-owned service principal at system, organization, team, project,
technology, catalog-object, or telemetry scope. Exactly one principal kind is present
on each binding, and a binding is valid only inside its owning organization.

Every protected scenario calls the same evaluator with actor, organization,
permission, scope kind, and optional scope identifier. Collection queries apply the
same decision before returning identifiers, counts, or search results. The Web uses
the resulting capability projection only for rendering; it never authorizes a
request.

Corporate resources store a non-null `organization_id`. Relationships between
corporate rows use tenant-compatible composite keys or an equivalent database constraint, and
application services reject a foreign identifier before loading protected fields.
Queues, object keys, caches, exports, and search projections include the tenant
boundary when they are introduced by their owning feature.

Authorization-relevant mutations increment the organization policy revision. A
mutation carrying an older revision fails before effects. The last active
`superadmin` cannot be suspended, demoted, or removed.

Privileged reads, mutations, exports, deletes, and security-relevant denials append a
redacted `AuditEvent` in the same database transaction as the decision or mutation.
Audit events are tenant-scoped and append-only; their payload allowlist excludes
credentials, tokens, assertions, repository content, and private telemetry.

Team leads are active team-scoped `lead` bindings, independent of the organization
membership role. Archived teams retain historical relationships but contribute no
effective grants. A team without an active lead remains under its superadmin's
administration; no automatic promotion or broader lead authority is introduced.

## Consequences

- `SPEC-079` owns the B2B-01 behavior and executable authorization matrix.
- Existing personal organizations retain their single-owner rules and cannot receive
  corporate roles or resources.
- Adding a permission requires a contract change and seed migration; arbitrary policy
  expressions are not accepted from clients.
- A later policy engine may replace the evaluator behind the same decision contract
  if the persisted closed matrix becomes insufficient.

## Revisit conditions

Revisit this decision when conditional policies require facts that cannot be
represented by tenant and resource scopes, or when measured policy volume requires a
dedicated decision service.
