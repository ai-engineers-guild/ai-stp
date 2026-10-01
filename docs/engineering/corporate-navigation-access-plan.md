---
description: "Evidence, design comparison, dependency order, and task reconciliation for corporate navigation and People and Access."
last_verified: "2026-09-30"
---

# Corporate navigation and People & Access plan

## Status and authority

Implementation is authorized. ADR-0219 is accepted and SPEC-095 describes the
shared sidebar from code; ADR-0220–0221 and SPEC-096–097 retain their existing
status. The 2026-09-30 correction expands navigation to both Human feature
profiles. `implementation-roadmap.md` remains the execution-order owner.

### Navigation repair acceptance

The first NA-04 implementation was incomplete: its Corporate-only nested rail
was flat, had no desktop collapse state, and left SaaS navigation in the header.
The repair extends that rail into `ContextRail` in the shared `AppShell`, removes
the second header/nested navigation, adds semantic Back, groups, icon collapse,
and the shared mobile dialog. Security now owns the existing domain policy and
service principals; Employee access has a real index. This uses existing kit
controls and registered icons. The policy form is extracted for its dedicated
page; no parallel form or new UI dependency is introduced.

Acceptance covers direct entry, reload, context changes, browser Back/Forward,
collapse/restore, independent disclosure controls, keyboard/Escape/focus return,
360 px and desktop, both profiles and locales. API authority remains unchanged.
The local checkout contains prior unfinished implementation work; its status is
not inferred from the screenshots. Full gate results must be recorded from this
checkout after the repair; older green evidence does not count.

Implementation progress: `NA-01`–`NA-03` shipped (binding `origin`/`coverage`
provenance, direct scoped permission grants, delegation-bound mutations,
last-effective-superadmin guard, `/members/{id}/access` explanation with exact
source records, corporate-owned private `AccessGrant` context). `NA-04` shipped
behind `AI_STP_CORPORATE_CONTEXT_NAV` (default off): one manifest drives the
sticky rail, the narrow-screen dialog, and `/api/corporate/navigation`. This
corporate-only gate has been superseded by the shared shell repair above. `NA-05`
shipped: `/corporate/organization/admins` is now URL-backed Members &
Invitations tabs; `/corporate/organization/admins/access` is the searchable
Access model (entities and role-matrix tabs plus effective decisions);
`/corporate/organization/admins/roles` lists system/custom roles with
inherited permissions and scoped assignments;
`/corporate/organization/admins/employees/{accountId}` explains one member's
effective decisions, bindings, direct grants, and private catalog grants at a
selected scope. Service principals moved to Security; domain policy is removed from Invitations. `NA-07` (spec rewrite)
and `NA-06` (`#544` migration) remain open.

The attached Russian target brief is input evidence, not a repository rule.
Its original review base was `dev` at `0362180d`; the initial planning checkout
was `3eb4e36e` on an OIDC work branch with unrelated changes. The navigation
repair is now local on `fix/shared-context-navigation`. Each risk R1–R8 must be reproduced against
the implementation branch before it is called fixed. The seven images show
target layout and task flow, not authoritative sample data, counts, actions,
role policy, routes, or security behavior.

## Initial live UI and source audit

Before implementation, the in-app browser alone opened the SaaS profile and redirected a corporate
admin URL to login. A signed-in Chrome profile on the same `:3000` build then
provided the actual Corporate Hub baseline. The `:3001` listener is no longer
needed. This audit inspected the catalog, `/corporate/organization/admins`,
`/corporate/organization/admins/access`, and `/corporate/roles/lead` at a
desktop viewport, including the admin page's lower sections and an expanded
permission group. Mobile, light theme, and mutation submissions were not
tested. The observed layout and incumbent source together show:

