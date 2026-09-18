---
description: "Retain corporate project identities and history through an authoritative lifecycle with a compatible legacy state projection."
last_verified: "2026-09-12"
---

# ADR-0183: Retained corporate project lifecycle

Status: accepted.

## Context

SPEC-081 requires separate project deprecation, deletion and activity filters.
Existing corporate project deletion physically removes metadata and conflicts
with retained canonical links. Extending the existing closed wire `state` enum
would break older readers and rollback compatibility (SPEC-015 REQ-1510).

## Decision

Keep the exact corporate/remote project ID established by ADR-0178. Add one
authoritative corporate `lifecycle`: active, deprecated, archived or deleted.
The legacy corporate `state` is only its compatibility projection: active for
active lifecycle, archived otherwise. It is not a second independently editable
lifecycle. Database enforcement and the shared mutation lock keep the projection
consistent. Legacy changes to the active/archive projection remain supported;
they update the authoritative lifecycle rather than leaving divergent fields.
An unchanged projection in a rename does not downgrade a deprecated lifecycle.

Expose lifecycle as an optional additive field on corporate project views and
through an explicit lifecycle mutation contract. Existing closed state values and
published snapshots remain unchanged. Remote identity availability remains active,
archived or deleted: deprecated corporate projects project to archived availability.
No second project identity, matching layer, relationship table or permission
snapshot is introduced.

Deletion is a retained tombstone: preserve corporate metadata, the remote identity,
ProjectLinks, memberships, canonical relation IDs, facts and audits. Retained
bindings become ineffective at inactive endpoints; deletion does not destroy their
identifiers. Deleted projects reject ordinary new work and require an explicitly
authorized lifecycle restoration. Archive restoration retains the prior active or
deprecated lifecycle. Deprecation, archival and deletion are separate from repository
activity and technology governance.

## Consequences

An additive migration backfills lifecycle from exact existing corporate/remote
states and installs projection enforcement before new writers are enabled.
Scoped lifecycle writes use entity and authorization revisions, tenant-fingerprinted
receipts and safe transactional audit. Current active counts exclude all non-active
lifecycles; historical reads retain references under current permissions.

Older readers continue to accept the legacy state projection. Rollback disables
new lifecycle/landscape mutations and reverts applications while retaining the
additive columns, projection enforcement and tombstones. It does not downgrade,
drop project data or resurrect deleted projects. Destructive downgrade requires
a separately verified recovery backup.

## Revisit conditions

Removing the compatibility projection requires a declared reader migration and
mixed-version evidence. A future retention/deletion policy is a separate decision,
not permission to physically delete retained history here.
