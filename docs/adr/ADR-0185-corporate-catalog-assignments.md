---
description: "Separate corporate catalog assignments from authorization and harness installation."
last_verified: "2026-09-13"
---

# ADR-0185: Corporate catalog assignments

Status: accepted.

## Context

SPEC-083 requires assigning an exact setup or component version to employees,
teams and projects. Existing catalog-object role bindings grant access; they do
not represent an operational assignment. Harness installation remains owned by
the CLI and its provider.

## Decision

Persist an organization-owned catalog assignment independently from role bindings.
The subject is one existing employee, team or project in that organization. The
object is one readable catalog setup or component identity at an exact X.Y version.
Validate both ends under the acting account before every mutation. Assignment does
not grant catalog access, change visibility, attest verification, or install a setup.

Use a stable assignment identity, current/retired state, revision guarding and
idempotent receipts. Enforce uniqueness of the subject, object kind, identity and
version within an organization. Retain retired assignments for audit and recovery.

Employee views distinguish direct assignments from assignments derived through
current team memberships. Derived rows reference their source team and assignment;
they are projections, not copied writes. Removal of team membership removes the
derived projection without deleting the team's assignment. Catalog links remain
subject to the viewer's access: assignment is never an access bypass.

## Consequences

Add assignment storage and contracts before enabling assignment controls. Test
cross-organization subjects, unreadable catalog versions, concurrent mutations,
receipt replay and derived membership changes. Rollback hides the new controls and
retains the additive storage; it never deletes assignment history or changes grants.
