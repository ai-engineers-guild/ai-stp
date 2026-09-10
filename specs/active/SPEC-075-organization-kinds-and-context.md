---
description: "SPEC-075: Personal and corporate organization kinds, ownership boundaries, and active context."
last_verified: "2026-09-09"
---

# SPEC-075: Organization kinds and context

## Purpose

Provide one unambiguous remote ownership and tenant boundary for personal SaaS
and Corporate Hub while allowing local projects to remain organization-free.

## Scope

This specification owns issue #226. It defines organization identity and kinds,
personal ownership, corporate tenant ownership, active-context resolution, and
the migration of existing account-owned cloud data.

Corporate bootstrap, role hierarchy, membership mutation, team/project
administration, and exhaustive infrastructure isolation belong to issues #200
and #203. A separate `Workspace` domain entity is excluded.

## Terms

- `Organization` — the only remote ownership and tenant aggregate.
- `personal organization` — the single-user cloud organization belonging to
  one account.
- `corporate organization` — a multi-member tenant whose behavior is governed
  by corporate authorization.
- `OrganizationMembership` — the explicit relation between an account and a
  corporate organization; the personal owner relation is constrained to one
  account.
- `workspace` — UI wording for the selected local or organization context, not
  a machine identity.

## Requirements

- `REQ-7501`: Every organization has a stable `organization_…` identifier and
  immutable kind `personal` or `corporate`; kind conversion is prohibited.
- `REQ-7502`: Personal cloud initialization idempotently creates or returns one
  personal organization for the authenticated account. That organization has
  exactly one owning account and one active owner relation.
- `REQ-7503`: A personal organization cannot contain another member, team,
  corporate role binding, invitation, SAML binding, or organization-wide
  administration. `AccessGrant` remains a separate object-access relation.
- `REQ-7504`: A corporate organization may contain memberships and corporate
  resources only through the contracts owned by B2B-01 and later stages. Merely
  knowing its identifier grants no read or write capability.
- `REQ-7505`: Every corporate project, team, technology relation, assignment,
  telemetry scope, background job, audit event, and organization-owned catalog
  object stores one immutable `organization_id`; a missing organization on a
  corporate row is invalid.
- `REQ-7506`: Every organization-scoped API request names its organization
  explicitly. A session's remembered UI selection is presentation state and is
  never substituted when the request omits or changes the scope.
- `REQ-7507`: Machine contracts contain no `workspace_id`, workspace ownership,
  workspace table, workspace passport, or workspace lifecycle. UI workspace
  links resolve to either local context or an `organization_id`.
- `REQ-7508`: Local projects, local project passports, local registry objects,
  and local installation state require no organization row and do not receive a
  synthetic remote organization while offline.
- `REQ-7509`: Existing account-owned cloud data is migrated idempotently into
  that account's personal organization. Existing `owner_account_id`, author,
  device, grant, and audit attribution is preserved rather than rewritten as
  organization authorship.
- `REQ-7510`: A resource belongs to at most one organization. Assignment to a
  second organization, cross-organization join, and lookup by a foreign
  identifier fail before any protected resource fields are returned.
- `REQ-7511`: Organization identity is distinct from OAuth-provider and source
  host organizations such as GitHub or GitLab; linking a provider installation
  never creates or authorizes a product organization.
- `REQ-7512`: Organization context is propagated through API application
  services, database access, cache keys, jobs, search projections, object-store
  locations, exports, and audit records; every layer uses the same stable ID.

## States and errors

Context selection returns `local`, `personal`, or `corporate` together with
`ready`, `unauthenticated`, `organization_not_found`,
`organization_forbidden`, or `organization_suspended`. Non-enumeration policy
may map not-found and forbidden to the same public response. A personal
organization with a second owner relation is invalid persisted state, not a
recoverable UI state.

## Security and privacy

Organization scope is checked before loading a protected row or emitting a job.
Foreign organization identifiers do not appear in errors, logs, metrics, cache
keys visible to clients, or partial collection results. Local context never
uploads project data merely to create an organization. Infrastructure-operator
access remains outside product authorization.

## Compatibility and migration

Roll out additive organization and owner-relation tables first, then create one
personal organization per existing account with cloud data, then backfill
organization foreign keys, and only then make corporate ownership non-null and
enable corporate routes. Old clients continue through personal account routes
during the compatibility window. Rollback disables corporate routes but retains
organization rows and the preserved account attribution.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-7501` | Schema and migration tests enforce typed stable IDs and reject kind changes. |
| `REQ-7502` | Concurrent personal initialization returns one organization and one owner relation. |
| `REQ-7503` | Constraint and API tests reject a second member and every corporate-only relation in a personal organization. |
| `REQ-7504` | An authenticated non-member with a known corporate ID receives no resource or capability data. |
| `REQ-7505` | Migration and model tests reject each corporate resource family without an organization ID. |
| `REQ-7506` | Requests with absent, stale, or substituted organization scope fail without falling back to the remembered UI context. |
| `REQ-7507` | Schema/database inventories contain no Workspace aggregate or `workspace_id`, while UI context links resolve correctly. |
| `REQ-7508` | Network-disabled local project adoption and operation create no organization row or remote request. |
| `REQ-7509` | A migration fixture preserves account authorship and attaches every existing cloud row to exactly one personal organization on repeated runs. |
| `REQ-7510` | Hostile cross-organization read, write, list, search, and relationship tests fail before protected fields are loaded. |
| `REQ-7511` | Connecting GitHub/GitLab leaves product organization records and memberships unchanged. |
| `REQ-7512` | Integration tests carry the same organization ID through API, storage, job, cache, search, export, and audit boundaries. |
