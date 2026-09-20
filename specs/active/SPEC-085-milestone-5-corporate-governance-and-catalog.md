---
description: "SPEC-085: Corporate governance lifecycle, team profile, and catalog context."
last_verified: "2026-09-19"
---

# SPEC-085: Milestone 5 corporate governance and catalog context

## Purpose

Complete the enterprise-MVP extension of the existing Corporate Hub for issues
210, 211, and 212, and extend the same assignment workflow for milestone 6
issues 205 and 206 without introducing a second authorization, publication,
assignment, distribution, or catalog search workflow.

## Normative boundary

The existing `authorize()` evaluator, role bindings, canonical relations,
publication pipeline, catalog object identities, and Corporate Hub entity detail
routes remain the single sources of truth. The additions below are tenant-scoped
relations and projections. They never grant catalog access, installation rights,
global verification, or provider authority.

## Scope

This specification covers tenant-scoped governance relations for published
components and setups, the existing Corporate Hub team detail projection,
corporate context on the existing component/setup catalog searches, the
deterministic effective-assignment policy used by the CLI and Web, and bulk
distribution of component/setup assignments across corporate scopes. It does not
replace publication, global author verification, catalog access grants, setup
installation, or provider-owned harness state.

SPEC-086 and ADR-0193 make `/corporate/catalog` the sole corporate Web surface for
these searches, add technology-category context, and expose authorized organization
usage on stable object details. The governance facts and search semantics remain owned
by this specification.

## Terms

- `Corporate governance relation` — an organization-scoped ownership,
  maintainership, corporate-verification, lifecycle, or exact-version
  assignment row.
- `Effective assignment` — the winning applicable assignment for an employee,
  resolved from direct user, project, technology, team, and organization scopes
  plus an optional harness condition. A team-derived row remains a projection
  of its source assignment.
- `Assignment selector` — either an exact immutable catalog coordinate (version
  and, when available, digest) or the `latest` selector, which is resolved to an
  exact eligible coordinate only when an effective plan is evaluated.
- `Corporate catalog context` — an authenticated organization plus optional
  team, project, technology, owner, maintainer, assignment, and verification
  filters applied to the existing catalog search contract.
- `Governance history` — authorized audit and retired/revoked relation evidence
  for a tenant, with stable target, actor, reason, revision, timestamp, and
  correlation metadata.
- `Bulk distribution` — an explicit assign or revoke operation that evaluates
  one source assignment against a resolved set of member and project targets;
  it creates derived per-target state without copying the source policy.
- `Distribution result` — the per-target outcome of a bulk operation: `applied`,
  `skipped`, `conflicted`, `denied`, or `failed`.
- `Distribution state` — the observable per-target lifecycle state consumed by
  Web, CLI, and CI: `pending`, `installed`, `outdated`, `failed`, or `revoked`.

## Requirements

- `REQ-8501`: Governance relations distinguish authorship, operational ownership,
  maintainership, corporate verification, and exact-version assignment. Ownership
  spans a stable component/setup and may target the organization, team, project,
  technology, or employee; verification and assignment identify an exact
  published version. Retired/revoked rows remain queryable by authorized history
  reads with revision, actor, reason, timestamps, and audit correlation.
- `REQ-8502`: Assignments accept employee, team, project, and technology subjects.
  Team-derived employee rows are computed from current canonical team membership;
  leaving a team removes only the derived projection. Assignment never changes
  grants, harness state, or global author/component verification.
- `REQ-8503`: Governance writes use existing role bindings and `authorize()` with
  explicit permissions for read, edit, publish, verify, assign, ownership transfer,
  maintainer management, lifecycle/moderation, and audit/explain. Supported scopes
  are organization, team, project, technology, and catalog_object. Every mutation
  carries the current authorization revision, expected object revision, and an
  idempotency key; replay reauthorizes and returns the durable result.
- `REQ-8504`: Team detail extends the existing entity projection with authorized
  lead/members, canonical project/technology links, owned/maintained catalog
  objects, direct and team-derived assignments, effective capabilities, available
  actions, and redacted governance history. The active lead is an active member.
- `REQ-8505`: Existing component/setup search accepts optional corporate context
  from the authenticated session. Organization/team/project/technology,
  owner/maintainer, direct/effective assignment, corporate verification, harness,
  and existing public facets compose with OR within a facet and AND between facets.
  Authorization is applied before facets, totals, sorting, and pagination; public
  requests without context retain their current behavior and cannot observe private
  objects through counts, errors, or timing.
