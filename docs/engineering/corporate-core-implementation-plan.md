---
description: "Implementation and verification sequence for B2B-01 Corporate core."
last_verified: "2026-09-11"
---

# Corporate core implementation plan

## Objective

Complete milestone B2B-01 and issues #200, #203, and #202 on branch
`codex/b2b-01-corporate-core`. SPEC-079 and ADR-0179 are normative.

## P0 — contract and persistence

1. Add corporate organization state and policy revision, corporate projects, roles,
   permissions, user/service-principal scoped bindings, bootstrap receipts, and audit
   outcome/correlation.
2. Add an idempotent migration with tenant-compatible uniqueness and relationship
   constraints, plus the initial closed permission seed.
3. Add strict requests and open responses for bootstrap, member/binding/project
   lifecycle, effective context, and audit listing.

Exit: migration, schema, and wire-contract tests pass.

## P1 — authorization and tenant boundary

1. Implement one deny-by-default evaluator over current persisted facts.
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
   and service-principal lifecycle routes.
2. Append redacted success and security-denial audit events transactionally.
3. Implement bounded tenant-scoped audit reads and audit those reads.

Exit: #200, #203, and #202 API acceptance tests pass with PostgreSQL.

## P3 — shared Web and generated surfaces

1. Regenerate OpenAPI, schemas, and the TypeScript client from their owners.
2. Enable only implemented corporate capabilities.
3. Add the minimal shared-shell corporate overview and administration surfaces driven
   by the server projection, with forbidden, stale, empty, and unavailable states.

Exit: generated drift, Web unit/component/type/build, accessibility, and locale checks
pass.

## P4 — closeout

Run `just docs-check`, `just back-static`, `just back-test`, `just web-check`, inspect
`just --show check`, run the complete applicable gate, run repository safety scans,
and review the final diff for unrelated changes. Close the three issues and milestone
only after the exact delivered SHA has green evidence.
