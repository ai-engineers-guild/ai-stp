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

## Recipient import reuse

The existing kit has no validated file-drop field or recipient review table.
`MemberImportFields` composes native file input/drop/paste with the existing Label,
Textarea and Icon; `MemberImportPreview` owns the reusable, read-only semantic table
and its empty/loading/validation states. Invitation Dialog, Button, Badge and
CompactChipList remain shared kit components. Files are parsed locally; the preview
never sends mutations. `read-excel-file` is dynamically loaded by
`src/lib/member-import-file.ts` solely for XLSX. That adapter owns the dependency;
remove it when XLSX support is removed. Other formats use the existing text parser.