| Concern | Incumbent evidence | Target correction |
| --- | --- | --- |
| Navigation ownership | `site-header.tsx` renders primary header links; `corporate-hub-navigation.tsx` renders secondary tabs and uses route regex; `projection/navigation.ts` owns another active-path switch. | One contextual rail, one route owner per URL, separate group and page semantics. |
| Permission hint | `/api/corporate/navigation` returns one `administration` boolean. | Page/create availability projection backed by current server decisions; failure closes admin menu. |
| Content width | Shared `AppShell` uses `max-w-6xl` and a full-width sticky header. | Corporate workspace needs a rail/content composition; public shell remains static and unchanged. |
| Corporate catalog | SPEC-086 and code make `/corporate/catalog` canonical; current active checks also place it under Landscape. | One Catalog nav item; Landscape does not own the same active route. |
| Access model | `corporate_authorization.py` propagates on role-name `superadmin`; permissions and membership paths have source-specific behavior. | Explicit coverage, provenance and action-specific explanation before editable matrices. |
| People pages | Existing `CorporateMembersPanel`, `CorporateAccessPanel`, admins routes and `/corporate/employees` already own data and controls. | Compose four focused pages from these owners; no second employee identity or CRUD. |

### Initially observed Administration defects and target behavior

| Priority | Live observation | Target from screenshots and brief | Acceptance signal |
| --- | --- | --- | --- |
| P1 | `For Admins` is a long page: a full 25-member list appears before invitation, domain policy, project/team/role lists, create forms, assignments and service-principal controls. The first viewport exposes only a few member rows. | Administration is a context, not a dashboard of every form. Put People & Access in the rail and keep Members/Invitations as local tabs. | At desktop entry, title, local task, search/filter and relevant primary action are visible without traversing another domain's data; unrelated forms are absent from the page DOM. |
| P1 | Header holds Overview, Catalog, Organization, Landscape, Dashboard and For Admins; the admin page repeats six underlined cross-domain links. Catalog also appears as Landscape > Components. | One rail owns navigation; the utility strip remains top-right. Back to Corporate has a semantic parent. | Exactly one active item for each canonical URL; no repeated admin link strip or duplicate Catalog active owner. |
| P1 | `Access matrix` has 19 tall accordions for 99 permissions, with raw keys such as `catalog_object`, `project_team` and `telemetry_usage`. An expanded group is a role-by-permission table with `audit.export` rows. | Searchable, grouped read-only Access model with Entities & actions and Sections tabs; entity/action details explain scope, dependency and availability. | Find a named action without expanding unrelated groups; technical code remains available as secondary text; unsupported, forbidden and state-blocked are distinguishable. |
| P1 | `/corporate/roles/lead` contains a title, generic description and Copy ID/URL, Share, Report menu. It does not reveal permissions, assignments or inherited source on the page. | Role workspace has a persistent role list and selected role's Permissions, Details and Assignments; system roles are inspect/copy only. | A user can inspect a role's effective actions and scoped assignees without returning to admin or the separate matrix; only valid management actions appear. |
| P1 | The admin page mixes invite, member creation, team/project creation, assignment and service-principal creation as simultaneous inline forms. Multiple orange Create/Save/Invite controls compete. | One primary task per page; context-specific create controls and progressive disclosure. Service principals stay outside this People & Access slice. | Primary action is unambiguous at each viewport, form entry does not compete with unrelated forms, and cancellation returns to the same list state. |
| P1 | Invitation history and outstanding items appear together; accepted/revoked/expired records consume the same repeated card layout. A mail failure displays `RuntimeError: smtp transport failure...` to the user. | Outstanding invitation table first, history separately; delivery failure is a safe plain-language state with recovery. | Outstanding count matches rows; completed records appear only in history; no exception class, transport stack or raw server error is rendered. |
| P2 | The page asks for `Expires in days` and currently selects `lead` in the invitation role control, while member creation elsewhere defaults to `staff`. | Invitation TTL uses the existing server-supported field; role is required and explicitly selected; stronger role selection is delegation-checked. | Two forms cannot silently choose different default authority; client TTL choices map to the supported server bounds. |
| P2 | Member rows show a name plus `staff`/`active` badges but no search, team, email state, row action, pagination or selected detail. Green state badges repeat on every normal row. | Compact searchable directory, teams and role columns, exceptional status emphasis, selected person detail. | At 25 members the operator can find one person, inspect their team/role and open access without scanning the whole page. |

