---
description: "Executable change-request ledger for the Corporate Hub consolidation."
last_verified: "2026-09-18"
---

# Corporate workspace change requests

## Usage

Execute change requests in order. A request is complete only after its exit oracle is
green and its documentation and generated artifacts are included. `Blocked by` names
hard dependencies; requests within one dependency level may be developed concurrently
but merge in delivery order.

## Ledger

| ID | Change | Owns | Blocked by | Exit oracle |
|---|---|---|---|---|
| `CR-CORP-01` | Stabilize server/client rendering and production smoke | Hydration, Radix IDs, session render parity, clean-build runtime | — | Production server route matrix has no HTTP 500 or browser-console error. |
| `CR-CORP-02` | Land normative package | SPEC-086, ADR-0192, ADR-0193, incumbent clarifications, generated indexes | — | `just docs-check` passes. |
| `CR-CORP-03` | Add job-title persistence and administration contract | Job-title table, membership reference, lifecycle, permissions, CRUD, audit | `CR-CORP-02` | Upgrade/downgrade, uniqueness, RBAC, tenant, and generated-contract tests pass. |
| `CR-CORP-04` | Consolidate bounded directory projections | One card DTO, owner/lead/category enrichment, pagination, facets, available actions | `CR-CORP-02` | Root/nested parity and authorization-before-count integration tests pass. |
| `CR-CORP-05` | Add transactional aggregate creation | Team, project, employee create commands and relationship validation | `CR-CORP-03`, `CR-CORP-04` | Role, replay, stale-revision, and no-partial-write tests pass. |
| `CR-CORP-06` | Canonicalize account and employee routes | Shared account detail, `/employees`, member redirects, corporate publisher resolution | `CR-CORP-04` | Identity, redirect, canonical-link, and public privacy tests pass. |
| `CR-CORP-07` | Consolidate the corporate catalog | `/corporate/catalog`, old-route redirects, corporate facets, URL codec, setup/component parity | `CR-CORP-02`, `CR-CORP-04` | PostgreSQL search, public compatibility, facet, URL, and redirect tests pass. |
| `CR-CORP-08` | Adopt directory pagination and corrected cards | Four root directories, job-title filter, technology owner/category, project owner | `CR-CORP-03`, `CR-CORP-04`, `CR-CORP-06` | Bounded loader, count, page, filter, sort, card, and mobile tests pass. |
| `CR-CORP-09` | Unify entity actions and create screens | Capability-driven menus, three dedicated create routes, searchable selectors | `CR-CORP-05`, `CR-CORP-08` | Administrator/lead/owner/self/staff UI and forged-request API matrices pass. |
| `CR-CORP-10` | Consolidate detail relations and organization usage | Expanded-only filters, ObjectCard assignments, stable routes, rail cards, usage API/UI | `CR-CORP-04`, `CR-CORP-07`, `CR-CORP-09` | Usage isolation/deduplication and detail component/browser tests pass. |
| `CR-CORP-11` | Polish overview, lifecycle, Markdown, and gallery | Description removal, exceptional-state display, table styling, wider rail, carousel | `CR-CORP-10` | Accessibility, visual, keyboard, reduced-motion, and responsive checks pass. |
| `CR-CORP-12` | Qualify and roll out | GitHub heavy gate, additive rollout, post-deploy observation, rollback evidence | `CR-CORP-01`…`CR-CORP-11` | Exact-SHA CI and post-deploy smoke are green. |

## Requirement coverage

