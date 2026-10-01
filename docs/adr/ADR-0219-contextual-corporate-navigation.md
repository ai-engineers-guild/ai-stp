---
description: "Shared contextual Human navigation for SaaS and Corporate, with server-owned availability."
last_verified: "2026-09-30"
---

# ADR-0219: Contextual navigation for SaaS and Corporate

Status: accepted.

## Context

The first corporate rail was mounted inside `corporate/layout.tsx`. It rendered
a flat list and a mobile dialog, but had no desktop collapse control or disclosure
groups. The global Human shell still owned horizontal header navigation and a
large corporate footer. The user's 2026-09-30 correction explicitly extends the
sidebar to every Human section in both feature profiles. This replaces the earlier
Corporate-only scope; screenshot data and example permission names remain
illustrative, not authorization policy.

## Options

1. Patch each page or retain header navigation alongside the rail. This leaves
   multiple owners and different controls across sections.
2. Extend the existing rail into one shell-level component, using the existing
   route inventories, Button, Dialog, Icon registry, and semantic theme tokens.
3. Introduce another router or navigation service. No domain need requires it.

## Decision

Choose option 2. `ContextRail` mounts once in `AppShell`, outside the corporate
page layout. The Human header owns locale, theme, account and keyboard utilities;
section destinations live in the sidebar. SaaS uses `siteNavigation` with
personal destinations excluded; the account popup owns account navigation. Corporate
uses `CORPORATE_NAV_PAGES` and the server's allowed page IDs. Corporate shared
account routes retain `corporateHref` rewriting. The same inventory names the
Machine destinations, while Machine remains its separate server document under
ADR-0076 and has no Human sidebar.

The Human app bar spans the viewport. The shared rail starts directly below it;
the desktop collapse control lives in the app bar beside the brand. The page
workspace occupies the remaining row, and the profile-aware footer spans the
viewport beneath the workspace and rail. This keeps one global navigation frame
across SaaS and Corporate without repeating the brand in a second sidebar header.

The URL owns the active destination after direct entry, reload and browser
Back/Forward. Corporate Catalog has one owner. Organization and Landscape have
separate overview links and disclosure buttons. Administration replaces the
normal rail with People & Access, Reference Data, Security, Organization and
Audit groups. Empty groups disappear. The active group opens when the route
changes; disclosure clicks do not navigate. Corporate Overview is redundant in
Administration. Its Main navigation button switches the rail back to Overview,
Catalog and other permitted sections without changing the content URL. This local
UI state resets on destination navigation or a route change. Administration never
uses the previously visited page as its drawer Back target; other entity-detail
Back links name their directory. Existing content Back controls
remain available.

Desktop has expanded and icon-only states. Collapsing keeps only top-level icons and does not change the route. Group
icons open keyboard-accessible flyouts for their parent and permitted children;
every root icon retains an accessible label and title. A tab's
session storage remembers only the collapsed UI preference. Disclosures are
local UI state and the URL reopens the active ancestor. On narrow screens the
same items appear in the existing Dialog with focus containment, Escape,
focus return and close on navigation, including browser Back/Forward.

Corporate protected routes already verify the session on the server. The shared
shell resolves allowed page IDs in that request and renders the rail and its
desktop control in the initial HTML. A transient context failure renders no
unverified links and the client retries; route changes revalidate through
`/api/corporate/navigation`. A 401/403 or an empty successful result clears the
rail, while a transient failure retains the last verified set. Public SaaS
shells remain session-independent. Navigation visibility is presentation; the
API reauthorizes every operation. No permissions, credentials or user records
enter preference storage.

Security is an addressable page for the existing email-domain policy and service
principals. The domain form is extracted from the invitations component and
reuses the same action, revision and idempotency handling. Employee access gets
an index reusing the member table and its links to individual access details.
These entries do not add an SSO configuration UI, notification system or policy
model absent from the implementation.

## Consequences

- Remove the route menu from `SiteHeader` and the nested rail from Corporate
  layout; the sidebar cannot be duplicated by a page.
- Preserve the normal profile-aware, full-width footer, including brand, summary,
  link columns, documentation and `llms.txt`. Do not compact it as part of navigation.
- `AI_STP_CORPORATE_CONTEXT_NAV` no longer selects Human navigation. The shared
  sidebar is the Human shell in both profiles.
- Preserve canonical URLs, compatibility routes, locale/theme controls, account
  popup, consent and analytics mounting, and the independent Machine layout.
- Update SPEC-083, SPEC-095, route inventory and design documentation from code.
- Revert the shell changes to roll back presentation; API authorization and
  stored organization data are unaffected.

## Evidence

Component tests in `corporate-context-rail.test.tsx` exercise disclosure,
collapse/restore, semantic parent links, SaaS navigation and dialog closure.
`corporate-navigation.test.ts` covers aliases and route identity;
`corporate-shell-navigation.test.ts` covers the server availability endpoint.
The local Corporate browser inspection reproduced the flat rail before the fix.

## User correction, 2026-09-30

Remove the added Account disclosure and all its personal destinations from the
drawer in both profiles. Remove the drawer's Corporate label. The header account
popup remains the owner of personal navigation. Restore the original footer
composition; its earlier compaction was outside the requested change.

## Drawer state correction, 2026-09-30

Corporate renders no sidebar or mobile trigger on authentication pages, after
organization denial/logout, or when the server cannot verify allowed pages.
Protected routes resolve the session and allowed page IDs before the initial
HTML, so the rail does not wait for hydration or a second request to appear.
Header branding does not depend on an absent rail. Route revalidation preserves
the last verified set through transient failures, while 401/403 and an empty
successful result clear it. No permission data enters storage.
Mobile modal state is separate from desktop collapse and closes on reaching
1024 px, releasing Radix focus containment and scroll locking.

Expose the existing rail frame as `ContextSidebar` for Storybook; this extends
the incumbent component rather than introducing another sidebar system. Reuse
Button, Dialog, Icon and the installed Radix Dropdown Menu pattern. The
[shadcn Sidebar](https://ui.shadcn.com/docs/components/radix/sidebar) documents
separate desktop/mobile state and grouped menu composition;
[Radix Dialog](https://www.radix-ui.com/primitives/docs/components/dialog) owns
modal focus/Escape behavior; the
[WAI disclosure navigation example](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/examples/disclosure-navigation/)
supports separate page links and disclosure controls. These sources inform the
interaction contract; repository tokens and screenshots retain visual authority.

## Administration navigation correction, 2026-09-30

Remove the redundant Back to Overview row from the Administration rail. The
global Overview destination remains the way out of that section; entity-detail
rails keep their directory Back links. Resolve the first Corporate rail from
the server-verified session and allowed page IDs so its initial HTML and first
hydration render the same navigation without a client visibility delay.

## Administration navigation correction, 2026-10-01

The drawer Back action on every Administration route, including employee details,
returns to the main sidebar within the current page. It is a button, not a browser
history operation or an Overview redirect. The main sidebar marks Administration
active until another destination is selected. Desktop and mobile share this state;
mobile remains open while switching the destination set. URL changes reset it.
