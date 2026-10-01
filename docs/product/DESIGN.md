---
description: "The visual design system for the web MVP: tokens, typography, components, and modes."
last_verified: "2026-08-22"
---

# ai_stp — design system

> Surface: web (`apps/web`)  
> Source of truth: `apps/web/src/theme/tokens.json`  
> Runtime CSS: `apps/web/src/app/globals.css`  
> Brand voice: [BRAND.md](BRAND.md)

A dense product UI for the catalog, account, devices, and installation paths. Two modes: light **human** and dark **machine**.

## Color palette

| Role | Name | Hex | Usage |
| --- | --- | --- | --- |
| background | Machine canvas | `#101010` | Dark product canvas |
| surface | Ink surface | `#181818` | Raised panels, cards (dark) |
| foreground | White | `#ffffff` | Primary text on dark |
| muted | Grey 600 | `#858483` | Secondary labels, meta |
| border | Grey 800 | `#434343` | Hairlines (machine) |
| accent | Signal orange | `#fb631b` | CTA, links, focus, active markers |
| accent-secondary | Signal orange hover | `#f4793f` | Primary hover |

Human mode: white `#ffffff` canvas, ink `#181818`, sand `#f9f8f4`, light `#d4d2cb` border.

Semantic HSL channels are in `tokens.json` under `color.*` for the light and dark themes. Product code uses roles (`primary`, `muted-foreground`, `border`), not raw hex.

State colors (`error`/`success`/`warning`) are in the same token file for forms and trust feedback.

## Typography

| Role | Family | Weights | Use |
| --- | --- | --- | --- |
| Display / UI | plexSans | 400, 500 | Headings, body, controls |
| Mono | plexMono | 400, 500 | Stable ids, versions, install code, technical meta |

Size scale: 12 · 14 · 16 · 18 · 20 · 24 · 30 (tokens in CSS).

Both typefaces are IBM Plex under SIL OFL 1.1, split by `unicode-range`, so a Latin
page does not load Cyrillic font files. The reason for the replacement and its verification are in
[BRAND.md](BRAND.md) and the comment in `apps/web/src/app/globals.css`.

## Layout

| Token | Value | Use |
| --- | --- | --- |
| Radius base | 8px (`0.5rem`) | Cards, panels |
| Radius sm | 4px | Buttons, inputs, selects |
| Radius md | 6px | Badges / chips |
| Radius xl | 16px | Large shells |
| Border | 1px | Never thick frames |
| Space baseline | 8px | 2 / 4 / 8 / 12 / 16 / 24 / 32 / 40 / 48… |
| Content width | Flexible remaining width | Human main beside the shared sidebar |
| Horizontal pad | 16–24px | Header and main |
| Narrow public screen | 360–430 px | landing, catalog, object card, sign-in, account |

At 360–430 px, the document does not overflow horizontally; the actions for
installation and viewing sources remain visible; primary actions on the
object page and in the shell have a 44px target. Mobile navigation and
result refinement retain keyboard access and visible focus. Executable criteria are in
`SPEC-022`, `SPEC-023`, `SPEC-034`, `SPEC-037`.

### Presentation rules

1. There are two independent display axes: the `human`/`machine` projection and the `light`/`dark` color theme. The theme button changes colors only. Under `ADR-0076` and `SPEC-036`, the projection is an addressable route and a separate server document, not styling applied to the human tree: the switch pinned at the bottom leads to the paired URL. Machine uses monospaced presentation and a text document in which Markdown heading markers and links are content, with no decorative media.
2. Accent orange is used only for a strong signal: CTAs, focus rings, the brand stripe, and key active dots. Full-screen fills are prohibited.
3. One solid primary button remains per action in a viewport.
4. Hover does not turn primary text gray: fill/border changes, while foreground contrast remains no lower than the default.
5. Every focusable control has a visible `:focus-visible` ring using `--ring` (accent).
6. Mono is used for machine labels; decorative emoji are not used as functional icons.
7. Icons only from `src/theme/icons.tsx` registry.

## React component set

Path root: `apps/web/src/components/`

### Atoms

