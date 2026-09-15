---
description: "SPEC-083: Corporate Hub directories, relationship editing, and catalog assignments."
last_verified: "2026-09-13"
---

# SPEC-083: Corporate Hub workspace

## Purpose

Provide a familiar corporate workspace inside the existing ai_stp visual system.
The primary acceptance flow creates a Mobile team, assigns three employees and a
team lead, links a project, and assigns the exact Mobile Development setup version.

## Scope

Corporate Hub navigation, organization editing, employee/project/team directories
and details, technology/category CRUD, bidirectional relationships, exact catalog
assignments, and separated administration. Preserve the incumbent Catalog, footer
documentation, theme, locale, and complete profile drawer. Public SaaS navigation
continues to use its own feature profile.

## Terms

- `Direct assignment` — an exact setup/component version assigned to an employee,
  team, or project; it is operational data rather than installation or access.
- `Team-derived assignment` — a current team assignment displayed for its current
  employees with its source team identified.
- `Technology competence` — an explicit employee/technology link, independent of
  project usage and administrative authority.

## Requirements

- `REQ-8301`: Corporate navigation preserves Catalog, documentation in the footer,
  theme, locale, and the complete account drawer. Articles and regional services
  are absent from corporate header/footer. Hub groups Overview, Organization,
  and Landscape; Organization groups employees, projects, teams, and Admins.
- `REQ-8302`: Employees, projects, teams, technologies, and technology categories
  have separate directories and linked detail pages. Viewing precedes editing.
  Search, empty/error/loading states, keyboard access, mobile layouts, and stable
  parent navigation preserve the directory context.
- `REQ-8303`: Relationship forms select authorized objects by name. Project/team,
  project/technology, technology/team, and employee assignments use the canonical
  SPEC-079/082 relations and expose reverse links. User forms never request IDs,
  revisions, evidence kinds, receipt keys, or canonical state. Manual technology
  selection defaults to confirmed use; optional version/context remain available.
- `REQ-8304`: Exact catalog setup/component versions can be assigned directly to
  an employee, team, or project. Team-derived assignments are identified separately
  from direct assignments. Assignment never installs or updates a harness and
  never manufactures an authorization grant or verification status.
- `REQ-8305`: Administration, role/access management, service accounts, repository
  policy, and audit journal are separate from ordinary directories. Audit presents
  readable actors/actions with optional technical details.
- `REQ-8306`: Each page loads only its authorized data. Related object labels and
  counts are server-filtered; denied reads never become empty records. Mutation
  revisions and idempotency remain mechanically enforced and hidden from users.
- `REQ-8307`: Employees can be linked to technologies as competences, and exact
  catalog component versions can be linked to technologies. Both sides expose
  readable named links and authorized add/remove actions without changing grants.
- `REQ-8308`: Organization details can be edited, and employees, projects, teams,
  technologies, and categories support creation, viewing, editing, and retained
  removal or suspension appropriate to their canonical lifecycle. Employee name
  editing is independent of role/access administration.

## Corporate workspace presentation and editing extension

The September 13 Corporate Hub redesign brief extends the requirements above.
It preserves the incumbent Catalog card/list and two-column detail composition,
tokens, typography, locale controls, theme controls, and account drawer. It does
not redesign administration or Technology Landscape. Dashboard is an empty route.

- `REQ-8209`: Local context has no website deployment. Personal SaaS retains its
  existing routes and navigation. The corporate build excludes Articles, Regional
  Services, Company, and Legal pages from its route/build surface, not merely from
  navigation. Corporate routes use `/corporate/`; Overview is
  `/corporate/overview`. The corporate account entry button is removed and an
  orange Corporate Hub badge immediately precedes the locale control. Header
  destinations are Overview, Catalog, Organization, Landscape, Dashboard, and
  For Admins; the last destination requires server-authorized administration
  capabilities. A Corporate Hub footer group links the four workspace destinations.
- `REQ-8210`: Overview shows the organization name and quick-navigation cards for
  teams, projects, employees, and technologies, with deduplicated counts from the
  authorized graph and directory relationships.
  Its expandable DAG/WBS projection
  displays project/team/employee relationships, team leads, and exact catalog
  assignments at each node. Shared teams and employees may appear under multiple
  parents without manufacturing additional membership records. Expansion-depth
  controls reach employees; filters support multiple selections. Team-derived
  projects are a labeled projection distinct from explicit employee/project links.
