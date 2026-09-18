---
description: "Delivery order, gates, migration, and rollback for SPEC-086."
last_verified: "2026-09-18"
---

# Corporate workspace consolidation plan

## Objective

Deliver SPEC-086 and the clarifications to SPEC-079, SPEC-081, SPEC-083, SPEC-084,
and SPEC-085 without introducing a second identity, authorization evaluator, catalog,
directory projection, Markdown renderer, media gallery, or selection control.

## Delivery rules

- Each change request is a vertical contract, persistence, API, Web, documentation,
  and test slice where those layers are affected.
- Additive contracts and migrations land before their consumers.
- Existing capabilities and object-specific available actions control the Web; API
  authorization remains authoritative.
- Local work runs targeted static, unit, contract, and migration checks. Full backend
  regression, PostgreSQL matrices, production Web build, browser matrices, and complete
  gates run on GitHub Actions for the exact commit.
- A later change request cannot compensate for a failed earlier exit gate.

## Twelve-step delivery order

### 1. Runtime stability

Remove server/client render divergence around session-aware controls and Radix menus.
Add a production-build smoke profile and browser-console failure assertions.

Exit: catalog, four directories, and representative detail routes return 200 with no
hydration, recoverable render, or uncaught browser error.

### 2. Normative contracts

Land SPEC-086, ADR-0192, ADR-0193, clarifications to incumbent corporate records, and
the change-request ledger. Regenerate documentation indexes.

Exit: documentation, specification, contract, and link checks pass.

### 3. Persistence and generated contracts

Add migration `0077_corporate_job_titles` with job titles and the nullable membership
reference. Add technology-category catalog
facets, bounded card projections, transactional create commands, and organization-usage
contracts. Regenerate schemas, OpenAPI, and the TypeScript client from their owners.

Exit: upgrade/downgrade migration tests and generated-source drift checks pass.

### 4. API projections and authorization

Implement authorization-before-enrichment directory cards, pagination, facets,
organization usage, title administration, and transactional create commands through
the incumbent evaluator, revision, receipt, and audit paths.

Exit: PostgreSQL tenant, hostile-identifier, role-matrix, replay, and no-partial-write
integration tests pass.

### 5. Canonical employee identity and routes

Build the shared account detail projection, introduce `/corporate/employees`, redirect
legacy member routes, and keep public publisher output private-data free.

Exit: route, canonical-link, account identity, redirect, and privacy tests pass.

### 6. Canonical corporate catalog

Extend the incumbent catalog query and filter modal, redirect corporate component
routes, and remove duplicate navigation and machine-route entries.

Exit: setup/component facet parity, URL round trip, public compatibility, pagination,
and redirect tests pass.

### 7. Bounded directories

Adopt one-page URL-backed directories and one card projection for teams, projects,
employees, and technologies. Add job-title filtering and correct owner/category labels.

Exit: root and nested card parity, counts, pagination, sort, filters, and mobile list
tests pass.

### 8. Creation and action policy

Add dedicated create routes using incumbent edit composition and searchable selectors.
Adopt one capability-driven action menu in cards and detail headers.

Exit: administrator, lead, owner, self, staff, stale-revision, replay, and partial-failure
tests pass for all create and action paths.

### 9. Detail content consolidation

Move relation filters inside expanded content, render assignments with canonical object
cards and stable links, add Use via CLI, fix owner/lead rail content, and add Organization
usage to setup/component details.

Exit: relation, action, stable-link, exact-version, usage, and empty-state tests pass.

### 10. Presentation polish

Hide normal lifecycle labels, remove Overview organization descriptions, style Markdown
tables, widen the desktop rail, and refine the incumbent gallery into a bounded carousel.

Exit: keyboard, reduced-motion, dark/light, 1440 px, 430 px, and 360 px visual and
accessibility checks pass without document-level overflow.

### 11. GitHub regression gate

Run the complete backend regression, migration matrix, integration API tests, generated
drift, production Web build, unit/component suites, feature profiles, E2E, browser-console
assertions, and repository security gates on GitHub Actions for the exact commit.

Exit: every required job is green on one exact SHA; skipped heavy jobs are not evidence.

### 12. Rollout and observation

Deploy additive migrations, API, then Web. Verify redirects, representative role flows,
tenant isolation, HTTP status, browser console, API error rate, and worker health. Roll
back the application without dropping additive data if acceptance fails.

Exit: post-deploy smoke is green and no new hydration, SSR 500, authorization denial
spike, cross-tenant anomaly, or migration error is present.

## Migration and rollback

1. Migration `0077_corporate_job_titles` adds job-title storage, indexes, and the
   nullable membership reference.
2. Deploy readers that tolerate absent titles and absent new projection fields.
3. Deploy writers and administration after contracts are live.
4. Deploy redirects and consolidated Web surfaces after API acceptance.
5. Preserve new rows, receipts, and audit during application rollback.
6. Perform schema downgrade only as a separate verified operation.

## Completion evidence

The implementation is complete only when every change request in the companion ledger
is complete, SPEC-086 acceptance criteria have executable owners, generated artifacts
are current, the final diff contains no unrelated work, and GitHub Actions provides one
exact-SHA green gate followed by a successful post-deploy smoke.
