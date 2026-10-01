---
description: "Proposed authoritative access descriptors, scoped provenance, and bounded delegation for corporate authorization."
last_verified: "2026-09-29"
---

# ADR-0220: Explainable corporate access and delegation

Status: proposed. Current authorization remains governed by ADR-0179.

## Context

The current evaluator special-cases the `superadmin` role name for scope
propagation. The permissions endpoint can associate an action with roles that
did not grant it. Membership synchronization can select independent bindings
in the same scope. Invitation and binding paths must not permit a caller to
grant authority beyond their delegation limit. These are source-level risks
identified against the current tree; exploitability and complete endpoint
coverage require targeted tests before claims of remediation.

## Options

1. Make the Web matrix authoritative. It cannot protect forged API requests or
   private delivery and would diverge from service checks.
2. Extend the ADR-0179 evaluator and persisted role/binding model with one
   descriptor inventory, explicit scope coverage, grant provenance, and
   decision explanations. Reuse bulk evaluation and current revisions/audit.
3. Add a policy engine and arbitrary expressions. This adds a language,
   migration, and operating dependency beyond the closed action set.

## Decision

Choose option 2. An action descriptor exists only when a server handler checks
that action. It names the stable permission, resource/action, supported scopes,
coverage, create parent, resource-state preconditions, and implementation status.
Descriptors describe enforcement; they do not synthesize permissions from a UI
column. Existing wire names remain stable unless a versioned migration proves a
replacement. Unsupported, forbidden, and state-blocked are separate outcomes.

The evaluator returns a decision for one principal, action, resource, and
organization, including only the bindings/direct grants/relationships that
actually contributed to that action and their inheritance and scope path.
Single and bulk decisions must be equivalent. An organization binding's
coverage is explicit and never inferred from the role name. Create checks run
against the authorized parent/container before a child exists. Ownership and
contributor relationships have action-specific effects.

Role definition, role assignment, membership-derived binding, and a direct
personal allow are distinct records. Membership synchronization changes only
its own provenance. A direct allow is tenant-scoped, action-scoped, revisioned,
audited, and revocable; V1 has no personal deny policy. The issuer cannot use
invitation, role parent change, role editing, employee update, or binding APIs
to grant a role/action/scope they cannot delegate. The server computes
grantable options and rechecks at write time and invitation acceptance.

One transaction protects the last effective active organization superadmin
across membership, binding, scope, and state changes. Parent-role cycles fail
before mutation. Current access is checked for every protected read/write;
navigation hints and stale explanations do not authorize requests. A changed
policy revision invalidates derived results. Audit records safe actual source
IDs and before/after effects, not tokens or entire private artifacts.

## Consequences

- First add regression tests for delegation, independent bindings, role cycles,
  last-admin transitions, single/bulk parity, tenant filtering, and explain.
- Extend the existing evaluator and contracts; do not create a parallel RBAC
  service or a global decision cache.
- Migrate old binding origin/coverage only when proven; classify ambiguous
  rows for review and retain their prior effective behavior until resolved.
- The proposed default-role policy is a separate previewed migration, not a
  side effect of the access UI. Rollback preserves audit and grant records.
- Rewrite `SPEC-079` from tested behavior in the implementing change.

## Revisit conditions

Revisit if closed descriptors cannot express a real protected operation, or
measured bulk evaluation cannot meet the existing request budget.
