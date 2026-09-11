---
description: "SPEC-077: Shared Next.js SaaS UI with server-resolved product context."
last_verified: "2026-09-11"
---

# SPEC-077: Shared product-mode Web UI

## Purpose

Use one Next.js application and design system for the authenticated SaaS
surfaces whose mode, endpoint, settings, and capabilities are resolved by the
authoritative backend.

## Scope

This specification owns issue #228. It defines shared SaaS navigation, backend
context propagation, route and component behavior, capability gating,
localization, accessibility, and browser verification.

Local operation remains a CLI concern and does not start a loopback process or
expose a local-mode control in Web. Web never reads SQLite, PostgreSQL, provider
APIs, or object storage directly.

## Terms

- **Shared resource surface** — one route/page/component family used for the
  same resource wherever the server grants its capability.
- **Server-resolved context** — the mode, organization, backend endpoint, and
  settings returned or enforced by the authenticated backend request.
- **SaaS default** — the authenticated personal organization returned by the
  configured backend when no other server-owned authority applies.

## Requirements

- `REQ-7701`: One Next.js application shell and route/component tree serves
  personal and corporate SaaS surfaces. Local mode is served by the CLI and is
  not a Web context.
- `REQ-7702`: Web exposes no product-mode or organization selector. It sends the
  authenticated session to its configured backend; that backend resolves the
  default personal SaaS context or returns the settings for another authorized
  endpoint/deployment.
- `REQ-7703`: Navigation, layouts, routes, page sections, controls, and actions
  use server-owned capability and authorization results. Hidden UI is never
  treated as proof that an API operation is authorized.
- `REQ-7704`: Projects, technologies, landscape views, catalog objects, tables,
  and simple charts use shared resource surfaces and schemas. Context-specific
  additions compose into those surfaces without changing shared field meaning.
- `REQ-7705`: Local workflows remain complete and network-independent through
  the CLI. Web does not start, stop, or proxy a local API session.
- `REQ-7706`: Corporate-only staff, teams, ownership, assignments, audit,
  telemetry, invitations, SAML, and enterprise-operation sections render only
  when their backend capabilities and current authorization allow them.
- `REQ-7707`: Empty, unavailable, forbidden, unauthenticated, stale, loading,
  partial, and failed states are distinct. An unavailable or forbidden resource
  is never shown as an empty collection.
- `REQ-7708`: Authentication changes, backend endpoint changes, and expired
  projections cause a fresh server resolution. Web does not reuse a previous
  context from a selector, context cookie, or cached client choice.
- `REQ-7709`: Web requests use the configured backend URL and authenticated
  session. Web does not synthesize product-mode or organization headers from
  browser state.
- `REQ-7710`: `public_saas` and `self_hosted` build profiles may control their
  existing deployment-owned content features but do not select product mode or
  synthesize capabilities.
- `REQ-7711`: New and changed UI has English/Russian parity, WCAG 2.2 AA
  semantics, visible keyboard focus, reduced-motion support, and no
  document-level overflow at 360 px, 430 px, tablet, and desktop widths.
- `REQ-7712`: Browser checks verify the shared shell has no context selector or
  context navigation and that authenticated requests use backend-derived
  personal SaaS defaults.

## States and errors

Context resolution is a backend/API concern. Web renders the backend's
authentication, authorization, capability, unavailable, stale, and failure
responses without offering a mode-switch or local-session recovery control.

## Security and privacy

The backend remains authoritative for authentication, endpoint selection,
organization scope, capabilities, and every protected operation. Browser state
cannot override that result through a stale cookie, hidden field, hostname, or
client-supplied product mode. The browser receives no provider token, local
filesystem path, private passport bytes, or foreign organization data.

## Compatibility and migration

Keep the versioned context and capability API contracts for CLI and backend
clients. Remove the Web context-selection route, local-session bridge, and
context shell. Old Web context cookies are ignored by request transport. Public
catalog and authenticated owner routes retain their existing URLs; `/workspace`
was only a context dashboard and is removed rather than preserved as a second
context model.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-7701` | Route and bundle inventories find one Web application and no local-mode Web shell. |
| `REQ-7702` | Browser checks find no context selector; API tests resolve authenticated personal context without a selection header. |
| `REQ-7703` | Capability fixtures drive visibility while direct forged requests are rejected by API tests. |
| `REQ-7704` | Shared resource routes continue to pass their existing human/machine parity tests. |
| `REQ-7705` | CLI/local API tests pass without any Web route starting a local session. |
| `REQ-7706` | Corporate sections appear only for server-granted capabilities. |
| `REQ-7707` | Existing API and page tests distinguish unavailable, forbidden, unauthenticated, stale, and empty states. |
| `REQ-7708` | Transport tests prove stale context cookies cannot pin a Web request to an old context. |
| `REQ-7709` | Request tests show the configured backend URL and session credentials, with no client-selected context headers. |
| `REQ-7710` | Both Web build profiles produce the same authorization verdict for identical backend responses. |
| `REQ-7711` | Existing RU/EN, axe, keyboard, reduced-motion, and responsive browser checks pass. |
| `REQ-7712` | Shell browser checks find no context selector, context navigation, or `Context unavailable` banner. |