- `REQ-8211`: Team, project, technology, and employee directories share Catalog
  search, filter, full-width list, and two-column card composition. Team filters
  include leads, technologies, and related teams; project filters include teams
  and technologies; technology filters include projects, teams, and categories;
  employee filters include projects, teams, technologies, and whether the employee
  leads a team. Filter semantics and related-team derivation must be explicit in
  the generated machine contract; unreadable objects never affect visible counts.
  Cards display team leads, project owner team, technology owner employee, or
  employee identity in the author position respectively. Tags display team
  technologies, project technologies, technology projects, or employee teams.
  Team action-menu placeholders are permitted; directory data is never fixture data.
  Directory cards use the Catalog's compact typography, spacing and outlined
  reference chips. They do not label teams, projects, employees or technologies
  as active. Directory filter controls reuse the Catalog's responsive dialog,
  focus handling, labeled two-column fields and Reset/Apply footer. Selection
  changes remain a draft until Apply; dismissal discards the draft. Name sorting
  supports ascending and descending order rather than a business status sort.
- `REQ-8212`: Shared two-column detail composition shows Markdown description,
  links, catalog assignments, and named related objects. Team details show
  employees/projects; project details show technologies/teams and the owner team;
  technology details show owner and reverse relations; employee details show their
  profile, teams, team-derived projects, and authored catalog components. Catalog
  authorship and designated ownership remain independent concepts.
- `REQ-8213`: Add designated technology and catalog-object ownership independently
  of authorship and competence. Administrators can edit project/team/technology
  presentation. Team leads can edit team presentation, owner-team projects, and
  other employee profiles. The brief's broader team-lead editing authority applies
  to presentation editing across the organization, not role/binding administration,
  visibility, publication, installation, or security policy. Technology owners can
  edit their technology presentation. Enforce these authorities on endpoints, not
  only navigation, and keep tenant and revision checks mandatory.
- `REQ-8214`: Shared presentation editors support Markdown description, replacement
  of the default avatar with an uploaded avatar, media uploads, and links. Corporate
  presentation and media remain tenant-scoped; public-description editing does not
  publish private organization content to the personal SaaS profile. Reuse existing
  profile controls and storage mechanisms where their authorization fits. Validate
  MIME type, size, links, and same-tenant media references mechanically. A failed
  upload/write preserves the draft; unused uploads have an explicit cleanup path.
- `REQ-8215`: Add server-side authorized directory and Overview projections rather
  than fetching unrestricted collections and filtering in the browser. Preserve
  existing typed stable identities, including the historical `operation_` team
  namespace; do not replace IDs with a second UUID scheme. Additive migrations
  precede contract/API/Web rollout and retain old data on application rollback.

The extension is accepted only after route/build-profile assertions, PostgreSQL
tenant/RBAC/media tests, generated-contract checks, and desktop/mobile browser
flows demonstrate all of the above. Browser coverage includes list/card switching,
multiple filters, expansion depth, owner/lead edits, another employee's profile,
media upload, named reverse navigation, denial recovery, and unchanged personal
SaaS navigation. A green narrow directory test does not prove the entire extension.

## States and errors

`GET /v1/corporate/organizations/{organization_id}/directory` initially serves
`resource=teams|projects`. It returns named cards, complete readable facets and
filtered total; query, lead_ids, team_ids and technology_ids use OR within
each selected dimension and AND across dimensions. Authorization precedes facets,
filters, sorting and offset/limit pagination. Team team_ids matches other teams
sharing a readable current project. Project team_ids matches its related teams.
Team technology tags combine current technology responsibility and usage of its
readable current projects. Technology names require technology read and canonical
relation read/list permissions. Archived roots retain identity/revision but do not
manufacture active related links. No directory load fetches catalog assignments.
This incremental endpoint does not replace employee/technology directory work.
Directory item models and responses have no business status field; the directory
query rejects the removed `state` filter. Archive retention and membership access
controls remain separate domain operations, not an active/inactive directory state.

