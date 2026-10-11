---
description: "Live, ordered entity action projections shared by catalog and corporate interfaces."
last_verified: "2026-10-11"
---

# SPEC-096: Server entity actions

Owner: [ADR-0232](../../docs/adr/ADR-0232-server-entity-actions.md).

## Purpose

Keep entity menus consistent across every card, related section and detail page
using the same live authorization as backend operations.

## Scope

Catalog objects, publishers, corporate resources, access grants, invitations,
technology scans and findings. Existing operation endpoints remain authoritative.

## Terms

A subject identifies an entity. A menu is its ordered authorized projection for
one principal. An action descriptor is a presentation hint, never a credential.

## Requirements

`POST /v1/entity-actions/query` returns ordered menus for at most 256 entity
subjects. The authenticated principal comes from the session, never the request.
Responses are private and uncached. Duplicate subjects share one evaluation per
request. The generated contract owns selector fields and the response shape.

- `REQ-9601`: The API filters its ordered action registry through current
  authorization and entity state. Corporate reads establish tenant membership
  before returning entity information. Built-in roles cannot be edited or
  deleted. Retired job titles and archived taxonomy entries use restoration
  permission rather than deletion permission.
- `REQ-9602`: Corporate mutations, profile editing and menu projections share
  subject authorization. Active technology ownership contributes technology
  update authority; active team leadership contributes profile authority through
  current relationships. Operational catalog ownership requires an active
  organization and active principal. Catalog edit/delete grants use object scope.
- `REQ-9603`: A personal author can edit presentation, manage access and delete
  unpublished objects. Published versions cannot be deleted. An access recipient
  can read the granted published major line; receiving access does not confer
  editing or delegation authority. Visibility changes require a matching active
  device and an eligible published author version.
- `REQ-9604`: Every menu host uses `EntityActionItems`. Hosts supply execution
  handlers and localized labels, while the server controls membership, groups
  and order. Concurrent opens are batched; permissions are not cached between
  opens. Failed reads display an explicit retry action. Changing the subject
  discards the previous menu.
- `REQ-9605`: Mutation endpoints independently reauthorize and validate revisions,
  state and idempotency. Menus never serve as permission credentials. Received
  grants are displayed separately from grants issued by the current account.

## Acceptance criteria

API: `apps/api/src/ai_stp_api/slices/entity_actions/` and corporate
`subject_access.py`; contracts: `packages/contracts/src/ai_stp_contracts/entity_actions.py`.
Web: `entity-action-items.tsx`, `entity-action-query.ts`, existing card/detail and
administration menu hosts.

`REQ-9601`, `REQ-9602`, `REQ-9603` and `REQ-9605`:
`tests/api/platform/test_corporate_subject_rbac.py` checks ordered duplicate
projections, team-scoped denial, solo author rights, unpublished/publication
boundaries and request limits against PostgreSQL.
`REQ-9604`: `tests/component/entity-action-items.test.tsx` in `apps/web` checks server order,
absence of locally supplied unauthorized actions, reloading and explicit retry.
Existing corporate delegation, directory authorization, context matrix and direct
grant recipient suites exercise the shared authorization boundaries.

## States and errors

Menus load, succeed, or show a retry action after failure. An unauthorized entity
returns the existing authentication, permission or not-found error. Oversized
batches are validation failures. Failed mutations retain their existing errors.

## Security and privacy

Session identity and tenant authorization precede private entity reads. Generated
menu responses must not enter a public cache. Mutation endpoints recheck access
and revisions after a menu was displayed. No secrets enter action descriptors.

## Compatibility and migration

Deploy API and web contract consumers together. No storage migration is needed.
For rollback, restore both application images to the preceding release; existing
grants, role bindings and catalog ownership records are unchanged.

## Corporate directory interactions

Corporate organizational creation and edit use intercepted modal routes. Employee
presentation edit and access grants also preserve the originating page. Project
and team presentation editing use distinct `/presentation/edit` pages. Repository
binding is part of project edit and uses the same subject permission decision,
including the active lead of the current owner team.

Area menus contain details and permitted management actions; landscape-view
subjects additionally receive ordered expand, collapse and technology-list actions.
Area menus omit generic sharing and copy actions. Scan menus expose details and
completed-scan deletion to principals with `landscape.manage`; project navigation
is an explicit journal button. Reports occurs once in root navigation; Landscape
contains the map, scans and mapping only.
