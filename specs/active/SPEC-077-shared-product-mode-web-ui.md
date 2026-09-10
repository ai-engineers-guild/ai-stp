---
description: "SPEC-077: One shared Next.js UI for local, personal, and corporate product contexts."
last_verified: "2026-09-09"
---

# SPEC-077: Shared product-mode Web UI

## Purpose

Use the existing Next.js application and design system to present local,
personal SaaS, and corporate capabilities without a second administration
frontend or duplicated resource component trees.

## Scope

This specification owns issue #228. It defines shared navigation, context
selection, route and component behavior, local API use, capability gating,
state presentation, localization, accessibility, and browser verification.

It does not define the domain behavior of future teams, technology registry,
landscape, assignments, audit, telemetry, invitations, SAML, or deployment
operations. Their owning specifications add capabilities and data contracts to
the shared surfaces. It does not permit Web to read SQLite, PostgreSQL, provider
APIs, or object storage directly.

## Terms

- **Shared resource surface** — one route/page/component family used for the
  same resource in every context where its capability exists.
- **Context switcher** — the UI control that selects local context, the personal
  organization, or an authorized corporate organization.
- **Local API session** — the explicitly started loopback FastAPI process that
  exposes local contracts for the current Web session.
- **Unavailable state** — the capability exists but its required service or
  local session is unavailable; it is distinct from forbidden and empty.

## Requirements

- `REQ-7701`: One Next.js application shell and route/component tree serves
  local, personal, and corporate contexts. A corporate context does not load a
  separate admin application or parallel corporate-only implementation of a
  shared resource.
- `REQ-7702`: The context switcher lists local context when a local API session
  is available, the authenticated account's personal organization, and only
  corporate organizations visible to the current account. Selection changes
  the explicit context used by subsequent reads and actions.
- `REQ-7703`: Navigation, layouts, routes, page sections, controls, and actions
  are derived from `ContextCapabilityProjection`. Hidden UI is never treated as
  proof that the corresponding API operation is authorized.
- `REQ-7704`: Projects, technologies, landscape views, catalog objects, tables,
  and simple charts use shared resource surfaces and schemas. Context-specific
  additions compose into those surfaces without changing the meaning of the
  shared fields.
- `REQ-7705`: Local mode obtains data only through the session-scoped loopback
  API and remains useful without a Corporate Hub server. Starting or ending the
  local Web session does not create an account, organization, daemon, or cloud
  synchronization operation.
- `REQ-7706`: Corporate-only staff, teams, ownership, assignments, audit,
  telemetry, invitations, SAML, and enterprise-operation sections render only
  when their capabilities exist and reuse the current shell, tokens, forms,
  tables, dialogs, and feedback patterns.
- `REQ-7707`: Empty, unavailable, forbidden, unauthenticated, stale, loading,
  partial, and failed states are visually and semantically distinct. An
  unavailable or forbidden resource is never shown as an empty collection.
- `REQ-7708`: Context changes cancel or ignore in-flight responses from the old
  context, clear context-bound caches and optimistic state, fetch a fresh
  projection, and never display old-organization data under the new heading.
- `REQ-7709`: All backend calls use the generated API client and explicitly name
  the selected organization or local context. Web does not infer tenant scope
  from a hidden field, hostname, stale cookie, or cached page payload.
- `REQ-7710`: `public_saas` and `self_hosted` build profiles may control their
  existing deployment-owned content features but do not select product mode,
  bypass the context switcher, or synthesize capabilities.
- `REQ-7711`: New and changed UI has English/Russian parity, WCAG 2.2 AA
  semantics, visible keyboard focus, reduced-motion support, and no
  document-level overflow at 360 px, 430 px, tablet, and desktop widths.
- `REQ-7712`: Shared surfaces are verified by a generated mode/capability matrix
  covering route entry, direct URL, context switching, component/action
  visibility, request scope, stale projection, and server denial.

## States and errors

The context shell has `loading`, `ready`, `empty`, `unavailable`, `forbidden`,
`unauthenticated`, `stale`, `partial`, and `failed` states. A stale context
refreshes capabilities before actions resume. A lost local API session offers an
explicit restart path and does not fall back to a remote corporate endpoint.

## Security and privacy

Server-rendered and client-side requests use the same explicit context. Cached
responses are partitioned by context identity and authorization revision. The
browser receives no policy graph, provider token, local filesystem path, private
passport bytes, or foreign organization identifiers. The local API binds to
loopback and requires a session-scoped anti-CSRF secret for mutations.

## Compatibility and migration

Introduce the context shell and capability projection before corporate sections.
Existing public and owner routes continue to resolve to the personal context
during the compatibility window. Shared surfaces migrate incrementally without
changing their public URLs unless a context identifier is required for safe
scope. Rollback hides new context selection and corporate sections while
preserving existing personal and public behavior.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-7701` | Route and bundle inventories find one application and one implementation for each shared resource family. |
| `REQ-7702` | Browser fixtures show local, personal, and authorized corporate choices and omit an unrelated organization. |
| `REQ-7703` | Capability fixtures drive every route/action, while direct forged requests are still rejected by API tests. |
| `REQ-7704` | The same project, technology, landscape, catalog, table, and chart components render compatible local/personal/corporate fixtures. |
| `REQ-7705` | With the network disabled, a loopback session serves local workflows and its shutdown leaves no process, account, organization, or sync event. |
| `REQ-7706` | Corporate sections appear only for their capability and use the shared design-system inventory. |
| `REQ-7707` | Component and accessibility tests distinguish every state and never render unavailable/forbidden as zero items. |
| `REQ-7708` | A delayed response from organization A cannot populate organization B after a context switch. |
| `REQ-7709` | Network assertions show only generated-client calls with explicit scope and no direct storage/provider access. |
| `REQ-7710` | Both web build profiles produce the same mode and authorization verdict for identical context fixtures. |
| `REQ-7711` | RU/EN, axe, keyboard, reduced-motion, and responsive browser checks pass at all declared widths. |
| `REQ-7712` | The generated mode/capability browser matrix covers every shared route and fails on a deliberately ungated action. |