Public-only route sources use build-gated Next page extensions: `content.tsx`
and `content.ts` for editorial pages/layout/feed, `saas.tsx` for contact/legal,
and `regional.tsx` for services/countries. Feature extensions require their
compiled feature; regional extensions are excluded in corporate builds while
preserving the existing noncorporate packaged surface. Disabled
routes therefore have no compiled page modules; middleware remains defense in
depth for the generic machine-document route. Personal SaaS URLs are unchanged.
Corporate profile overrides cannot reenable editorial or SaaS-public surfaces.
Corporate builds also set Next's native `skipMiddlewareUrlNormalize` flag so
excluded machine targets are not reconstructed by URL normalization; other
profiles retain the default value.
Standalone packaging reads baked feature values from required-server-files,
omits disabled editorial/legal Markdown and editorial public assets, and retains
documentation. Docker consumes this same packaged asset tree. Browser regressions
resolve user-facing sources from the packaged artifact, not the source checkout.

`GET /v1/corporate/organizations/{organization_id}/overview` returns a normalized
current graph: organization, distinct project/team/employee nodes with readable
names, team leads and exact catalog assignments, and project/team or team/employee
edges. The read requires organization access, each visible anchor's access, and
canonical relationship read/list permissions. It excludes inactive subjects and
retired links. Employee assignments additionally require the existing employee
read authority; roster visibility alone does not grant assignment access. All
assignment pages are consumed, not silently truncated to the first 128 entries.
The graph creates no state and contains no raw-ID label fallbacks. Filter/expansion
UI operates on the authorized graph and never requests hidden data.

Overview retains one organization header and four summary counts above an in-place
switch between organization hierarchy and component/setup usage. Organization rows
show named links, readable descriptions, leads, roster counts, technology chips and
catalog assignments. Usage groups each stable component/setup once across versions
and deduplicates its visible usage anchors. Exact-version assignment links remain
unchanged. Descriptions and operational owners use existing directory, catalog and
ownership reads, never a new API contract. Unavailable ownership is not reported as
unassigned. Filters use incumbent searchable selectors; mobile filters use Sheet.
Search, selection, sort and expansion affect only the read projection; clear is
visible only with active filters. Shared branches retain their canonical identity.
Dense desktop rows align entity details, lead and assignment statistics; mobile
rows stack without horizontal scrolling. Owning teams appear first; the initial
hierarchy expands the first team's compact three-employee preview. More employees
remain reachable through `+N`, or the Employees expansion depth.
Project leads use existing scoped lead
bindings. Team roster lead metadata is displayed only to authorized roster readers
and never substitutes for permission checks. Presentation descriptions use the
existing entity profile description, independently of membership authorization role.
Catalog descriptions and ownership are optional enrichment reads; a transient
catalog or rate-limit failure must leave the authorized organization graph
renderable with its available names and assignments.
The explicit development-only Twinby fixture loader preserves existing accounts,
memberships and assignments, adds canonical project/team relationships, classified
technologies and experimental catalog examples, and refuses changed target revisions.

The audit journal has a dedicated `/corporate/organization/admins/audit` page.
It requires `audit.list`; actor names are resolved only from an authorized member
directory under `member.list`. Display localized actions, outcomes, dates, and
named employee links, not target table names, raw identifiers, or arbitrary audit
payloads. Unknown action kinds retain a neutral event label. Employee filtering
uses the existing `actor_account_id` query; changing the filter resets pagination.
Earlier-event navigation retains the filter and passes the complete timestamp/ID
cursor returned by the API. Invalid or incomplete cursors are not sent downstream.
The administration landing page links to the journal without loading audit events.

Directories distinguish loading, empty, filtered-empty, data, denied, and failed
reads. A denied read is not an empty directory. Missing or unreadable related
objects never fall back to raw IDs. Forms preserve drafts after failed writes;
stale revisions produce a conflict with reload/retry recovery. Repeating an
uncertain effect uses the same idempotency key; changing the effect uses a new key.
Retired links remain available for hidden revision handling during reactivation.
Repository activity is an administrative projection, not a required project-detail
request. Canonical entity states and transitions remain owned by SPEC-079/081/082.

