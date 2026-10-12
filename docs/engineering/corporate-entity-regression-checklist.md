---
description: "Regression oracles for corporate entity details, dialogs, actions and assignments."
last_verified: "2026-10-12"
---

# Corporate entity regression checklist

## Automated oracles

Test design distinguishes the reported failure from the required outcome. Component
checks use the real kit and dialogs, with transport mocked at the request boundary.
PostgreSQL checks use real authorization and persistence. Browser checks exercise
production artifacts, route interception, keyboard interaction and geometry. Test
criticism is a self-review in the implementation thread, not an independent review.

| Request | Failure that must not recur | Required outcome and regression owner |
| --- | --- | --- |
| 1, 10 | Accordion content changes or compresses the detail frame | Stable wide frame, responsive columns and no document overflow: `component-detail.spec.ts`, `corporate-hub-goal.spec.ts`, `corporate-entity-detail.test.tsx`. |
| 2 | Current entity offers redundant navigation | Server detail context removes only Open details, preserving permission decisions and order for all nine entity kinds: `test_entity_action_detail_context.py`, `entity-menu-context.test.ts`. Related entities keep their navigation. |
| 3 | Stable detail shows duplicate CLI cards | Use via CLI remains; Inspect this version is absent: component/setup detail browser and component tests. Version-specific pages retain inspection. |
| 4 | Copy/share rows lengthen the root menu or a left-opening flyout closes under the pointer | One side submenu preserves server order and clipboard commands. Keyboard selection and real-browser pointer selection work: `menu.test.tsx`, `entity-action-items.test.tsx`, component/setup detail browser tests. |
| 5 | Readable public objects disappear until assigned | Corporate search includes readable public and private objects; explicit assignment filters and hidden lifecycle still apply: `test_entity_menu_followups.py`. Mixed multi-page results render across the server/client boundary and retain resource page coordinates: `catalog-pagination.spec.ts`. Private detail uses the authorized private passport envelope; public reads stay closed: `catalog-client.test.ts`, `test_visibility.py`. |
| 6 | Draft technologies fail assignment or retry repeats successful writes | Draft/active/deprecated targets accept assignments; archived targets reject them. Partial retry preserves receipts and retries failed targets only: PostgreSQL follow-ups and `corporate-assign-dialog.test.tsx`. |
| 7 | Sidebar scrolls away before the footer | Fixed viewport rail, accessible Administration and independently scrollable navigation: `corporate-directory-modals.spec.ts`. |
| 8 | Employee creation assigns catalog objects | Form and request contain only employee fields and relationships: `corporate-create-form.test.tsx`. |
| 9 | Lead employee has an empty Team leads rail | Employee rail lists teams they lead: `corporate-employee-detail.test.tsx`. |
| 11 | Assigned cards expose account IDs or an external Unlink button | Publisher name/avatar, contextual permission-backed Unlink, inherited assignments protected, primary Assign before Filters: `corporate-assignment-cards.test.tsx`, PostgreSQL follow-ups. Latest/exact selectors and harness identity survive retirement. |
| 12 | Markdown tables/line breaks or fresh authorization revisions fail saving | GFM tables, emoji and attribute-free line breaks round-trip; unsafe HTML remains rejected. Links/avatar survive and saves use fresh authorization: `test_corporate_entity_profiles.py`, `corporate-presentation-save.test.ts`, `corporate-rich-editor.test.tsx`, `markdown-render.test.ts`. |
| 13 | Employee Save or close is inert, or edit replaces its origin | Success closes and refreshes; failure keeps the draft; Cancel/X closes over the original page: `corporate-member-edit-save.test.tsx`, route-dialog tests and corporate directory browser checks. |
| 14, 16 | Grant or ordinary creation navigates to a separate workspace | Common Grant dialog opens over the invoking card; creators and small organizational editors preserve the origin. Big presentation editors remain pages: `entity-action-items.test.tsx`, `corporate-directory-modals.spec.ts`, `corporate-people-access.spec.ts`. |
| 15 | Team lead appears in both columns | Lead card exists only in the right rail: corporate detail component/browser checks. |
| 17 | Corporate presentation exposes Linked service, Save strands the user, or nested requests submit the presentation | Corporate excludes service fields; SaaS retains them. Save/Cancel returns to the invoking URL, with safe direct-link fallback. Country/service requests submit only their own form: feature-profile, component-presentation-media and external-catalog-requests browser tests, navigation-history, object-presentation-form and external-product-manager tests. |
| 18 | Owner cannot be assigned, or ordinary editing grants that authority | Technology owner action and endpoint require organization management; scoped technology editing does not confer it. Corporate catalog operational-owner action uses the shared capability: PostgreSQL follow-ups and `entity-action-items.test.tsx`. |

## Local acceptance

Use the existing account session and the Corporate Docker stack. Inspect directories,
details and menu commands at `http://localhost:3000/en/corporate/overview`. Confirm
both published local skills in the catalog, including the public one without an
assignment filter. Opening and cancelling editors is read-only acceptance.

Mutation acceptance uses isolated fixtures or a rolled-back database transaction;
do not overwrite existing ownership, grants, assignments or user presentation data.

Before Docker recreation, record the worktree content digest and current API/web
image digests. Build from that recorded source, revalidate the digest and preserve
rollback tags. Recreate only API/web; persistent database and object-storage volumes
remain in place. Repeating the recreation with the same images is idempotent.
Rollback uses the recorded prior images and the same Compose configuration.
