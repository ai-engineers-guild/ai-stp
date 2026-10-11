---
description: "Consolidation of the apps/web component library: dead-code removal, missing primitives, tier corrections, and the component-driven boundary."
last_verified: "2026-10-07"
---

# Web component consolidation plan

Source: full inventory audit of `apps/web/src/components/**` (168 files, import
cross-reference against `app/`, `lib/`, `actions/`, `stories/`, `tests/`) on
2026-10-07, branch `feat/saml-identity-provider` neighborhood.

## Objective

One component library where every interface is composed from registered kit
components, every component carries a Storybook story and a component test, dead
code is removed, and missing primitives (`select`, `menu`, `table`, pager,
copy) exist once instead of as per-file copies.

## Hard boundaries

Enforced in [`apps/web/DESIGN.md`](../../apps/web/DESIGN.md) and the AGENTS.md
web gate; repeated here as the operative list:

1. UI is composed only from components in
   `apps/web/src/components/{atoms,molecules,organisms,layouts,screens}` and
   `@/theme` icons. Raw `<select>`, `<table>` row markup, and direct
   `radix-ui` imports are prohibited outside the kit file that owns the
   primitive.
2. Every component ships a Storybook story under
   `apps/web/src/stories/UI Kit/<Tier>/` and a component test under
   `apps/web/tests/component/` (pure helpers may use `tests/unit/`). No story +
   no test = not mergeable.
3. Adapt before create: a new component is allowed only after the existing kit
   is shown insufficient; the reason is recorded in the PR description or
   `DESIGN.md`.
4. Tiers follow the FSD shared-layer idea: `atoms` = single elements and radix
   wrappers; `molecules` = composed atoms, no data fetch; `organisms` = feature
   sections; `layouts` = shells/chrome; `screens` = route-level compositions
   that may fetch and gate sessions. Hooks, label factories, and type modules
   live in `src/lib/`, not in component tiers.
5. File name equals primary export name; no cross-file re-export barrels
   inside tiers.

## Inventory baseline

| Group | Files | Verdict |
| ----- | ----- | ------- |
| atoms | 11 | all live; missing `select`, `menu`, `table` primitives |
| molecules | 48 | 3 dead/test-only/story-only, 2 tier violations |
| organisms | ~105 | 13 dead/test-only, 2 page-tier files, 6 non-component modules |
| layouts | 6 | 1 test-only (`corporate-hub-navigation`) |
| `installations/`, `usage/` | 4 | dead tables + wire types; folders outside the tier list |
| providers | 1 | live |
| page-local modules | 6 | legitimate colocation; migrate to primitives later |

Cross-cutting duplication measured: ~50 raw `<select>` in ~30 files, 13 files
with raw `DropdownMenu`, 4 copies of `itemClassName`, 16 raw `<table>` files, 2
parallel pagers (`PageNav` vs `PeoplePager`), 3 clipboard implementations, 3
initials-avatar implementations.

## Phase 0 — documentation boundary (this change)

- `apps/web/DESIGN.md` rules extended with the five boundaries above.
- `AGENTS.md` web gate hardened to the same contract.
- This plan registered in the engineering index (`just docs-gen`).

## Phase 1 — dead code removal (~20 files, ~4 300 LOC)

Delete file + its test + its story; update importers where a live file
re-exports the dead module.

| File | Also remove / fix |
| ---- | ----------------- |
| `molecules/collapsible-section.tsx` | — (alias of `DetailAccordion`) |
| `molecules/scoped-object-filters.tsx` | — |
| `molecules/search-field.tsx` | `stories/UI Kit/Molecules/SearchField.stories.tsx`; keep the local `SearchField` inside `corporate-directory-toolbar.tsx` (different controlled API; collision resolved by deleting the dead shared one) |
| `molecules/safety-checks-summary.tsx` | `tests/component/safety-checks-summary.test.tsx`. **Precondition:** confirm REQ-2703 owner-version coverage is satisfied by `OwnerCoverage` + `EvidenceList`; if not, wire the view into `objects/[kind]/[stableId]/versions/[version]` instead of deleting. Default: delete. |
| `organisms/context-budget-local-check.tsx` | — |
| `organisms/context-cost-calculator.tsx` | — |
| `organisms/corporate-employee-directory.tsx` | — |
| `organisms/corporate-employee-technologies.tsx` | — |
| `organisms/corporate-member-profile.tsx` | `tests/unit/corporate-member-profile.test.tsx` |
| `organisms/corporate-project-memberships.tsx` | `tests/unit/corporate-project-memberships.test.tsx` |
| `organisms/corporate-team-editor.tsx` + `corporate-team-memberships.tsx` | `tests/component/corporate-team-workspace.test.tsx` — split, keep the `CorporateResourceActions` (live) part |
| `organisms/corporate-technology-owner-editor.tsx` | `tests/unit/corporate-technology-owner-editor.test.tsx` |
| `organisms/project-team-editor.tsx` + `project-technology-editor.tsx` | `tests/unit/project-team-editor.test.tsx`, `tests/unit/project-technology-editor.test.tsx` |
| `organisms/technology-governance-editors.tsx` | `tests/unit/technology-team-editor.test.tsx` |
| `organisms/technology-merge-controls.tsx` | merge-controls portion of `tests/unit/technology-registry-create.test.tsx` (keep the registry-create part) |
| `layouts/corporate-hub-navigation.tsx` | `tests/unit/corporate-hub-navigation.test.tsx` |
| `installations/installations-table.tsx` | move `installations/types.ts` → `src/lib/installations-types.ts`, update `app/api/corporate/installations/route.ts`, delete folder |
| `usage/usage-report-panel.tsx` | move `usage/usage-report-types.ts` → `src/lib/usage-report-types.ts`, update `app/api/corporate/usage/route.ts`, delete folder |

