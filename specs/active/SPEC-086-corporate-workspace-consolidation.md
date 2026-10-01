---
description: "SPEC-086: Corporate workspace identity, directory, catalog, and detail consolidation."
last_verified: "2026-09-18"
---

# SPEC-086: Corporate workspace consolidation

The canonical employee and catalog routes here remain binding. Proposed
navigation and access pages in SPEC-095–097 reuse those identities; they do
not create a second employee directory or corporate catalog.

## Purpose

Make the Corporate Hub a stable, capability-driven workspace in which each person,
catalog object, and organization entity has one canonical user-facing route and one
consistent set of directory, detail, creation, filtering, and action behaviors.

## Scope

This specification owns the consolidation of corporate employee identity and routes,
the canonical corporate catalog surface, directory pagination, entity creation flows,
shared action menus, detail composition, corporate catalog facets, technology job-title
metadata, organization-usage projections, and production-like Web acceptance.

SPEC-079 remains authoritative for authorization, tenant isolation, lifecycle, audit,
and idempotency. SPEC-081 and SPEC-082 remain authoritative for technology metadata and
canonical relations. SPEC-084 remains authoritative for presentation storage and edit
authority. SPEC-085 remains authoritative for catalog governance and assignments.

## Terms

- `Employee` — the corporate user-facing projection of one account's membership in an
  organization; it is not a second identity kind.
- `Job title` — organization-governed employee classification, independent of RBAC
  role, team role, competence, and presentation content.
- `Canonical corporate catalog` — `/corporate/catalog`, the only corporate setup and
  component search surface.
- `Organization usage` — an authorized projection of teams, projects, and technologies
  related to one stable setup or component through current direct or effective
  corporate relations.
- `Normal lifecycle state` — the current non-exceptional state that does not need a
  badge in ordinary directories or detail headers.

## Requirements

- `REQ-8601`: The Corporate Hub exposes people through `/corporate/employees` and
  `/corporate/employees/{account_id}`. Employee, member, and publisher views resolve to
  one account identity and one shared two-column corporate detail projection. Legacy
  `/corporate/members` routes redirect permanently while preserving a safe query string.
  Public publisher routes remain public catalog projections of the same account.
- `REQ-8602`: `/corporate/catalog` is the only corporate setup/component catalog.
  Legacy `/corporate/components` routes redirect permanently with compatible query
  translation. Corporate context extends the existing catalog query, cards, pagination,
  and object detail routes instead of introducing a second search implementation.
- `REQ-8603`: Team, project, employee, and technology directories use server pagination,
  URL-backed query, sort, filters, page, and page size. Responses return the authorized
  total and complete readable facets after authorization. Changing query, sort, or a
  filter resets the page. A directory request does not materialize every page.
- `REQ-8604`: Directory and relation cards use one authorized projection for names,
  leads, owner employees, owner teams, categories, tags, and available actions. The same
  readable object has the same relationship metadata in a root directory and every
  nested detail section. Authorization precedes enrichment, counts, and facets.
- `REQ-8605`: Add-team, add-project, and add-employee actions are exposed only through
  server capabilities and submit one revision-checked, idempotent, transactional command.
  Team creation requires a display name and may include description, one lead, employees,
  projects, and technologies. Project creation requires a display name and may include
  description, one owner team, and technologies. Employee creation requires a display
  name and at least one team and may include incumbent profile fields, one job title, and
  exact-version component assignments. A failed command creates no partial aggregate.
- `REQ-8606`: Entity cards and detail headers share one action policy. Structural edit
  follows the entity update capability; presentation edit follows the authoritative
  `can_edit` projection; readable entities expose copy ID, canonical share URL, and the
  existing report action. Like and CLI-copy actions remain exclusive to installable
  catalog objects. The API independently authorizes every mutation.
- `REQ-8607`: Normal lifecycle state is not rendered on ordinary team, project,
  employee, technology, setup, or component cards and headers. Suspended, archived,
  deprecated, merged, deleted, and other actionable exceptional states remain visible.
  Canonical lifecycle fields and transitions remain persisted and enforced.
- `REQ-8608`: Shared entity details render safe Markdown tables as bordered semantic
  tables, keep relation filters inside expanded section content, render assigned setups
  and components with the canonical one-column object card, and link stable public
  objects rather than exact-version detail routes. Exact assignment versions remain
  visible and immutable assignment facts.