## Security and privacy

Authenticate before protected reads; authorize the anchor and every related object
in the same organization. Navigation filtering does not replace endpoint checks.
Exact catalog versions must remain readable and published at mutation and replay
time. Assignment writes do not change grants, harness state, or verification.
Service credentials and audit metadata remain in authorized administrative views;
secrets never enter directory labels, ordinary forms, or audit exports. Preserve
tenant constraints, current authorization revisions, and audited mutation receipts.

## Compatibility and migration

Employee competences use one retained relation per organization/account/technology.
States are `current` and `retired`; revision starts at 1 and increases on mutation.
Creation expects revision 0; reactivation uses the retained revision. Writes require
`member.manage` in the organization and readable same-tenant employee/technology
anchors, current authorization revision, and durable idempotency. Reads require
access to their anchor and filter every related object by current authorization.
No competence operation changes role bindings, grants, or project usage. User
forms select names and never request evidence or proficiency scoring.

Employee display names belong to organization memberships. `PATCH
/v1/corporate/organizations/{organization_id}/members/{account_id}/profile`
accepts a nonblank display name, exact member revision, current authorization
revision, and idempotency key under `member.update`. It changes only the tenant
name and member revision, retaining roles, bindings, policy revision, and global
account profile. Migration copies existing account names into memberships; legacy
null names retain the account-name fallback until a tenant name is supplied.

Preserve existing corporate identities and detail URLs. Existing account menu and
catalog behavior remain unchanged. Employee/team and employee/project memberships
remain independent; do not claim project-specific team membership from their
intersection. Extend contracts before introducing catalog assignment persistence.
Roll out additive migrations and generated contracts before API and Web changes.
Application rollback disables new operations while retaining existing identities,
assignments, receipts, and audit history; deployment does not drop database volumes.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-8301` | Corporate feature-profile and browser navigation assertions preserve Catalog, footer Docs, theme/locale and every profile-drawer action while excluding Articles/Regional services. |
| `REQ-8302` | Route inventory and desktop/mobile browser scenarios cover each directory/detail, search/status pagination, named links, keyboard access, and Back with preserved URL filters. |
| `REQ-8303` | Mobile flow creates three employees and one team lead, links team/project/technology, and verifies forward/reverse pages; mutation tests reject stale revisions while exposing no technical inputs. |
| `REQ-8304` | Authenticated PostgreSQL tests cover direct employee/team/project setup/component writes, exact versions, replay, retirement/reactivation, tenant denial and team-derived reads; before/after grants and harness state are unchanged. |
| `REQ-8305` | Administrator browser scenarios reach distinct access/service-account/settings/audit screens; ordinary directories contain no policy or audit forms; restricted users cannot open administrative data. |
| `REQ-8306` | Loader request assertions exclude unrelated administrative/activity collections; endpoint tests filter related names/counts by current access and distinguish denial from empty; retries preserve effect keys. |
| `REQ-8307` | HTTP and browser tests add/remove employee competences and technology/component links from either side, preserve exact versions, and reject cross-tenant or unreadable subjects. |
| `REQ-8308` | CRUD browser/API matrix renames organization and employee, edits each directory entity, removes or archives it without losing retained links, and keeps member profile edits separate from access changes. |

Catalog assignment reads default to current direct and current team-derived
assignments. `include_retired=true` additionally returns readable direct history
for hidden revision handling when reassigning the same exact version. Retired
team assignments never propagate to employees. Ordinary UI lists hide retired
rows and load all pages needed to resolve the selected assignment revision.

Employee project memberships are read through `GET
/v1/corporate/organizations/{organization_id}/members/{account_id}/projects`.
Project rosters are read through `GET
/v1/corporate/organizations/{organization_id}/projects/{project_id}/members`.
These reads require access to the subject and its related directory; return only
explicit memberships in the same tenant, never team/project intersections.

Acceptance requires browser tests covering the complete Mobile Development flow, reverse navigation,
directory return context, permission denial, mutation conflicts, archive behavior,
and desktop/mobile rendering. Contract and tenant tests cover catalog assignments.
Regenerate affected contracts and documentation, run affected repository checks,
then verify the same browser flow against the Docker deployment.
