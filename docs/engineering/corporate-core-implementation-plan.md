---
description: "Implementation and verification sequence for B2B-01 Corporate core."
last_verified: "2026-09-12"
---

# Corporate core implementation plan

## Objective

Deliver and verify the B2B-01 corporate-core slice for issues #200, #203, and #202;
record any feature-owned follow-up scope before closure. SPEC-079 and ADR-0179 are
normative.

The slice owns corporate bootstrap, role definitions and binding CRUDL,
member/team/project and assignment lifecycle, service principals, context and
capabilities, audit, and the generic queue/object tenant conventions it introduces.
Search indexes (#212), application caches and non-audit product exports (#247),
private/runtime telemetry (#52, #218, #219), GitLab integration (#18, #213), and
feature-specific technology/background handlers (#207, #208, #222, #215, #230)
remain follow-up issue scope until they have their own implementation and hostile
cross-tenant acceptance tests. IdP administration and invitations remain follow-up
under #19, #220, and #201; verified identity linking during first login is part of
this slice.

## P0 — contract and persistence

1. Add corporate organization state and policy revision, corporate projects, roles,
   permissions, user/service-principal scoped bindings, bootstrap receipts, and audit
   outcome/correlation. Binding and resource lifecycle routes expose separate CRUDL
   decisions; account relationships use tenant-compatible composite foreign keys.
2. Add an idempotent migration with tenant-compatible uniqueness and relationship
   constraints, plus the initial closed permission seed.
3. Add strict requests and open responses for bootstrap, member/binding/project
   lifecycle, effective context, and audit listing.

Exit: migration, schema, and wire-contract tests pass.

## P1 — authorization and tenant boundary

1. Implement one deny-by-default evaluator over current persisted facts for every
   corporate surface introduced by this slice.
2. Route capability projection and every new application scenario through it.
3. Enforce stale authorization revisions, last-superadmin protection, immutable
   tenant ownership, PostgreSQL FORCE RLS, non-enumeration, and tenant-safe list
   filtering.
4. Partition queue idempotency and private object keys by organization; revalidate a
   queued principal, permission, scope, and authorization revision immediately before
   handler execution.

Exit: the role/scope/CRUDL and cross-tenant hostile matrices pass.

## P2 — API scenarios and audit

1. Implement bootstrap and member, binding, membership assignment/removal, project,
   team, and service-principal lifecycle routes.
2. Append redacted success and security-denial audit events transactionally.
3. Implement bounded tenant-scoped audit reads and audit those reads.

Exit: #200, #203, and #202 API acceptance tests pass with PostgreSQL.

## P3 — shared Web and generated surfaces

1. Regenerate OpenAPI, schemas, and the TypeScript client from their owners.
2. Enable only implemented corporate capabilities.
3. Add shared-shell corporate overview and projection-driven create/update/archive/delete
   administration surfaces, with forbidden, stale, empty, and unavailable states.

Exit: generated drift, Web unit/component/type/build, accessibility, and locale checks
pass.

## P4 — closeout

Run `just docs-check`, `just back-static`, `just back-test`, `just web-check`, inspect
`just --show check`, run the complete applicable gate, run repository safety scans,
and review the final diff for unrelated changes. Do not close the three issues or
milestone until their acceptance criteria either match this boundary or the listed
follow-up scopes have shipped with exact-SHA green evidence and independent review.
