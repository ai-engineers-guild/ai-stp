# Theme & UI kit

Portable design system for `apps/web` (product **ai_stp**).

| Role           | Light (human)   | Dark (machine) |
| -------------- | --------------- | -------------- |
| canvas         | `#ffffff`       | `#101010`      |
| surface / card | `#f9f8f4`       | `#181818`      |
| foreground     | `#181818`       | `#ffffff`      |
| muted          | grey-600 family | `#858483`      |
| border         | `#d4d2cb`       | `#434343`      |
| primary / CTA  | `#fb631b`       | `#fb631b`      |
| primary hover  | `#f4793f`       | `#f4793f`      |

Type: **plexSans** (UI) + **plexMono** (labels, ids, code). Fonts live in `public/fonts/`.

Specs: [`docs/product/BRAND.md`](../../../../docs/product/BRAND.md) · [`docs/product/DESIGN.md`](../../../../docs/product/DESIGN.md) · [`DESIGN.md`](../../DESIGN.md)

HTML page prototypes (mirror of real routes): `docs/references/prototypes/`.

## Change theme

1. Edit **`tokens.json`** (DTCG-shaped: color, space, radius, font, icon, motion).
2. Mirror values into **`../app/globals.css`** (`:root` / `.dark` and `@theme inline`).
3. Components already use **semantic utilities** (`bg-primary`, `text-muted-foreground`, `rounded-lg`). Do not add raw hex.
4. Keep signal orange high-signal only (primary CTA, focus ring, active mono markers) — never full-bleed washes.

## Icons

Register every product icon in **`icons.tsx`**. Import `Icon` from `@/theme` in pages/components.

## Storybook

```bash
cd apps/web
bun run storybook          # http://localhost:6006
bun run build-storybook    # storybook-static/
```

Sidebar groups:

- **Foundations** — Introduction, Colors, Typography, Spacing, Radius, Icons
- **UI Kit / Atoms** — Badge, Button, Dialog, Input, Label, Skeleton, Textarea
- **UI Kit / Molecules** — RouteLoading, SearchField, StatePanel, ThemeToggle
- **UI Kit / Organisms** — CatalogFilters, CatalogResults, DeviceList, IdentityList, InstallBlock, ObjectCard, ProfileForm
- **UI Kit / Layouts** — AppShell, SiteHeader

Use the toolbar theme switch (light/dark).
