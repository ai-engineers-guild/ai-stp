# ai_stp web design system

Canonical product docs:

- Brand: [`docs/product/BRAND.md`](../../docs/product/BRAND.md)
- Design: [`docs/product/DESIGN.md`](../../docs/product/DESIGN.md)

## Runtime sources

| Artifact      | Path                                                 |
| ------------- | ---------------------------------------------------- |
| Tokens (DTCG) | `src/theme/tokens.json`                              |
| CSS variables | `src/app/globals.css`                                |
| Typed helpers | `src/theme/tokens.ts`                                |
| Icons         | `src/theme/icons.tsx`                                |
| UI kit        | `src/components/{atoms,molecules,organisms,layouts}` |
| Storybook     | `src/stories/**`                                     |

## Modes

- **Human projection:** visual product interface optimized for people
- **Machine projection:** compact technical representation with explicit machine-readable links
- **Color theme:** independent light/dark control available in either projection

Primary signal: `#fb631b` → hover `#f4793f`. Type: plexSans + plexMono.

## Rules (ship checklist)

1. No raw hex in components — only token utilities.
2. Controls `rounded-sm` (4px); chips `rounded-md` (6px); cards `rounded-lg` (8px).
3. Primary CTA hover keeps white text on orange hover fill.
4. Ghost/outline hover shifts surface only — never greys the label.
5. One solid primary per action per viewport.
6. Icons only via `@/theme` `Icon`.
7. Public landing, catalog, detail, login, and account stay usable at 360–430px: no document overflow, visible install/view CTA, 44px primary actions.

## Component boundary (hard)

UI is component-driven. Pages and layouts compose registered kit components;
they do not invent controls inline.

1. Interfaces use only components from
   `src/components/{atoms,molecules,organisms,layouts,screens}` and icons from
   `@/theme`. Raw `<select>`, `<table>` row markup, and direct `radix-ui`
   imports are forbidden outside the kit file that owns that primitive.
2. Every component ships with a Storybook story under
   `src/stories/UI Kit/<Tier>/` and a component test under
   `tests/component/` (pure helpers may use `tests/unit/`). A component
   without both is not mergeable.
3. Adapt before create: search the kit first and extend the existing
   component; a new component is allowed only after the kit is shown
   insufficient, with the reason recorded in the PR description or this file.
4. Tiers: `atoms` — single elements and radix wrappers; `molecules` —
   composed atoms, no data fetch; `organisms` — feature sections; `layouts` —
   shells and chrome; `screens` — route-level compositions that may fetch and
   gate sessions. Hooks, label factories, and type-only modules live in
   `src/lib/`, not in component tiers.
5. File name equals the primary export name; no re-export barrels between
   component files.

The consolidation order and the audit baseline are in
[`docs/engineering/web-component-consolidation-plan.md`](../../docs/engineering/web-component-consolidation-plan.md).

## Recipient import reuse

The existing kit has no validated file-drop field or recipient review table.
`MemberImportFields` composes native file input/drop/paste with the existing Label,
Textarea and Icon; `MemberImportPreview` owns the reusable, read-only semantic table
and its empty/loading/validation states. Invitation Dialog, Button, Badge and
CompactChipList remain shared kit components. Files are parsed locally; the preview
never sends mutations. `read-excel-file` is dynamically loaded by
`src/lib/member-import-file.ts` solely for XLSX. That adapter owns the dependency;
remove it when XLSX support is removed. Other formats use the existing text parser.

## Technology workspace reuse

The five supplied references define the technology map/table, journal, mapping
and scan-detail compositions. The existing `TechnologyLandscapeResults`,
`TechnologyLandscapeFilters`, `TechnologyScanFindings`, `TechnologyScanLaunch`
and `TechnologyRegistryCreate` remain the feature entry points. The kit had no
scan journal with repository/date/duration filtering or inline category
finding editor. `TechnologyScanJournal`, `TechnologyReviewHeader`,
`TechnologyFindingsTable` and `TechnologyReviewDialogs`
compose existing Table, PagePager, Select, SearchableMultiSelect, Dialog and
registry forms; they do not introduce primitives. Shared draft/review state lives
in `src/lib/technology-review-state.ts`. The old standalone mapping editor is
removed to keep recognized and unknown findings on one mutation path.