These are observed presentation and information-architecture failures. The
delegation, scope and private-grant risks remain separate server claims to
verify with tests. The live data includes demonstration accounts and error
receipts; do not copy those values into fixtures, screenshots or public docs.

### Impeccable Operate assessment

The target images improve information scent: persistent left context, precise
breadcrumb, page title, local tabs, compact filters, tables, and a selected
detail panel tell an administrator where they are and what object an action
will affect. Orange is reserved for current location and primary action;
neutral surfaces keep dense operational data readable. Members, invitations,
roles, and effective access use a shared visual vocabulary. Compared with the
observed corporate header, repeated links and long form stack, this reduces
page switching ambiguity and gives nested Administration an explicit parent.

Do not copy the screenshots literally. Their dense three-column desktop
tables need column priority or a row-detail layout at 360–430 px and 200%
zoom. Icon-only menus require accessible names. A side panel must not clip
long permission names or hide Save/Cancel. Counts must be server-authorized,
not illustrative. A read-only Access model cannot show selectable controls.
The Roles screenshot shows delete/edit controls for a system role; the target
contract instead shows read/copy. The invitation screenshot shows optional
name and editable expiration; current API/policy require different behavior.
The Employee access screenshot's Full/Extended/Standard labels are not an
authorization model. Tooltips, focus, disabled reasons, error recovery,
loading, and audit-safe preview matter more than pixel-copying mock values.

The existing design tokens, typography, Button, Badge, Input, Dialog, filters,
`Icon`, and UI selectors are the first implementation choices. Before any new
component, inventory atoms/molecules/organisms/layouts and record the concrete
gap. A `ContextSidebar` may be justified by the missing rail topology;
`NavigationProvider`, a new generic matrix engine, and one component per
mockup label are not preapproved. Keep one primary action per viewport.

## Dependency order and work packages

| ID | Work and owner | Exit evidence | Rollback |
| --- | --- | --- | --- |
| `NA-00` | Extend the observed signed-in desktop baseline to light/dark, 1440/430/360 px, Human/Machine; inventory selectors, kit and route states. | Captures plus route/AX/keyboard notes on exact checkout; record visual failures against the live Corporate Hub. | Read-only. |
| `NA-01` | Reproduce R1 delegation, R4 independent-binding removal, R6 last-admin/cycle paths; patch shared authorization paths where failing. | Negative PostgreSQL tests and audit/transaction assertions; no privilege escalation or partial writes. | Revert code without reverting retained audit. |
| `NA-02` | Add enforced descriptor inventory, explicit coverage/origin, correct explain and bounded bulk decisions. Backfill only provable rows. | Handler/descriptor coverage, single-bulk parity, legacy before/after and tenant matrix. | Disable new writers; preserve rows and old effective interpretation. |
| `NA-03` | Add direct scoped allows and delegation-safe grantable options; integrate private major-line AccessGrant through current owner context. | Forged grants, dependency closure, revoke, revision and audit tests. | Hide controls/disable writes; retain grants/audit for review. |
| `NA-04` | Repair the shared Human sidebar for SaaS and Corporate from the original rail and corporate manifest. The old corporate-only gate is superseded. | Direct URL, reload, Back/Forward, aliases, desktop collapse, independent group disclosures, mobile focus/closure and Machine parity. | Revert the shared shell change; keep route aliases and data. |
| `NA-05` | Compose Members & Invitations, Access model, Roles, Employee access from incumbent records and UI kit. | T01–T20 from target brief mapped to tests, including no-email, history, conflict, keyboard and responsive states. | Switch new page entry points off; retain API/data. |
| `NA-06` | Preview any default-role policy change as its own migration; compare affected principals/scopes before enabling. | Recorded before/after and explicit operator decision; no silent old-binding widening. | Restore previous policy version, not security fixes. |
| `NA-07` | Rewrite active specs from implemented code, update product/design/runbooks, regenerate artifacts and complete exact-SHA gates. | `just docs-check`, `just back-static`, `just back-test`, `just web-check`, then full `just check`/CI as applicable; final diff and browser review. | Revert deployment code while preserving additive data and audit. |