| Component | File | Notes |
| --- | --- | --- |
| Button | `atoms/button.tsx` | default / secondary / outline / ghost / destructive; sizes sm · default · lg · icon |
| Badge | `atoms/badge.tsx` | mono chips, radius md |
| Input | `atoms/input.tsx` | radius sm, 1px border |
| Textarea | `atoms/textarea.tsx` | same as input |
| Label | `atoms/label.tsx` | Radix label |
| Skeleton | `atoms/skeleton.tsx` | muted pulse |
| Dialog | `atoms/dialog.tsx` | Radix dialog shell |

Modal backdrops use the theme-independent `scrim` role so dark surfaces dim rather
than brighten. The default border reset belongs to the CSS base layer; semantic
state utilities must remain able to override it. `SearchableMultiSelect` supports
an inline disclosure for constrained dialogs, keeping options in the form flow
and the submit action reachable.

### Molecules

SearchField · StatePanel · ThemeToggle · RouteLoading · DetailAccordion · PassportJsonViewer · CatalogAuthorLink · ObjectTechnicalDetails · RequirementsSummary · ObjectVersionHistory

### Organisms

ObjectCard · CatalogFilters · CatalogResults · InstallBlock · DeviceList · IdentityList · ProfileForm · ObjectDetailHeader · ObjectDetailFrame · ComponentMediaGallery

### Layouts

AppShell · SiteHeader · MachineHeader · MachineIndex · MachineFooter

## Storybook

```bash
cd apps/web
bun run storybook
bun run build-storybook
```

Groups: Foundations · UI Kit / Atoms · Molecules · Organisms · Layouts. Toolbar switches light/dark.

## Changing the theme

1. Edit `apps/web/src/theme/tokens.json`.
2. Mirror channels into `globals.css` (`:root` / `.dark` and `@theme inline`).
3. Keep React on semantic utilities only.
4. Rebuild Storybook to verify foundations and kit stories.

## Shared Human navigation

`layouts/context-rail.tsx` extends the original corporate rail and is mounted
once by `AppShell` for SaaS and Corporate. Its atoms are the existing Button,
Dialog and registered Icon; no page creates a separate sidebar. The header holds
utilities and spans the viewport above the rail. The desktop collapse control
sits beside the brand in that global bar. The rail begins below the bar, with no
second logo row. Desktop is expanded or an icon rail; narrow screens use the same
links in a focus-contained dialog. The active page comes from the URL, and
page links never double as group-disclosure buttons. Administration groups and
semantic parent links follow ADR-0219 and SPEC-095. Personal account navigation
belongs to the header popup, not the sidebar. The drawer has no Corporate label.
Preserve the normal profile-aware full-width footer with brand, summary and
destination columns, including Documentation and `llms.txt`.

Corporate authentication screens and unverified sessions have no drawer or
trigger. Protected Corporate routes receive server-verified page IDs so the
rail is present in the first HTML and first hydration. The header carries the
brand when the rail is unavailable. Desktop collapsed navigation has one
icon per top-level entry, with Radix flyouts for grouped destinations. Mobile
uses the existing Dialog and closes at 1024 px without changing the desktop
preference. Initial HTML and hydration agree before stored preferences apply.
`ContextSidebar` exposes the incumbent rail frame for the 13 Storybook scenarios;
`ContextRail` owns session/capability availability. The light active surface uses
a 5% primary tint to keep small primary text above WCAG AA contrast; dark keeps
the existing 10% tint.

### People administration component reuse

Members & Invitations extends the existing directory kit. The existing generic
resource cards do not cover checkbox selection, membership-specific contact/date
columns or invitation history/actions. The domain table organisms therefore
compose the incumbent Badge, Button, Input, Dialog, CompactChipList,
SearchableMultiSelect and registered Icon components. NavigationTabs adds an
underline variant; CatalogChoiceMenu adds callback options for sorting/export and
revoke. Neither change introduces another controls system or dependency.
Tables scroll locally at narrow widths with keyboard access; toolbars wrap and
modal content is bounded by the viewport. Summary counts stay separate from tabs.

The shared Dialog returns focus to its external opener when a flow does not use
DialogTrigger, while honoring explicit autofocus handlers. Its backdrop uses
the semantic scrim token in both themes. Base border defaults stay in the base
CSS layer so component state utilities retain their intended colors. Invitation
team selection expands inline to keep submission controls reachable.
