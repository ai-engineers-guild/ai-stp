---
description: "SPEC-095: Shared contextual Human sidebar for SaaS and Corporate."
last_verified: "2026-10-01"
---

# SPEC-095: Shared contextual navigation

## Purpose

Human pages share one sidebar in both `public_saas` and `corporate_hub`.
Corporate protected routes render it after the server verifies the session and
organization navigation; authentication pages have no drawer or trigger. Users
can collapse it and disclose sections. ADR-0219
owns the shell architecture. This specification describes the implemented UI;
API permissions, role definitions and organization data remain with their owners.

## Scope

All Human routes in both web feature profiles. Existing API authority and domain
models are unchanged. Machine keeps its separate layout and paired inventory.

## Terms

A page is an addressable destination. A disclosure group reveals page links
without navigating. A context replaces the sidebar's destination set. Collapsed
means the desktop icon rail; closed means the narrow-screen dialog is dismissed.

## Requirements

- `REQ-9501`: `AppShell` mounts one `ContextRail`; the Human app bar spans the
  viewport, and the rail starts below it. The desktop collapse control is in the
  app bar beside the brand. The header contains no second route menu. Corporate
  layout does not mount another rail.
- `REQ-9502`: Corporate page identity resolves by longest segment-aware route
  match, including locale, aliases and detail paths. Query/hash do not create
  another active page. Corporate Catalog has one active owner.
- `REQ-9503`: Organization and Landscape overview links are separate from their
  disclosure buttons. Administration has People & Access, Reference Data,
  Security, Organization and Audit disclosures, filtered by server page IDs.
  Disclosure buttons expose `aria-expanded` and `aria-controls`, and never navigate.
- `REQ-9504`: The active ancestor opens on route entry. Desktop can toggle from
  the app bar between an expanded sidebar and an icon rail. The icon rail shows top-level entries
  only, with an active-descendant marker. A grouped entry opens a Radix flyout
  containing the parent destination and permitted children; arrow keys, Enter
  and Escape retain keyboard access and focus return. Accessible labels and
  titles identify each root icon. Session storage remembers only collapse state;
  unavailable storage must not break navigation.
- `REQ-9505`: Administration has no redundant Back to Overview row; a Main navigation button restores the primary sidebar without changing the
  content URL. All Administration details use that same action. The root sidebar
  marks Administration active. Navigation or a route change resets the override.
  An Administration route outside the verified page IDs renders the permitted
  root destinations with no active item, so page-level denial cannot strand the
  user in an empty navigation context.
  Other corporate entity details retain their directory Back link. Existing content Back controls continue to preserve
  their own history/fallback contract.
- `REQ-9506`: Below `lg`, the same destinations appear in the shared Dialog. It
  contains focus, closes on Escape and link navigation, returns focus to its
  trigger, and does not reopen during browser Back/Forward. Reaching the 1024 px
  desktop breakpoint closes the modal, releases focus containment and body
  locking, and preserves the independent desktop collapse preference.
- `REQ-9507`: Public SaaS HTML remains session-independent. A protected Corporate
  route resolves the verified session and allowed page IDs on the server, so its
  initial HTML and first hydration contain the rail and desktop control without
  a client visibility wait. Signed-out, initially unknown, organization-denied
  and authentication-page states render neither drawer nor mobile trigger; the
  header brand remains visible. Verified page IDs stay in memory during client
  route revalidation rather than being bound to the previous pathname.
  Network/503 failures retain that last verified set; logout, HTTP 401/403 and an
  empty successful response remove it. Aborted responses cannot replace newer
  navigation. The backend authorizes every request.
- `REQ-9508`: SaaS public section destinations use the same sidebar. The drawer
  excludes Account and its personal destinations and has no Corporate label.
  Personal navigation remains in the header account popup. Preserve the normal
  profile-aware, full-width footer with its brand, summary and destination columns.
  Locale, theme, account popup, keyboard utilities, consent and analytics remain
  mounted. Corporate shared pages use existing `corporateHref` rewriting.
