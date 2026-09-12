---
description: "One tenant-scoped technology registry and canonical relations with attached reviewed facts, not duplicate landscape edges."
last_verified: "2026-09-12"
---

# ADR-0181: Canonical technology relations and attached facts

Status: accepted.

## Context

Issues #207 and #209 both originally described project technology links and responsibility.
The current task assigns metadata/facts/landscape to #207 and canonical links to #209.
CorporateProject and ProjectIdentity currently expose separate persistence paths;
building another project matching layer would violate SPEC-078 and duplicate IDs.

## Decision

SPEC-080 owns technology/category metadata, aliases, lifecycle, versioned mappings,
reviewed usage facts and projections. SPEC-081 owns the one project–technology pair,
project–team links and technology responsibility. Usage contexts, versions and
immutable observations attach to a pair; they never create another pair model.
Subject/applicability references retain explicit meanings and never count as uses.

The governed registry is organization-scoped. Imported canonical seed identities
and mapping provenance are retained; one tenant's correction, approval or ownership
does not change another tenant's registry. Requests resolve identities with their
explicit organization. Canonical metadata is stored separately from organizational
adoption/responsibility. There is no new global-write authority for tenant admins.
Stable `technology`, `category`, and `relation` ID prefixes extend SPEC-015's closed
registry; they are not harness/setup/component kinds or passport object kinds.

Integrate corporate project administration with the existing remote ProjectIdentity
using exact IDs, preserving legacy `remote_project` spelling and all existing
memberships, role bindings, receipts, ProjectLinks, revisions and audit attribution.
No name, URL, path, category or technology similarity creates an identity or link.
Corporate metadata remains an extension of that remote identity, not a second
independently matched project. Conflicting exact identity metadata aborts migration
instead of being silently overwritten.

Keep direct current/retired links without validity periods. Common append-only audit
is the history of structural changes; immutable observations are evidence history,
not a second structural temporal database. Current authorization and assignment
scope evaluation queries live links and still requires explicit permissions.
Responsibility alone grants no authority. Archive/removal invalidates applicable
scopes atomically with the policy revision.

The #222/#208 handoff carries canonical IDs, versions, completeness and safe evidence.
It proposes observations; manual decisions survive rescans. Missing detectors or
forge availability never block manual declaration or responsibility management.
Landscapes filter authorized projects first and count distinct remote project IDs.
No popularity/confidence-derived radar policy, evidence execution, model call,
credential collection, or harness installation is introduced.

## Consequences

Migration adds tenant-compatible keys, exact project identity integration, registry
and canonical relations before enabling API/Web. Existing IDs and evidence survive
renames, lifecycle changes, merges and restoration. Seed/import receipts preserve
manual changes. Merge conflicts require an explicit reviewed resolution.

Schemas/OpenAPI/client/projections are regenerated from source. Migrate first, deploy
API second and Web third. Rollback disables new operations and reverts application
commits while retaining registry, relation, identity and audit data. A destructive
schema downgrade requires a verified recoverable backup, not an automatic revert.

## Revisit conditions

A shared public global technology registry requires a separate governance/access
decision and migration contract; tenant maintainers cannot acquire that authority
implicitly. Temporal interval semantics require a new task and ADR, not speculation.
