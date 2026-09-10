---
description: "Personal and corporate organizations are the remote ownership aggregates; workspace is only an active UI context."
last_verified: "2026-09-09"
---

# ADR-0176: Organization is the remote ownership aggregate

Status: proposed.

## Context

Current server resources are primarily account-owned, while local projects and
passports work without a server identity. Corporate Hub needs tenant ownership,
membership, teams, projects, technology records, catalog objects, assignments,
audit, and later SAML. Introducing a generic `Workspace` aggregate beside an
organization would create two identifiers for the same ownership and isolation
boundary.

The word workspace is still useful in the interface: it describes the context
currently shown to the user. That presentation concept does not require another
domain object.

## Options

1. Keep account ownership and add optional team fields to resources. This cannot
   define a stable corporate tenant or enforce complete tenant isolation.
2. Add both `Workspace` and `Organization`, with resources assigned to one or
   both. This creates ambiguous ownership, membership, and authorization joins.
3. Use `Organization` as the only remote ownership aggregate, with `personal`
   and `corporate` kinds; resolve a UI workspace to an organization.

## Decision

Option 3 is selected.

Every remote organization has a stable `organization_…` identifier and the
immutable kind `personal` or `corporate`.

A personal organization has exactly one owning account and one active owner
membership. It cannot contain teams, corporate roles, invitations, SAML
bindings, or organization-wide administration. Account-to-account catalog
grants remain separate `AccessGrant` records and do not turn the personal
organization into a multi-user tenant.

A corporate organization owns its memberships and every corporate project,
team, technology relation, assignment, telemetry scope, job, audit event, and
organization-owned catalog object. Corporate authorization is evaluated within
that organization. A remote resource belongs to exactly one organization; an
identifier from another organization is rejected before the resource is read.

`Workspace` is a UI label for the selected local or organization context. There
is no `workspace_id`, workspace table, workspace passport, or independent
workspace lifecycle. Server requests name their organization scope explicitly;
a remembered UI selection is not authority.

Local projects retain local identities without an organization. Existing
account-owned cloud data is migrated into one personal organization per account,
while `owner_account_id` remains the actor or author attribution where that fact
is required. Organization transfer is not implicit and is not introduced by
this decision.

## Consequences

- `SPEC-075` owns organization kinds, invariants, migration, and context reads.
- B2B-01 owns corporate bootstrap, roles, membership mutation, and exhaustive
  tenant-isolation implementation.
- Server storage gains an organization boundary before corporate resources are
  enabled; nullable or missing tenant ownership is not valid for corporate rows.
- Existing personal data keeps its account attribution and receives an additive
  personal organization assignment.
- UI copy may say workspace, but all machine contracts use local context or
  organization identity.

## Revisit conditions

Revisit this decision if one remote resource must be jointly owned by several
organizations, if a personal context becomes genuinely multi-user, or if a
separate collaboration aggregate gains lifecycle and policy that cannot belong
to an organization.