- `REQ-9509`: Security owns the existing email-domain policy and service-principal
  controls. Invitations do not embed the domain-policy form. Employee access
  has an index with links to the existing individual access page.
- `REQ-9510`: Human and Machine route inventories both include the new Security
  and Employee access index routes. Machine retains its independent document
  layout and does not render the Human sidebar.

## States and errors

Desktop is expanded or collapsed. The mobile dialog is open or closed. The
current URL opens its active disclosure ancestor. Initial unavailable Corporate
navigation is absent; revalidation keeps the verified set instead of replacing
it with an Overview-only fallback. The target page owns authentication, denied,
empty and API error rendering. The first client render matches static HTML even
when session storage contains a collapsed preference. Storage failure
leaves collapse working for the current mount.

## Security and privacy

Server page IDs control menu visibility, and API checks still control access.
The shell remains cookie-independent before hydration. Preference storage holds
only the collapse boolean, never permissions, tokens or membership records.

## Compatibility and migration

Canonical URLs and aliases are preserved. Security and Employee access index
are additive routes paired with Machine. Domain policy and service principals
move into Security. The corporate-only presentation gate no longer selects a
Human layout; rollback restores prior shell components without deleting data.

## Acceptance criteria

| Requirement | Executable oracle |
| --- | --- |
| `REQ-9501` | Shell component mount source test and browser assert one Human sidebar and no header route tabs. |
| `REQ-9502` | Corporate navigation route inventory tests normalize locale, aliases and details with one active destination. |
| `REQ-9503` | ContextRail component test activates disclosure independently of the overview link and filters allowed IDs. |
| `REQ-9504` | Component collapse/restore test asserts root-only icons, keyboard flyouts, labels and session preference; browser reload verifies persistence. |
| `REQ-9505` | Component and browser tests assert the Administration Main navigation button preserves the URL and opens root destinations, including from details; other details retain directory Back links. |
| `REQ-9506` | Dialog component tests assert Escape/focus return, navigation closure and no reopen on Back/Forward; 360/768/1023/1024 px browser checks verify fit and modal cleanup on resize. |
| `REQ-9507` | SSR hydration and navigation endpoint tests cover initial allowed-page HTML, anonymous/non-member absence, revalidation, rejection, logout and localized entry. |
| `REQ-9508` | Sidebar tests reject personal links in both profiles; context-free-shell browser tests verify full footer, header account control and mobile drawer; i18n and consent/analytics suites preserve utilities. |
| `REQ-9509` | Corporate People & Access browser scenarios open both new routes and find domain/service-principal or member access controls. |
| `REQ-9510` | Projection inventory parity suite covers the additive Human/Machine destinations. |

- `apps/web/tests/unit/corporate-context-rail.test.tsx`: interactions, active
  destination, semantic parent, SaaS and mobile focus/closure.
- `apps/web/tests/unit/corporate-navigation.test.ts`: route inventory and aliases.
- `apps/web/tests/unit/corporate-shell-navigation.test.ts`: server availability
  and unauthenticated behavior.
- `apps/web/tests/e2e/corporate-people-access.spec.ts`: addressable administration
  pages, including Employee access and Security.
- `apps/web/tests/component/context-sidebar-hydration.test.tsx`: actual server
  markup hydration with existing client/session preferences.
- `apps/web/tests/e2e/context-sidebar.spec.ts`: authentication, root-only icons,
  keyboard flyouts, reload, resize, Back/Forward, logout, axe and Storybook scenarios.
- `apps/web/src/stories/UI Kit/Layouts/ContextSidebar.stories.tsx`: expanded,
  collapsed, Administration, dark, detail, restricted, long-label, short-desktop,
  mobile, signed-out, initial loading/unavailable and organization-denied views.
- Projection inventory parity, i18n parity, static-shell and account-popup suites
  remain part of `just web-check`.

## Limits

Screenshots prescribe structure and interaction, not sample counts, roles,
permission names or absent backend capabilities. This slice does not implement
SSO settings or redesign the role/access content tables. Collapsing stores no
permission or account data. The old corporate-only Human navigation gate is no
longer a switch between two layouts.