No phase may advertise an editable action until its endpoint enforces it.
Schema/contract changes precede Web consumers. Every protected operation uses
plan, digest, revalidated precondition, and idempotency. If an operation has
no recovery path or expands another person's access, obtain the separate
decision required by AGENTS.md at action time.

## Specification and ADR reconciliation

| Current owner | Disposition now | Implementation-time update |
| --- | --- | --- |
| ADR-0179, SPEC-079 | Keep binding/active. | Refine evaluator, scope, audit, delegation, and last-admin requirements from green tests under ADR-0220. |
| SPEC-083 | Keep active for current shell. | `REQ-8301/8309` now describe the shared sidebar under ADR-0219; retain directory/relation semantics. |
| SPEC-086 | Keep active; canonical catalog/employee routes remain valid. | Adjust navigation or route acceptance only if implementation changes observable behavior. |
| SPEC-075/076/077 | Keep active. | Check context, capability and shared UI boundaries; edit only clauses actually changed. |
| SPEC-084/085 and private-grant owner | Keep active. | Update field authority, catalog assignment and AccessGrant integration only after NA-03. |
| SPEC-095 | Active for the implemented shared sidebar. | Maintain code-backed interaction and route oracles; do not claim the whole People & Access redesign complete. |
| SPEC-096–097 | Proposed access work. | Promote verified clauses into the correct active owner; archive unused proposal clauses after implementation decision. |
| Completed corporate-core foundation plan | Archive as history. | No replay of its checklist. |
| Workspace consolidation plan/ledger | Retain until exact completion evidence is reconciled. | Archive only when every `CR-CORP-01`…`12` exit oracle is evidenced; file existence is insufficient. |

No active corporate spec is archived merely because a new layout is planned.
No accepted ADR is retroactively rewritten: add supersession wording to a new
accepted ADR and update `docs/adr/binding.md` only when the implementing
change establishes a real conflict.

## Task audit and proposed issue breakdown

The read-only GitHub inventory on 2026-09-29 lists #20 and #224 as open
corporate umbrellas, #19 as open OIDC work with an open PR, and #220 as open
SAML. None satisfies its full exit condition from this documentation-only
work; close none. Existing B2B child issues are not reopened from a stale
brief. The completed local foundation plan is archived above. Before closing
any GitHub item, verify its exact acceptance and merged SHA; an open umbrella
cannot be closed because one slice shipped.

Bounded implementation issues now exist under #224: `#541` navigation (`NA-04`),
`#542` authorization/delegation (`NA-01`–`NA-03`), `#543` pages and qualification
(`NA-05`, `NA-07`), and `#544` separate policy migration (`NA-06`). The #224
discussion links them. Each issue names its proposed spec clauses, API/data
migration, negative security tests, Web states where applicable, and an exit
oracle. Acceptance of a proposed ADR remains part of the implementing PR,
not a claim that the issue is already done. Keep #19/#220 separate from
People & Access; OIDC and SAML are not a prerequisite for local UI design.

## Verification of the navigation repair

### Authentication, state and responsive follow-up

The next observed failures were an anonymous Corporate rail, sections disappearing
on Overview, nested icons leaking into the collapsed rail, and a Webpack runtime
error. The implemented correction extends the incumbent frame as `ContextSidebar`:

- Corporate chrome stays absent until session hydration and a verified organization
  navigation response. Authentication pages and organization denial have no drawer
  or mobile trigger; the header keeps its brand.
- Verified page IDs belong to the session UI store. Route revalidation retains them
  through network/503 failures; logout, 401/403 and an empty successful response
  clear them. Aborted requests cannot publish an older result. API authorization
  remains authoritative and no permission data enters preference storage.