`TechnologyWorkspace.stories.tsx` registers map, table, journal, mapping, scan,
empty, read-only and dark states. `technology-workspace.test.tsx` exercises their
functional compositions. Scoped technology CSS uses existing theme tokens and
Plex typography, five area columns and five metrics on desktop, a persistent
category table with derived areas, and contained tables on narrow screens. Production
counts and rows always come from the authorized contract client.
Repeated technology findings share one row with merged versions and evidence.
Warning-tinted rows and the review filter expose outstanding classification;
journal row navigation and per-row action menus remain independent.

## Corporate project repository source

`CorporateProjectRepository` fills the source slot in `CorporateEntityDetail`'s
existing identity rail. `ExactSourceLink`, Button, Input, Label and Badge already
cover display and controls; no primitive was added. No existing organism owns
project source authorization, URL preview and explicit binding, so the organism
composes those kits. Linking never starts a scan. Public GitHub and the configured
organization GitLab are supported. A saved source displays provider, repository
link, URL and branch, including for read-only viewers.

## People & Access workspace reuse

The existing directory kit supplies search, filters, identities, chips and pagination.
The kit had no entity/action permission table or role workspace. `CorporatePermissionTable`
adds one semantic table shared by role viewing, role editing and effective employee access.
`CorporateAccessModel` and `CorporateRolesWorkspace` compose those controls around the
server permission catalog and existing navigation manifest. `CorporateEmployeeAccessDrawer`
adds access/profile/activity tabs around the existing member access mutations.
`CorporateDetailDrawer` extends the shared Sheet atom for all three workspaces.
All controls retain the existing Button, Input, Badge, Dialog, Sheet, tokens and icon registry.
No additional dependency is required. Tables scroll within their container on narrow screens;
desktop detail panels reserve content space when the viewport can accommodate both.

## Administration modal/drawer primitives

Administration pages (`/corporate/organization/*`) own exactly two overlay
primitives; domain code supplies fields and submit logic, never its own chrome:

- `FormDialog` (molecule) — centered create/edit/confirm modal: title,
  optional description, caller fields, Cancel + submit with busy and
  `submitVariant="destructive"` for irreversible confirms. Used by member and
  bulk edit, job-title create/edit/assign/delete, category edit and link
  management, grant-access, and invitation revocation. The invitation
  composer keeps raw `Dialog` chrome: its send/import/help footer has three
  custom actions that do not fit the two-button footer.
- `CorporateDetailDrawer` — right-side sheet for view/detail (member access,
  job-title detail, role panel, category detail) with sticky header and an
  `actions` slot. `PeopleTable` is the shared framed, labelled table shell.
- `SearchableMultiSelect` is the single team/employee/technology picker
  (inline or modal, single or multi, avatar options, native form values).

Page headers use the shared `PeopleHeader` (breadcrumb + title) in
`corporate/organization/people-shared.tsx`; each page passes its rail-group
label as `section`.

## Policy & journal surfaces

Administration policy pages (`/corporate/admin/*`) share three molecules the
kit previously lacked; each exists because no existing component covered the
pattern:

- `SettingsSection` — titled card region with icon, description and an aside
  slot; the sectioning unit for policy cards.
- `SwitchRow` — labelled `Switch` atom row with status text; the single
  boolean policy control.
- `InfoNote` — bordered informational callout for policy consequences.
- `FieldHint` — promoted from `organisms/` to `molecules/`; the organism file
  re-exports it for existing imports.

`/corporate/admin/telemetry` is a `NavigationTabs` page (heartbeat / usage /
retention); each tab's submit merges its fields over the known policy into the
single `PUT telemetry/policy` mutation — tabs never clobber each other's
fields. `/corporate/admin/audit` composes `PeopleTable`, `PeoplePager`,
`PeopleSelect`, `PersonIdentity` and `CorporateDetailDrawer` over URL-driven
server filters (actor/action/target_table/outcome/date/q) with offset
pagination and a bounded CSV/JSON export gated on `audit.export`. Security
keeps `SwitchRow` + `SettingsSection` + `InfoNote` composition for the
email-domain policy.