- `REQ-8609`: Shared entity details use a responsive two-column frame with a wider
  desktop rail. The rail presents owner or lead identity, Context budget, Use via CLI,
  and links without empty cards. Non-installable entities show an explicit unavailable
  state in Use via CLI. Media uses one bounded keyboard-accessible carousel with hidden
  native scrollbar, finite controls, scroll snapping, a usable mobile layout, and
  reduced-motion behavior.
- `REQ-8610`: Corporate catalog filters include searchable multi-select teams, projects,
  technologies, technology categories, operational owners, and maintainers, plus direct
  or effective assignment and corporate-verification filters. Values use OR within one
  facet and AND across facets, are serialized in the canonical URL, and apply equally to
  setups and components. Public requests retain existing behavior and cannot infer
  corporate values.
- `REQ-8611`: Every organization may govern job titles. A job title has a typed stable
  `job_title_` identifier, organization, unique normalized name, optional description, revision, and
  current or retired lifecycle. One employee membership references at most one current
  job title. Administrators manage titles; employee directories and every employee
  selector can filter by job title. RBAC roles and team roles remain independent.
- `REQ-8612`: Corporate setup/component details expose an authorized Organization usage
  section containing paginated named teams, projects, and technologies with direct or
  effective source. Unreadable relations do not affect rows or totals. Direct and
  effective paths to the same subject are deduplicated without erasing provenance.
- `REQ-8613`: Organization Overview omits entity descriptions from By organization
  cards while preserving names, relationships, counts, and detail navigation. Full
  descriptions remain on detail pages.
- `REQ-8614`: The Corporate Web has no hydration mismatch, recoverable server-render
  error, or browser-console error on catalog, directory, and entity-detail acceptance
  routes. Acceptance runs against a clean production build and production server;
  long-lived development Fast Refresh is not release evidence.

## States and errors

Job titles are `current` or `retired`. A retired title remains attached for historical
reads but cannot be newly selected. Existing employees may have no job title after the
additive migration. A create command rejects an unreadable, foreign, inactive, or stale
relation before committing any row. Legacy route translation rejects unsafe or unknown
query values rather than forwarding them blindly.

Stable errors are `capability_forbidden`, `capability_stale`, `revision_conflict`,
`idempotency_conflict`, `contract_invalid`, and the existing non-enumerating access
denial. Pagination rejects invalid bounds. Corporate facet values from another tenant
are denied before search totals or facets are computed.

## Security and privacy

The server capability and available-action projections drive visibility but never
replace endpoint authorization. Enrichment, relationship totals, search facets,
organization usage, selectors, and redirects resolve the active organization before
reading protected data. Job title and employee filters reveal no foreign or unreadable
membership. Create commands, governance reads, and presentation writes retain current
revision, receipt, audit, redaction, and tenant-isolation requirements.

## Compatibility and migration