- `REQ-8506`: Corporate context additionally accepts technology-category filters and
  exposes a paginated organization-usage projection over readable teams, projects,
  and technologies for one stable setup or component. Direct and effective paths are
  deduplicated without erasing source, and authorization precedes rows and totals.
- `REQ-8507`: An assignment targets one stable setup or component line and carries
  an exact immutable selector or `latest`, plus an optional harness restriction.
  Exact selectors must identify an eligible published coordinate; wildcard,
  mutable, unverified, unavailable, and malformed coordinates are rejected.
  `latest` is never persisted as an installed coordinate and is resolved only by
  an authorized evaluation or installation-plan operation.
- `REQ-8508`: Effective assignment precedence is deterministic and documented as
  user, project, technology, team, then organization. Within a scope, a
  harness-specific assignment wins over an unrestricted assignment; an explicit
  user exception or revocation wins over inherited assignments. Effective results
  identify the winning assignment and source scope. `latest` resolves according
  to the same catalog eligibility and trust rules as exact selection, and the
  resulting plan records the exact version and digest.
- `REQ-8509`: Assignment mutations remain tenant-scoped and use the existing
  authorization evaluator, role bindings, expected revision, authorization
  revision, idempotency receipt, and audit history. Organization-wide and foreign
  tenant mutations are denied to actors without the corresponding scope
  permission. Retiring or changing an assignment does not rewrite prior history
  or silently mutate a materialized installation.
- `REQ-8510`: CLI and Web consume one generated effective-assignment contract and
  return the same winning source, exact resolved coordinate, and explainability
  fields. Evaluation and planning are read/plan operations separate from live
  provider installation or active-harness replacement.
- `REQ-8511`: A bulk assign or revoke request identifies one source assignment,
  an operation action, and a resolved target set across organization, team,
  project, technology, or individual-user scopes. Every request exposes a
  dry-run preview that lists affected members and projects, exclusions,
  individual overrides, and per-target planned results without mutation.
- `REQ-8512`: Applying a bulk request reuses the existing single-assignment
  mutation primitives and validates authorization and tenant ownership for each
  target. It preserves individual exceptions, does not copy the source policy,
  and returns an explicit per-target result of `applied`, `skipped`,
  `conflicted`, `denied`, or `failed`.
- `REQ-8513`: Bulk operations use the existing revision, authorization-revision,
  idempotency, and audit model. Repeated requests and retries return the durable
  per-target result without duplicate assignments, distribution rows, or audit
  events.
- `REQ-8514`: Partial application is visible: successful target changes remain
  observable while conflicted, denied, and failed targets retain their result
  and safe diagnostic. Updating or revoking the source assignment exposes the
  resulting effect for every affected member and project.
- `REQ-8515`: Web, CLI, and CI consume one generated distribution contract that
  exposes source explainability and per-target `pending`, `installed`,
  `outdated`, `failed`, or `revoked` state. Distribution state never silently
  rewrites an active provider-owned harness target.

## States and errors

Ownership is current for a stable component/setup coordinate and is transferred
or cleared by an exact expected revision. Maintainer, assignment, verification,
and lifecycle rows retain retired, revoked, or historical states rather than
rewriting the relation's past. Verification and exact assignments identify an
exact published version; an assignment may additionally use the `latest`
selector for future evaluation. Every evaluated or materialized plan contains
an exact eligible version and digest. Invalid typed identities, stale revisions,
missing idempotency, unavailable catalog versions, foreign tenant coordinates,
mutable or unverified selectors, and insufficient permissions are rejected
before a durable mutation. A dry-run has no durable side effect. Bulk apply
records one result per resolved target; target-local authorization, conflicts,
and failures do not erase successful targets. Replays reauthorize and return the
original durable result. Changing a `latest` assignment affects future plans
only; it does not rewrite assignment history or an existing materialized
installation.

## Security and privacy

All governance reads and writes first resolve the explicit organization and
current membership through the existing authorization evaluator. Permission
names and scopes are explicit and tenant-local; a governance relation never
creates a catalog grant, publication, installation right, global verification,
or provider authority. Search authorization runs before relation filters,
counts, sorting, and pagination, and unauthorized corporate context fails
without revealing object existence or relation counts. Audit history is
redacted to safe actor, target, revision, reason, timestamp, and correlation
metadata; bulk authorization runs for every resolved target inside its tenant
boundary; denied targets reveal no foreign membership or project data. Secrets
and personal data do not enter contracts, logs, or fixtures.