Exit: `just web-check` green; no `components/installations`/`components/usage`
imports remain; the "TEST-ONLY" class is empty in a re-run of the audit script.

## Phase 2 — missing primitives

Each lands with story + component test (boundary 2) before consumers migrate.

| New/changed | Basis | Consumers to migrate |
| ----------- | ----- | -------------------- |
| `atoms/select.tsx` | `peopleSelectClass` from `corporate-people-ui.tsx` (h-11, `rounded-sm`, `border-input`, focus ring) | ~50 raw `<select>` sites: connectors, corporate panels, `dashboard-builder`, `machine-chrome`, page-local tables/filters |
| `atoms/menu.tsx` (DropdownMenu wrapper + `MenuItem`/`MenuLinkItem`/`MenuSeparator`) | shared `itemClassName` (11px variants in 4 files converge to one) | `catalog-item-menu`, `object-menu-privileged`, `entity-detail-menu`, `component-actions`, `corporate-resource-actions`, `publisher-actions`, `staff-case-actions`, `access-workspace`, `sso-sign-in`, `context-rail`, `compact-chip-list`, `catalog-choice-menu`, `account-drawer` |
| `atoms/table.tsx` (`Table`/`THead`/`TBody`/`Tr`/`Th`/`Td`) | `peopleHeadClass`/`peopleCellClass` | 16 raw-table files incl. page-local `RoleTable`/`MatrixTable`/`EffectiveAccessTable`, `usage-report-table`, `dashboard-builder` |
| `molecules/page-pager.tsx` | merge `PageNav`/`SingleResourcePager` (link mode) + `PeoplePager` (button mode) over `lib/page-window` | `catalog-results`, `corporate-directory-results`, `corporate-members-directory`, `corporate-invitations-panel`; delete `organisms/catalog-page-nav.tsx` and `PeoplePager` |
| `molecules/clipboard-icon-button.tsx` | add optional `label` prop for text-button use | `copy-value.tsx` re-implemented over it; `install-block.tsx` uses it (third clipboard impl removed) |
| `atoms/avatar-image.tsx` | export `InitialsAvatar` (initials circle) | `PersonIdentity` (people-ui), `AuthorChipContent` (catalog-filters), `verified-avatar` |

## Phase 3 — merges, renames, shadowing

| Action | Detail |
| ------ | ------ |
| `organisms/account-drawer.tsx` → `account-control.tsx` | export is `AccountControl`; update `site-header.tsx` |
| remove re-export of `CorporateMembershipPolicyControls` from `corporate-invitations-panel.tsx` | `admins/security/page.tsx` imports from `corporate-membership-policy-controls` directly |
| `lib/github-connection-flow.ts` → `lib/connection-flow.ts` | used by GitLab connector too; name lies about ownership |
| delete dead `molecules/search-field.tsx` | resolves shadow by toolbar-local `SearchField` (phase 1) |

## Phase 4 — tier and file moves

| Action | Detail |
| ------ | ------ |
| new tier `components/screens/` | route-level compositions with fetch/session: `object-presentation-editor-page.tsx`, `corporate-create-page.tsx` move here |
| `organisms/use-{catalog-like,object-presentation-form,profile-form}.ts` → `src/lib/` | `lib/` already holds `use-hydrated.ts`, `use-narrow-viewport.ts` |
| `organisms/{context-budget-labels,corporate-directory-types,corporate-employee-labels}.ts` → `src/lib/` | type/label modules, not components |
| `organisms/corporate-people-ui.tsx` → `molecules/people-ui.tsx` | molecule-weight primitives; do not split into six files — `PeopleSelect`/`PeopleCheckbox` dissolve into atoms once `select` lands |
| `organisms/corporate-heartbeat-rows.tsx` → `molecules/` | rendering fragment of heartbeat-report |
| `molecules/component-target-matrix.tsx` (382) → `organisms/` | full assessment section, organism weight |
| `molecules/landing-hero-preview.tsx` → `organisms/` | hero media block |
| `molecules/entity-editor-layout.tsx` | keep in molecules; rename to `entity-editor.tsx` only if touched later (low value churn) |

## Phase 5 — connector convergence (after phases 2–3)

Extract `useConnectorFlow` (status/plan/error/`run`/popup-poll) from
`github-connector.tsx` (491) and `gitlab-connector.tsx` (634) into `lib/`; keep
two thin organisms with provider deltas. Reuses the renamed
`lib/connection-flow.ts`.

## Verification

- After each phase: `just web-check` (build, types, unit, E2E, profiles).
- Phase 1 additionally: `just back-static` for import drift; Storybook build.
- Final: re-run the inventory script; expected zero `DEAD`/`TEST-ONLY`/`STORY-ONLY`,
  zero raw `<select>`/`<table>`/`DropdownMenu` outside owning primitives.

## State

| Phase | State | Commit/PR |
| ----- | ----- | --------- |
| 0 docs boundary | done | this change |
| 1 dead code | done | this change |
| 2 primitives | done | this change |
| 3 merges/renames | done | this change |
| 4 tier moves | done | this change |
| 5 connectors | done | this change |
