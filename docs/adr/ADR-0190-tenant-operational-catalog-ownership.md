---
description: "Separate tenant operational catalog ownership from authorship and ownership claims."
last_verified: "2026-09-18"
---

# ADR-0190: Tenant operational catalog ownership

Status: accepted. Presentation and organization-usage consequences are clarified by
ADR-0193 and SPEC-086.

## Context

SPEC-083 REQ-8313 and the original Corporate Hub goal 9 require an employee to
own a setup or component operationally while its author can be someone else.
Catalog metadata ownership and ownership claims govern provenance and publication;
neither represents a tenant's operational responsibility.

## Decision

Retain one nullable owner employee and monotonically increasing revision per
organization, object kind, and existing stable setup/component ID. Ownership spans
versions. An exact published version is a read-access witness, not part of the
ownership key. No fictional UUID, passport edit, author transfer, ownership claim,
access grant, verification change, publication, or harness operation is produced.

Writes reuse the existing tenant-scoped `entity_profile.owner` authorization
for administrators and active organization team leads; reads require
`organization.read` and catalog read. Revealing an owner additionally requires
`member.read` or the explicit profile edit authority above. This relation read
does not grant an employee-directory list permission. Validate active same-tenant employee membership and exact catalog
access for both actor and designated employee on writes and receipt replays.
Unreadable or inactive owners cause an explicit denial, never an invented label
or empty result. Administrators can clear retained ownership without requiring
the departed employee to remain active.

Reuse corporate authorization, per-tenant mutation locking, canonical request
fingerprints, revision guards, durable idempotent receipts, and audit. Creation
expects revision zero; clearing requires the retained revision and retains the row.
Absent ownership reads return null owner and revision zero. Responses include a
nullable authorized employee display name and authoritative `can_edit` flag, with
no raw-ID label fallback. Candidates use the existing authorized employee directory
and exclude suspended employees. A receipt restores its original ownership effect
only after current authority and subject access are revalidated; the employee name
and edit capability are refreshed from current authorized state.

The write request carries `expected_revision` and `authorization_revision` in its
JSON body together with the idempotency key. Those fields are the mutation
precondition; this route does not use an `If-Match` header.

## Consequences

Migration `0075_corporate_catalog_ownership` follows
`0074_corporate_entity_profiles`. The model, contract, and separate API router are
registered by the integrating worker. Application rollback hides the endpoints
and retains rows, receipts, and audit. An explicit schema downgrade drops the new
table and is not an application rollback. Operational ownership grants no catalog
editing authority; those existing authorization boundaries remain in force.
The detail rail presents one read-only operational-owner card; owner mutation remains
an authorized action and does not turn the read card into an inline administration form.
