---
description: "Participation roles on projects, a scoped teammates projection, an organization people-visibility policy, and category as a binding scope."
last_verified: "2026-10-02"
---

# ADR-0223: Corporate participation and scoped people visibility

Status: accepted. ADR-0220 authorization semantics remain binding; this record
separates *participation* (who works on a team, project, or technology) from
*access* (which permissions a principal holds) and defines how people are
visible to each other. Implemented behavior is recorded in SPEC-079.

## Context

The current model conflates three different things under one word "role":

- the organization role on `OrganizationMembership` (an access role bound at
  organization scope);
- the participation role on `CorporateTeamMember` (`lead | staff`), which the
  membership synchronization materializes into a binding carrying the
  *organization* role name at team scope;
- `CorporateProjectMember`, which has no role at all — project assignment
  copies the member's organization role into a project-scope binding, so a
  staff employee can silently inherit lead authority on a project.

People visibility has only one knob: `member.list` / `member.read`, both
organization-wide administrative permissions. An ordinary member cannot see
who they work with; a holder of `member.read` sees the entire roster. There is
no "teammates" projection and no organization-level choice between an open
roster, scoped visibility, and admin-only visibility.

Technology categories (`category.*` permissions exist) cannot be a binding or
grant scope, so "owner of a category" cannot be expressed even though category
ownership is a real organization concept.

## Options

1. Keep one role concept and document the ambiguity. The record already proved
   confusing: the UI rendered the same person twice and assignment copied the
   wrong role.
2. Add participation as a separate relation family with its own closed role
   vocabularies, materialized into scoped bindings by fixed mapping; add a
   teammates projection gated by membership and an organization visibility
   policy; add `category` as a scope kind.
3. Add a generic "contextual role" entity usable for teams, projects,
   categories, and future kinds. This is a second role system beside the RBAC
   role table and duplicates lifecycle/audit rules.

## Decision

Choose option 2.

**Participation roles.** `CorporateProjectMember` gains `role`, a closed set
`owner | lead | contributor | staff`, default `staff`. Team participation
keeps `lead | staff`. Participation materializes to access through a fixed
mapping, never by copying the member's organization role:

- project `owner` or `lead` → `lead` binding at that project's scope;
- project `contributor` or `staff` → `staff` binding at that project's scope;
- team `lead` → `lead` binding at that team's scope;
- team `staff` → `staff` binding at that team's scope.

A binding written by this mapping keeps its `assignment` origin and is
replaced — not accumulated — when the participation role changes. Removing
participation revokes the derived binding. Organization-role bindings
(`membership` origin) are untouched by participation writes.

**Teammates projection.** `GET /v1/corporate/organizations/{id}/teammates`
returns the reduced people projection: `account_id`, `display_name`, and the
contexts the caller shares — `team` or `project` id, name, and the subject's
participation role. No email, job title, organization role, or account state
is exposed. The gate is active organization membership plus, per context, the
caller's co-membership *or* a `member.list` permission at that exact scope.
`member.list` at organization scope still opens the administrative registry;
it is not required for the teammates projection.

**People visibility policy.** The organization carries `people_visibility`
with values `members | teammates | admins`, default `teammates`:

- `teammates` — the projection shows co-members of shared teams and projects;
- `members` — the projection returns every active member (open roster);
- `admins` — the projection returns only contexts where the caller holds a
  scoped `member.list` grant; ordinary members see themselves.

`member.read` of a single member stays an administrative permission. The
teammates projection is not a substitute for it and never returns its fields.

**Member scope extension.** `member.list` and `member.read` may be evaluated
at `team` and `project` scopes; the `member` scope target (one account) also
matches bindings on the teams *and* projects the target member belongs to.
The permission matrix advertises `member` at
`organization | member | team | project`.

**Category scope.** `category` is a `ScopeKind` and `GrantScopeKind`. A
`category`-scope binding or grant applies to every technology classified in
that category (through `TechnologyClassification`), in addition to matching
`category` scopes directly. Category existence is checked against
`technology_category`.

## Consequences

- `CorporateProjectMember` and the `Organization` policy field require a
  schema migration; new columns get safe defaults so existing rows keep their
  current effective behavior (`staff` participation, `teammates` visibility).
- The teammates endpoint must not emit audit events on read. List/read audit
  emission was removed across the corporate read surface; only audit-journal
  reads (`audit.list`, `audit.export`) keep self-audit per REQ-7912.
- The built-in `lead` role gains `member.manage` so participation assignment
  matches the other member-write permissions it already holds; migration 0112
  backfills existing organizations because built-in matrices are immutable.
- The assignment services that materialize participation into bindings update
  their origin payloads so the journal shows participation, not an opaque
  organization-role copy.
- Tests: participation → binding mapping (including role change and removal),
  teammates projection filtering under each policy value, `member.list` at
  team/project scopes, category-scope binding matching on classified
  technology, and the matrix advertisement.
- SPEC-079 / SPEC-083 rewrite reflects the implemented semantics in the same
  change.

## Revisit conditions

Revisit if a participation role needs permissions the fixed binding mapping
cannot express, or if `members` visibility is requested together with
field-level member restrictions.