- Collapsed desktop shows one icon per root section. The installed Radix Dropdown
  Menu supplies grouped destinations, keyboard navigation, Escape and focus return.
  Expanded groups retain separate links and disclosures. The existing mobile Dialog
  closes on navigation and on reaching 1024 px, independently of desktop collapse.
- Thirteen Storybook scenarios exercise the same frame, including both themes,
  short and narrow viewports, long labels, restricted navigation, signed-out,
  initially unavailable and organization-denied states. Browser tests run axe after
  theme transitions complete; the addon uses manual mode to prevent concurrent axe
  executions. Existing tokens, Button, Dialog and Icon are reused without a new
  dependency or sidebar provider.

The comparison used the original screenshots, the local application and primary
references: the [shadcn Sidebar documentation](https://ui.shadcn.com/docs/components/radix/sidebar),
its [official implementation](https://raw.githubusercontent.com/shadcn-ui/ui/main/apps/v4/registry/new-york-v4/ui/sidebar.tsx),
[Radix Dialog](https://www.radix-ui.com/primitives/docs/components/dialog) and the
[WAI disclosure-navigation example](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/examples/disclosure-navigation/).
These references establish interaction patterns; the repository kit and supplied
screenshots remain the visual owners.

The `.call` screenshot came from the server Webpack module loader before React
hydration. The persistent dependency volume ran Next 15.5.25 while the checked-in
lockfile pinned 15.5.26. Installing the frozen lockfile in that volume with the
repository-pinned Bun and restarting only the web service regenerated its compile
cache and restored rendering. The image also had an older Bun runtime; future
image rebuilds must use the current pinned Dockerfile. This recovery is evidence
of restored operation, not proof of which missing module first corrupted the HMR
graph. Do not diagnose the Webpack exception as a React hydration mismatch.

For recovery after dependency changes, stop the web service, rebuild its dev image
from the current Dockerfile, synchronize the existing `web_node_modules` volume
with `bun install --frozen-lockfile`, and start web with the same Compose files.
The existing startup command regenerates only the compile cache. Keep database,
API, object-storage and account state. Revalidate localized Human and Machine
routes after recovery. Actual SSR hydration is covered separately by
`context-sidebar-hydration.test.tsx` with a saved collapse preference and an
authenticated client.

Production browser previews used local HTTPS with synthetic test certificates:
the unchanged production CSP upgrades HTTP fetches, so plain HTTP previews caused
SSL/RSC failures. The temporary TLS proxy and test-only certificate handling are
not shipped. Start the Corporate mock server fresh for a full workflow run: its
process-local editor drafts and invitations otherwise survive repeated external
test invocations. The SaaS performance oracle reads the manifest and chunks from
the exact production artifact, not the dev cache.

Observed qualification on this checkout:

| Check | Observed result |
| --- | --- |
| `just web-test` | 182 files, 841 unit/component tests passed; global and catalog coverage gates passed. |
| `just web-static` | Passed i18n, ESLint, generated-client drift, formatting and types. |
| Documentation | `just docs-check` passed earlier in this repair; final `just docs-gen` and `just docs-static` passed after recording the evidence. |
| `just web-storybook` | Passed with 13 sidebar scenarios. |
| SaaS production browser suite | 230 browser scenarios passed in both Chrome projects. The two performance cases initially lacked a local manifest; both passed after pointing the oracle at the exact native production artifact. 38 Corporate/Storybook opt-in cases were skipped in this SaaS invocation. |
| Corporate offline browser suite | 38 passed, 4 skipped across desktop/mobile: the two Storybook cases ran separately, and the two live multi-membership cases need an existing two-tenant session. Includes auth/absence, section retention, root-only collapse, flyout keyboard/focus, reload, responsive Dialog, Back/Forward, logout, full footer, People & Access, directories and profile exclusion. |
| Storybook browser suite | Both projects passed all 13 scenario assertions, keyboard/focus checks and axe scans of the visible sidebar/dialog. Light and dark settled states have no axe violations. |
| Original `localhost:3000` | Five initial shell cases passed; the cold Machine compile exceeded the 30-second test timeout. Both Machine cases passed on a bounded 120-second rerun. No `.call`, JSON corruption or HTTP 500 appeared in the subsequent server log slice. |

The full aggregate `just web-check` remains unqualified: the Windows native build
stalled earlier, and the complete self-hosted feature matrix was not run. Linux
SaaS/Corporate production builds and the checks above are individual evidence,
not a substitute claim for that aggregate. Live multi-organization acceptance and
the unrelated unfinished backend changes remain outside this qualification.
`NA-04` has local implementation and interaction evidence; `NA-01`–`NA-03`,
`NA-05`–`NA-07`, issue closure, commit, merge and release retain their own gates.
The final mobile frame is retained at
`.impeccable/review/sidebar-storybook-mobile-chromium.png`, and the root-only
desktop rail at `.impeccable/review/sidebar-root-only-chromium.png`.

### Follow-up correction and local runtime recovery

The user rejected the added Account disclosure, the drawer's Corporate label
and the compact Corporate footer. Remove personal destinations from both
drawers, keep their existing header-popup owner, label Administration Back as
Back to Overview, and restore the original profile-aware footer composition.

The local dev server returned HTTP 500 across routes because
`.next/prerender-manifest.json` contained a complete JSON document followed by
52 trailing characters. Next 15's dev static-path loader reads and rewrites
that shared file without serializing concurrent routes. The locale layout
supplied static locale params on every dev route, activating that write path.
In development the locale and documentation generators now return no static
params, so routes render on demand;
production still generates `ru` and `en`. Restarting only the web container
regenerates its build cache. Source, API state and database records are not
recovery inputs. The locale unit test exercises both environment branches;
the context-free-shell browser suite covers repeated concurrent locale routes,
the full footer and the drawer correction.

### Earlier navigation verification

The 2026-09-30 repair was verified in this working checkout, including its
pre-existing unfinished access implementation. Observed results:

- `just docs-gen`, `just docs-check`, `just web-static` and `just web-test`
  passed. The full unit/component run passed 831 tests across 181 files;
  the coverage gate and separate catalog coverage run passed.
- SaaS and Corporate production builds passed in Linux containers mounted to
  this checkout using the frozen lockfile. Storybook also built successfully.
  The aggregate `just web-check` did not complete: its Windows Next build
  stalled before compilation, and the complete feature-profile matrix was
  not rerun as one aggregate. Individual results do not close that gate.
- Selected SaaS browser scenarios covered public routes, locale/theme/account
  controls, mobile navigation and Machine layout. The first broad run had two
  failures during cold rendering; both passed on isolated reruns. Corporate
  scenarios passed for anonymous availability, Security controls and mobile
  Administration in both browser projects. The fixture's Settings denial was
  asserted without widening its permissions.
- Live signed-in browser inspection on `:3000` verified grouped Administration,
  context Back, Security, collapse persistence after reload, and mobile
  focus/Escape behavior. SaaS inspection used a separate production preview.
  The mobile pass repaired the projection dock occupying its own flex column
  and the header covering the menu trigger.

The mobile Administration capture is retained at
`.impeccable/review/people-access-offline-chromium-mobile-navigation.png`.
These results qualify the navigation repair; they do not qualify every prior
backend change or the entire role/access content redesign. No commit, merge
or release is implied by local browser success.

## Members & Invitations correction, 2026-10-01

Implementation now uses the supplied screenshot structure: breadcrumbs/title,
four statistic cards, underline tabs, compact searchable/selectable member and
invitation tables, row actions and ten-row pagination. Invitation creation and
bulk import are in the shared Dialog, with roles, teams and the API-supported
expiry. History is reached through the invitation status filter. Member creation
reuses CorporateCreateForm. Domain policy stays in Security. Response enrichment
adds corporate contact, membership join time, device activity and invitation issuer;
no OAuth contact fallback is allowed. SPEC-086 REQ-8615–8617 owns this shipped slice;
SPEC-096 remains a proposal for the remaining access-administration changes.

Rollback is to restore the prior page/panel and shared molecule variants from
Git; additive response metadata can remain. Existing records and permissions are
preserved.

The current correction removes the Administration Back to Overview row, superseding
its label in the earlier follow-up above. Server-verified navigation is rendered in
the first protected Corporate HTML; it does not wait for a client availability
request. Development locale/document generators bypass the shared static-path
manifest write, while production retains both locales. The Docker dependency
volume now matches the frozen lockfile (Next 15.5.26). Watchpack polling is enabled
for the Windows source bind so saved changes reach the running dev server.

Live Russian-page inspection also reproduced a real hydration mismatch: Alpine's
Node installation had only English ICU data, so server RelativeTimeFormat emitted
English while the browser emitted Russian. The dev image now installs
`icu-data-full` and asserts EN/RU RelativeTimeFormat support during image build.
The locale layout explicitly gives the URL locale to the message loader and
client provider. This fixes the common runtime boundary rather than replacing
each page's Intl formatter. See [Node internationalization support](https://nodejs.org/api/intl.html).
The members browser scenario checks Russian relative activity and an error-free
locale transition.

Human and Machine app bars use the same height so a projection change preserves
the main content top edge (REQ-3614). The local standalone preview names the
existing user-facing documentation directory explicitly; its changed working
directory must not be mistaken for missing product documentation.

The shared Dialog restores focus to an external opener when no DialogTrigger is
present, honors custom autofocus handlers, and uses the semantic scrim token in
both themes. The base border reset is in Tailwind's base layer so active tab and
control state colors are not overridden. Invitation team choices expand inline
instead of covering submission controls. No new UI dependency was added.

Observed qualification for this correction on this checkout:

| Check | Observed result |
| --- | --- |
| `just web-test` | 183 files, 847 unit/component tests passed; global and catalog coverage gates passed. |
| `just web-static` | Passed i18n, ESLint, generated-client drift, formatting and type checks after removing automatic temporary-build includes from tsconfig. |
| Corporate production build | Passed with an isolated native build directory and copied standalone assets. |
| SaaS production build and browser suite | Passed with an isolated native build directory; 50 browser scenarios passed and four duplicate mobile-project cases were skipped by their desktop-only guard. Covers locale transitions, mobile routes, full footer, documentation, account controls and Human/Machine alignment. |
| Corporate offline browser suite | 24 passed before the final Russian-activity assertion. The repeat passed 23 cases and caught one resource 404 in the member workflow; both member workflows passed on a fresh mock server with the Russian assertion. Coverage includes first authorized HTML, anonymous absence, EN/RU, navigation state, responsive drawer, access pages, CSV, confirmation, receipts, focus return and document overflow. Console failures now include the resource URL to diagnose recurrence. |
| `just docs-gen` / `just docs-check` | Passed document/specification/contract lint, links, generated indexes, builds and Mermaid rendering. |
| `just web-storybook` | Passed. |
| Storybook browser suite | Four tests passed across both projects, exercising 13 sidebar and 11 people administration stories, keyboard/focus, responsive layouts and axe checks. |
| Backend metadata slice | Ten focused database tests passed; `just back-static` passed before the final UI-only corrections. |

The delivered dev image is
`sha256:06de029b5453d520140a07f1a22378016375ba2b4507e29f4d481d89c7525bb2`.
Its ICU assertion passed at build time and both locales were checked in the running
container. Live `localhost:3000` Members and Access model inspection confirmed the
rail, removed Back row and no browser errors after the restart. Restoring the
prior source and rebuilding/recreating only web is the recovery path; retain
persistent API, database, account and object-storage state.

The complete aggregate `just web-check` and self-hosted feature-profile matrix
remain unqualified. This evidence does not close the remaining SPEC-096 proposal,
qualify unrelated unfinished work, or imply a remote release.