| Requirement | Change requests |
|---|---|
| `REQ-8601` | `CR-CORP-06` |
| `REQ-8602` | `CR-CORP-07` |
| `REQ-8603` | `CR-CORP-04`, `CR-CORP-08` |
| `REQ-8604` | `CR-CORP-04`, `CR-CORP-08` |
| `REQ-8605` | `CR-CORP-05`, `CR-CORP-09` |
| `REQ-8606` | `CR-CORP-04`, `CR-CORP-09` |
| `REQ-8607` | `CR-CORP-11` |
| `REQ-8608` | `CR-CORP-10`, `CR-CORP-11` |
| `REQ-8609` | `CR-CORP-10`, `CR-CORP-11` |
| `REQ-8610` | `CR-CORP-07` |
| `REQ-8611` | `CR-CORP-03`, `CR-CORP-08` |
| `REQ-8612` | `CR-CORP-10` |
| `REQ-8613` | `CR-CORP-11` |
| `REQ-8614` | `CR-CORP-01`, `CR-CORP-12` |

## Implementation anchors

These anchors identify incumbent owners to extend. They are not permission to create
parallel frameworks when the named owner can carry the behavior.

| Concern | Incumbent owner |
|---|---|
| Corporate directory contract | `packages/contracts/src/ai_stp_contracts/corporate_directory.py` |
| Catalog corporate facets | `packages/contracts/src/ai_stp_contracts/catalog.py` and `apps/platform/src/ai_stp_platform/catalog_search.py` |
| Corporate directory API | `apps/api/src/ai_stp_api/slices/corporate/directory.py` |
| Corporate governance API | `apps/api/src/ai_stp_api/slices/corporate/governance.py` |
| Catalog search API | `apps/api/src/ai_stp_api/slices/catalog/router.py` and `service.py` |
| Directory Web loader | `apps/web/src/lib/api/corporate.ts` |
| Directory cards and filters | `corporate-directory-card.tsx`, `corporate-directory-toolbar.tsx`, and `corporate-relation-section.tsx` |
| Canonical catalog | `apps/web/src/app/[locale]/(site)/catalog/(index)/page.tsx`, `catalog-filters.tsx`, and `catalog-filter-panel.tsx` |
| Shared detail frame | `corporate-entity-detail.tsx` and `object-detail-frame.tsx` |
| Assigned catalog cards | `corporate-catalog-assignments.tsx` and the incumbent `ObjectCard` |
| Markdown | `apps/web/src/lib/markdown/render.ts` and its shared article-table styles |
| Gallery | `component-media-gallery.tsx` |
| Searchable relation selection | `searchable-multi-select.tsx` |
| Route and machine inventories | `corporate-hub-navigation.tsx`, `projection/navigation.ts`, `projection/inventory.ts`, and `projection/routes-corporate.ts` |

Generated schemas, OpenAPI, projections, clients, and documentation indexes are updated
only through `just back-gen` or `just docs-gen` as owned by the repository.

## Original feedback coverage

| Feedback | Change requests |
|---|---|
| 1 | `CR-CORP-11` |
| 2, 10 | `CR-CORP-01`, `CR-CORP-12` |
| 3, 7, 20 | `CR-CORP-05`, `CR-CORP-09` |
| 4, 6, 14, 21 | `CR-CORP-09` |
| 5, 23, 24 | `CR-CORP-04`, `CR-CORP-08` |
| 8, 15, 16, 17 | `CR-CORP-10` |
| 9, 25 | `CR-CORP-07` |
| 11, 12, 13 | `CR-CORP-11` |
| 18 | `CR-CORP-10` |
| 19, 27 | `CR-CORP-06` |
| 22 | `CR-CORP-04`, `CR-CORP-08` |
| 26 | `CR-CORP-03`, `CR-CORP-08` |

## Pull-request slices

1. `CR-CORP-01` and `CR-CORP-02` may land independently.
2. `CR-CORP-03` through `CR-CORP-05` form the contract and API foundation.
3. `CR-CORP-06` through `CR-CORP-08` consolidate routes, catalog, and directories.
4. `CR-CORP-09` and `CR-CORP-10` consolidate mutations and details.
5. `CR-CORP-11` is the presentation pass after structural UI is stable.
6. `CR-CORP-12` contains qualification and rollout evidence, not feature code.
