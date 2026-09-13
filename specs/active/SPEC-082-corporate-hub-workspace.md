---
description: "SPEC-082: Corporate Hub directories, relationship editing, and catalog assignments."
last_verified: "2026-09-13"
---

# SPEC-082: Corporate Hub workspace

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

- `REQ-8201`: Corporate navigation preserves Catalog, documentation in the footer,
  theme, locale, and the complete account drawer. Articles and regional services
  are absent from corporate header/footer. Hub groups Overview, Organization,
  and Landscape; Organization groups employees, projects, teams, and Admins.
- `REQ-8202`: Employees, projects, teams, technologies, and technology categories
  have separate directories and linked detail pages. Viewing precedes editing.
  Search, empty/error/loading states, keyboard access, mobile layouts, and stable
  parent navigation preserve the directory context.
- `REQ-8203`: Relationship forms select authorized objects by name. Project/team,
  project/technology, technology/team, and employee assignments use the canonical
  SPEC-079/081 relations and expose reverse links. User forms never request IDs,
  revisions, evidence kinds, receipt keys, or canonical state. Manual technology
  selection defaults to confirmed use; optional version/context remain available.
- `REQ-8204`: Exact catalog setup/component versions can be assigned directly to
  an employee, team, or project. Team-derived assignments are identified separately
  from direct assignments. Assignment never installs or updates a harness and
  never manufactures an authorization grant or verification status.
- `REQ-8205`: Administration, role/access management, service accounts, repository
  policy, and audit journal are separate from ordinary directories. Audit presents
  readable actors/actions with optional technical details.
- `REQ-8206`: Each page loads only its authorized data. Related object labels and
  counts are server-filtered; denied reads never become empty records. Mutation
  revisions and idempotency remain mechanically enforced and hidden from users.
- `REQ-8207`: Employees can be linked to technologies as competences, and exact
  catalog component versions can be linked to technologies. Both sides expose
  readable named links and authorized add/remove actions without changing grants.
- `REQ-8208`: Organization details can be edited, and employees, projects, teams,
  technologies, and categories support creation, viewing, editing, and retained
  removal or suspension appropriate to their canonical lifecycle. Employee name
  editing is independent of role/access administration.

## States and errors

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
request. Canonical entity states and transitions remain owned by SPEC-079/080/081.

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
| `REQ-8201` | Corporate feature-profile and browser navigation assertions preserve Catalog, footer Docs, theme/locale and every profile-drawer action while excluding Articles/Regional services. |
| `REQ-8202` | Route inventory and desktop/mobile browser scenarios cover each directory/detail, search/status pagination, named links, keyboard access, and Back with preserved URL filters. |
| `REQ-8203` | Mobile flow creates three employees and one team lead, links team/project/technology, and verifies forward/reverse pages; mutation tests reject stale revisions while exposing no technical inputs. |
| `REQ-8204` | Authenticated PostgreSQL tests cover direct employee/team/project setup/component writes, exact versions, replay, retirement/reactivation, tenant denial and team-derived reads; before/after grants and harness state are unchanged. |
| `REQ-8205` | Administrator browser scenarios reach distinct access/service-account/settings/audit screens; ordinary directories contain no policy or audit forms; restricted users cannot open administrative data. |
| `REQ-8206` | Loader request assertions exclude unrelated administrative/activity collections; endpoint tests filter related names/counts by current access and distinguish denial from empty; retries preserve effect keys. |
| `REQ-8207` | HTTP and browser tests add/remove employee competences and technology/component links from either side, preserve exact versions, and reject cross-tenant or unreadable subjects. |
| `REQ-8208` | CRUD browser/API matrix renames organization and employee, edits each directory entity, removes or archives it without losing retained links, and keeps member profile edits separate from access changes. |

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
