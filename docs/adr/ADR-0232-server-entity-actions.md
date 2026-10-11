---
description: "Project entity menus from the same authorization decisions used by mutations."
last_verified: "2026-10-11"
---

# ADR-0232: Server entity actions

Status: accepted.

## Context

Directory cards, related entities, catalog cards and detail pages independently
assembled permissions and menu order. Ownership exceptions and scoped grants
therefore produced different actions for the same principal and entity.

## Decision

The server owns the ordered entity action projection. Role permissions, direct
grants, active membership, author and operational ownership, and object state
contribute to one authorization decision. Presentation order is a separate
server registry filtered by that decision. Menus render the returned order and
translate action labels; they never infer authority from a role or edit right.
Every mutation rechecks current authorization, revisions and state. An action
projection is never an authorization token. Responses are private and uncached.
The same principal, entity and policy state receive the same action projection
on every surface. A failed projection is an explicit retryable error.

Personal access grants remain read access to a published major line. They do
not grant editing or delegation. Corporate operational ownership requires an
active organization and active membership. Scoped object permissions are
evaluated at the object, including organization descendant coverage.

## Consequences

Keep existing mutation endpoints and UI kit controls. Replace local menu
authorization and ordering with the shared projection. Batch visible entities
and bound requests. Regression checks compare projections and mutations across
solo authors, recipients, corporate roles, owners, leads and revoked membership.
Rollback restores the previous API and web images together; no data migration
is required.
