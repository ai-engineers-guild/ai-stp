---
description: "SPEC-081: Single canonical team/project/technology relationships, responsibility, and current assignment scopes."
last_verified: "2026-09-12"
---

# SPEC-081: Canonical corporate relations

## Purpose

Implement #209 as the sole owner of corporate team/project/technology relations.
SPEC-080 supplies technology metadata and facts, not competing relationship rows.

## Scope

Direct current links, responsibility, reverse navigation, authorization/assignment
scope evaluation, and audit history. No validity periods or temporal intervals.
Existing member-to-team/project assignments remain member relations, not substitutes
for project-to-team ownership. Harnesses, setups and components keep their identities.

## Terms

- `Project–technology relation` — one canonical link per tenant/project/technology.
- `Project–team relation` — one canonical link per tenant/project/team, with role.
- `Responsibility` — an organization decision on a canonical relation, not a
  property changing technology identity or an automatic permission grant.
- `Historical read` — retained facts/archived metadata and safe common-audit
  changes, not a second interval-versioned relationship database.

## Requirements

- `REQ-8101`: The canonical project–technology link has immutable identity and
  tenant, stable remote project and technology references, revision, and current
  or retired state. There is at most one link per pair; multiple contexts,
  versions and evidence attach to this link through SPEC-080 usage facts.
  No second technology-use join table, landscape-owned relation, or assignment
  snapshot models the same pair. Retire/reactivate preserves link identity.
  Canonical link identities use the registered `relation` prefix (ADR-0181).
- `REQ-8102`: Projects link to zero or more teams; teams link to zero or more
  projects. Each pair has one current direct relation with `owner`, `responsible`,
  or `contributor` role. A project has at most one current owner team; additional
  responsible/contributor teams are permitted. Ownership replacement is an exact,
  revision-checked atomic operation, never an intermediate two-owner state.
  Removal and later recreation preserve resolvable identity/history.
- `REQ-8103`: A technology has zero or more responsible teams and at most one
  designated responsible lead account per organization. Responsible accounts
  must be active tenant members; teams must be same-tenant and active when assigned.
  A technology/team pair has one canonical responsibility record. Organizational
  approval/adoption decisions attach to canonical technology context, separate
  from technology metadata. Responsibility neither duplicates project usage nor
  changes registry identity or lifecycle.
- `REQ-8104`: Explicit `subject` and `applicability` references from catalog setups
  and components are distinct from project `uses` meaning. A PostgreSQL-addressing
  MCP component and React-subject skill can be referenced without creating project
  use, ProjectLink, ownership, or an installed harness. Only reviewed project-use
  facts contribute to SPEC-080 usage counts.
- `REQ-8105`: Every project relation references the canonical remote project
  identity consumed by SPEC-078. Integrate existing corporate administration and
  ProjectIdentity without name/URL/technology matching or duplicate project creation.
  Migration retains existing IDs, memberships, role bindings, receipts, links and
  audit attribution; existing legacy ID spelling is not grounds to replace identity.
  Newly created corporate projects are available to both administration and
  explicit link/sync consumers through the same remote identity.
- `REQ-8106`: API/Web team, technology and project details expose the same current
  relationships, responsibility and reverse navigation. Create/change/remove,
  archive/restore and historical reads use the same model. Archived endpoints
  retain historical relations and safe metadata, are excluded from default active
  scopes/totals, and reject new links; authorized removal remains possible.
  Restore evaluates retained links against current target/member states.
- `REQ-8107`: Current assignment and authorization evaluation reads canonical
  relations rather than copying teams/technologies into assignment payloads or
  permission snapshots. An applicable explicit role binding and its permissions
  are still required; a responsible-team/lead label alone grants no authority.
  Team/project/technology scope expansion, where supported, evaluates current
  same-tenant links and active endpoints. Ownership/link/archive changes invalidate
  authorization revisions atomically and revoke obsolete effective scopes.
  Existing member-assignment endpoints retain their separate meaning.
- `REQ-8108`: Relation CRUD and responsibility changes are independently scoped
  and authorized using the shared evaluator. `project_team`, `project_technology`,
  `technology_team`, and
  `technology_decision` have separate create/read/update/delete/list permissions;
  project metadata update is not a relationship mutation grant. Relationship
  grants use the project or technology endpoint scope; reverse reads also require
  permission to read both endpoints. Organizational approval additionally requires
  the technology approval permission. Staff cannot mutate ownership outside
  explicit grants. Entity revisions plus authorization revision protect competing
  changes. Tenant-partitioned effect fingerprints and idempotent receipts bind all
  endpoint identifiers and requested effects; replay reauthorizes but does not
  repeat the mutation or manufacture another relationship/history entry.
- `REQ-8109`: Composite tenant foreign keys, FORCE RLS and service authorization
  cover forward/reverse reads, mutations, lists, counts and assignment evaluation.
  Filter both endpoints before returning links, suggestions or aggregation.
  Common append-only audit records actor, correlation, reason, outcome and safe
  before/after for changes, removal, denial and replay. Historical responses never
  expose a foreign or currently unauthorized endpoint. No temporal relation store.

## States and errors

Relations are current or retired; project/team lifecycle remains active or archived
under SPEC-079. Technology lifecycle and usage review remain SPEC-080 dimensions.
Responsibility removal is not registry deletion. Use corporate forbidden/stale/
revision-conflict conventions plus explicit relation-conflict, unavailable-target
and invalid-role reasons. Unknown and foreign identifiers remain non-enumerating.

## Security and privacy

Endpoint ownership and permission checks precede protected hydration and aggregation.
Ownership does not grant credentials or source-provider access. Relation history
contains safe metadata, not source bytes, tokens, email addresses or private paths.
Every introduced background evaluator reauthorizes immediately before effects.

## Compatibility and migration

Add identity integration, direct relations and tenant constraints before enabling
API/Web. Backfill only exact known identifier relationships, never guessed matches.
Preexisting relations and receipts remain readable; additive contract fields preserve
old clients. Regenerate all derived contracts from source. Deploy migrations, API,
then Web. Rollback disables new operations but retains identities, links, decisions
and audits. Do not downgrade/drop relationship history without verified recovery.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-8101` | Duplicate-pair/concurrency and retire/reactivate tests retain one link; usage evidence never creates another pair model. |
| `REQ-8102` | Cardinality and atomic owner-replacement tests cover multiple teams, removal and historical reads. |
| `REQ-8103` | Responsibility CRUD checks active same-tenant targets, lead cardinality and independent technology identity. |
| `REQ-8104` | MCP/skill subject fixtures produce zero project-use counts and no installation or project-link effects. |
| `REQ-8105` | Migration and project create/rename/archive/link tests preserve exact IDs and one canonical identity. |
| `REQ-8106` | API/Web forward/reverse lifecycle and navigation tests share identical filtered relations. |
| `REQ-8107` | Assignment/scope evaluation observes current link changes and archive state without snapshots or implicit grants. |
| `REQ-8108` | Scoped staff/lead/admin, stale entity/policy revision, competing ownership and effect-replay matrix. |
| `REQ-8109` | Hostile tenant, FORCE-RLS, restricted historical read, audit/privacy and background-evaluation tests. |
