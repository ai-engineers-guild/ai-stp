---
description: "A versioned capability projection drives one shared web UI while API authorization remains authoritative."
last_verified: "2026-09-09"
---

# ADR-0177: Server capabilities drive one shared UI

Status: proposed.

## Context

B2B-00 requires one Next.js application for local, personal SaaS, and corporate
contexts. The current web build profiles control deployment-owned features, and
the current Web/API boundary uses generated contracts. Corporate RBAC cannot be
copied into React, while hiding a control in the browser cannot authorize the
request behind it.

Local mode also cannot depend on corporate endpoints or allow the browser to
read SQLite directly. A second admin frontend or a duplicated corporate
component tree would make behavior and accessibility diverge.

## Options

1. Implement role checks and route tables independently in Next.js. This makes
   the browser a second policy engine and becomes stale after permission changes.
2. Build a separate corporate administration frontend. This duplicates shared
   catalog, project, technology, navigation, and design-system behavior.
3. Publish a compact versioned capability projection from the authoritative
   Python boundary and use it to drive one shared route/component tree.

## Decision

Option 3 is selected.

The capability projection contains the product mode, explicit context identity,
a monotonic authorization revision, generation time, and a sorted closed set of
capability identifiers. It does not contain the role graph, policy rules, hidden
resource identifiers, or data from another organization.

For personal and corporate contexts, FastAPI evaluates authentication,
organization membership, scoped policy, and resource constraints before
returning the projection and again on every protected request. The projection is
rendering guidance, never an authorization grant. Permission changes advance the
authorization revision; stale mutating requests fail and require a fresh
projection.

For local mode, an explicitly started loopback FastAPI session exposes the same
contract family over local application services. It requires no account, binds
only to loopback, uses a session-scoped anti-CSRF secret, and is not a persistent
daemon. Next.js does not read the local registry or invoke CLI internals directly.

One Next.js route and component tree renders shared resources. Capabilities
control navigation, page availability, action visibility, and requests. Empty,
unavailable, and forbidden remain distinct states. Corporate-only staff, team,
assignment, audit, and SAML surfaces compose from the same design system and
shell rather than a separate frontend.

The `public_saas` and `self_hosted` build profiles remain limited to deployment
features. They do not add capabilities and are not consulted by API
authorization.

## Consequences

- `SPEC-076` owns the capability wire contract and invalidation behavior.
- `SPEC-077` owns shared route, component, and local/personal/corporate UI
  behavior.
- The generated API client remains the only Web/backend contract boundary.
- Local web operation adds an on-demand loopback API process but no resident
  daemon and no direct browser filesystem access.
- Every protected scenario needs both rendering tests and server-side denial
  tests; a UI-only test is insufficient security evidence.

## Revisit conditions

Revisit this decision if the capability set becomes too large for bounded
projection, if offline Web cannot be delivered safely through an on-demand
loopback boundary, or if a corporate surface proves unable to share the current
application shell and design system without duplicating domain behavior.