## Compatibility and migration

Migration `0076_milestone5_corporate_governance` is additive. It backfills
existing employee ownership into the typed owner coordinate, preserves legacy
owner account reads, adds technology assignment coordinates, and creates
maintainer, verification, and lifecycle relation tables. Existing public
catalog requests, publication workflows, role bindings, and catalog routes
remain compatible. Generated schemas, OpenAPI, provider projections, and web
clients are regenerated by the repository generators. Rollback can disable the
new governance routes and corporate search context without deleting incumbent
catalog, publication, membership, or audit data. The legacy exact-version
assignment request remains valid. Selector, harness condition, precedence,
explainability, and effective-plan fields are additive; existing exact
assignments keep their current semantics. No existing active installation is
rewritten during migration or latest-selector evaluation. Bulk operation and
distribution records are additive and retain the source assignment identity;
they do not duplicate assignment policy or rewrite provider-owned state.

## Acceptance

Contract, unit, PostgreSQL tenant/isolation, revision/idempotency/audit, API, Web
component, and E2E tests cover the governance matrix, derived assignments,
effective team profile, both catalog object kinds, URL-backed filters, and public
compatibility. Bulk contract/API/CLI/Web tests cover dry-run, target expansion,
exceptions, partial results, retries, and distribution-state retrieval. Generated
schemas and clients are updated only by repository generators.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-8501` | `tests/unit/test_corporate_governance_contracts.py::test_ownership_accepts_non_employee_subjects` and `::test_ownership_rejects_mixed_typed_subjects`; `tests/api/platform/test_corporate_catalog_assignments.py::test_exact_catalog_assignment_http` cover typed coordinates and exact-version assignments. |
| `REQ-8502` | `tests/unit/test_corporate_assignment_contracts.py` covers employee, team, project, and technology subject identity validation; `tests/api/platform/test_corporate_catalog_assignments.py::test_exact_catalog_assignment_http` covers the existing assignment route. |
| `REQ-8503` | `tests/api/platform/test_corporate_directory_authorization.py::test_corporate_profile_routes_are_registered` and `tests/contract/test_openapi.py` cover the additive route and revision/idempotency contract surface; the full API suite covers authorization and audit behavior. |
| `REQ-8504` | `tests/api/platform/test_corporate_entity_profiles.py` covers the existing team/entity projection and tenant authorization; the full API suite covers the additive profile response fields and redaction. |
| `REQ-8505` | `tests/contract/test_openapi.py` covers generated search contracts; Web unit tests cover corporate catalog loading and URL/query transport; the full API suite covers public compatibility and tenant isolation. |
| `REQ-8506` | Contract and PostgreSQL API tests cover technology-category filtering, setup/component usage pagination, direct/effective source, deduplication, authorization-before-count, and tenant isolation. |
| `REQ-8507` | Contract/API tests cover exact and `latest` selectors, harness conditions, immutable-coordinate validation, and rejection of mutable, unverified, wildcard, or unavailable selectors. |
| `REQ-8508` | Effective-assignment tests cover precedence, harness-specific selection, user exceptions/revocations, winning-source explainability, and exact version/digest resolution for `latest`. |
| `REQ-8509` | API tests cover tenant/scope authorization, revision/idempotency replay, audit retention, and the absence of live-installation mutation. |
| `REQ-8510` | Generated contract tests and CLI/Web integration tests compare the effective result and explanation fields across both clients. |
| `REQ-8511` | Bulk contract/API tests cover assign and revoke previews, affected member/project expansion, exclusions, individual overrides, all supported scope coordinates, and the no-mutation dry-run guarantee. |
| `REQ-8512` | Bulk API tests cover per-target authorization, tenant isolation, reuse of single-assignment validation, exception preservation, and the five explicit per-target results. |
| `REQ-8513` | Revision/idempotency/audit tests cover retry replay, duplicate suppression for assignments/distribution rows/audit events, and reauthorization on replay. |
| `REQ-8514` | Bulk API tests cover partial success, conflict/denial/failure visibility, update/revoke effects, and durable result retrieval. |
| `REQ-8515` | Generated contract, CLI/Web, and CI-consumer tests cover the five distribution lifecycle states and the absence of active provider-target mutation. |