Add the job-title table and nullable membership reference before enabling title writes.
Add new projection and search fields before Web adoption. Existing clients may omit all
new fields and filters. Legacy corporate routes remain permanent redirects for one
compatibility window; application rollback restores their incumbent handlers and hides
new controls while retaining job titles, references, receipts, and audit. Schema
downgrade is a separate explicit operation.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-8601` | Route tests prove canonical employee rendering, account identity reuse, safe permanent redirects, and unchanged public publisher URLs. |
| `REQ-8602` | Route and query-contract tests prove one corporate catalog, compatible component redirects, and absence of duplicate navigation or machine routes. |
| `REQ-8603` | API and Web tests prove bounded page reads, authorized totals, URL round trips, page reset, and no all-pages loader call. |
| `REQ-8604` | Integration fixtures render identical owner, lead, category, and action projections in root and nested cards without foreign labels or counts. |
| `REQ-8605` | Role-matrix and transactional integration tests cover all three create commands, searchable relations, stale revisions, replay, and rollback after one invalid relation. |
| `REQ-8606` | Component and API tests cover administrator, lead, owner, self, staff, and anonymous action matrices; forged mutations remain denied. |
| `REQ-8607` | Rendering tests omit normal-state badges and retain every actionable exceptional lifecycle state without changing persistence transitions. |
| `REQ-8608` | Component and browser tests cover bordered Markdown tables, expanded-only filters, canonical object cards, stable links, and visible exact assignment versions. |
| `REQ-8609` | Desktop, keyboard, reduced-motion, 430 px, and 360 px browser tests prove the rail and carousel have no document-level horizontal overflow or empty card. |
| `REQ-8610` | Contract, PostgreSQL search, URL codec, and browser tests cover every corporate facet for setups and components, composition semantics, pagination, and public isolation. |
| `REQ-8611` | Migration, uniqueness, lifecycle, RBAC, API, directory, selector, and tenant-isolation tests cover job-title administration and filtering. |
| `REQ-8612` | API tests cover setup/component usage, pagination, authorization-before-count, direct/effective deduplication, and tenant isolation; browser tests cover named navigation. |
| `REQ-8613` | Overview component tests omit descriptions only in By organization cards and preserve detail descriptions. |
| `REQ-8614` | GitHub Actions builds and starts the production Web artifact and fails on hydration warnings, recoverable rendering errors, uncaught page errors, or HTTP 500 across the acceptance route matrix. |

## Members and invitations administration (2026-10-01)

This is the code-backed administration view over the existing authorized member
and invitation lists, separate from the resource directories in REQ-8603.

- `REQ-8615`: `/corporate/organization/admins` renders breadcrumbs, four summary
  counts, and URL-backed Members/Invitations tabs. Each administration table has
  name/email search, role/team/status filters, ten rows per page, selected-row CSV
  export and keyboard-accessible row actions. Query changes reset the page. The
  status column explicitly shows normal and exceptional membership states; this
  administration table is the exception to REQ-8607's ordinary entity cards.
  Empty and unavailable data remain distinguishable. A missing contact is labeled
  No email, while unknown dates/activity remain absent rather than synthesized.
- `REQ-8616`: The member list exposes nullable `contact_email`, `joined_at`, and
  `last_activity_at`. Contact comes only from the current organization's corporate
  provisioned identity; private OAuth email is never a fallback. Joined time comes
  from the membership; activity is the latest registered-device visit. Invitations
  expose nullable issuer identity for the Invited by column. Authorization and
  tenant filtering precede enrichment. The response fields are additive; no
  migration or role semantics change is required.
- `REQ-8617`: Invitations initially show unexpired pending/confirmation-pending
  records; the status filter exposes completed history. Invite member opens the
  existing focus-contained Dialog with required email and explicit role, optional
  display name and teams, and supported expiry choices of 1/3/7/14/30 days. Seven
  days is the initial expiry. Import from file opens a native click/drop file field for CSV, JSON, Markdown,
  XLSX (first sheet), or TXT, bounded to 2 MB and 500 recipients. It projects
  email/display_name columns, ignores file roles, and previews every recognized
  row in the reusable MemberImportPreview table. Invalid emails, duplicate emails
  and oversized names remain visible and are skipped. Localized help opens a
  modal with the format example and validation rules. Role/team/expiry choices
  survive invitation-mode changes. The full authorized role catalog remains
  visible: roles outside the server delegation projection are disabled with a
  localized explanation. Failed or stale delegation reads block submission with
  a distinct recovery message. The API still checks current closed permissions.
  Errors release request
  busy state independently of route refresh. Revision checks and per-effect idempotency prevent
  duplicate mutations on retry; successful receipts survive a partial failure.
  Generated bearer links appear only in the receipt dialog/export, never directory
  exports or URLs used for filtering. Revoke is confirmed in a dialog and retains
  the history row. Domain policy remains in Security.

Executable oracles: `corporate-people.test.tsx`, `member-export.test.ts`,
`test_member_directory_uses_corporate_contacts_and_nullable_activity`,
`test_corporate_invitations.py`, `corporate-people-access.spec.ts`, and
`context-sidebar.spec.ts` and `corporate-members-screenshot.spec.ts`. The CorporatePeople stories cover light/dark, empty,
read-only, mobile, invitations/unavailable, invite/error/busy and bulk input.

Role badges and team chips in member/invitation tables link to the existing role
matrix and team details. Row action menus use nonmodal Radix menus, preserving
page scrolling and keyboard focus return. Administration's drawer return action
is specified in SPEC-095. Component oracles additionally include
`corporate-members-table.test.tsx`, `member-import.test.tsx`,
`corporate-invitation-actions.test.tsx`, and `member-import-file.test.ts`.
Storybook includes independent member table and recipient preview states.
