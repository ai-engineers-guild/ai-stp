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
| Content width | `max-w-6xl` | App shell main |
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
