---
description: "ai_stp logo sizes and delivery."
last_verified: "2026-08-09"
---

# ai_stp logo and icons

Source: final mark (five people linked at the elbows), true-alpha PNG.

**Safe zone:** ~10% on each side when resizing.

**Gradient:** `#f4793f` → `#fb631b` → `#b0486e` → `#62347a` → `#2d1c4e`

## Sizes

| File | px | Purpose |
|------|-----|------------|
| logo-large.png | 512 | Large logo / hero |
| logo-medium.png | 256 | Medium logo |
| logo-small.png | 128 | Small logo / UI |
| logo-mark.png | 512 | Primary mark |
| logo-mark-64.png | 64 | UI chip |
| icon-512.png | 512 | PWA / store |
| icon-192.png | 192 | Android / PWA |
| icon-48 / 32 / 16 | 48/32/16 | Toolbar / favicon size ladder |
| favicon-32.png | 32 | Favicon |
| apple-touch-icon.png | 180 | iOS home screen |
| logo-mark.svg / icon.svg | vector wrapper | SVG (embedded PNG, true alpha) |
| logo-on-dark.svg / logo-on-light.svg | 64 | Context-specific wrappers |
| logo-lockup.svg | — | Mark + wordmark ai_stp |

## Channels

- PNG: **RGBA**, background alpha = 0 (hollow center + outer field)
- Do not place a black or white backing behind the mark
- SVG: `<image href="data:image/png;base64,...">` — pixel-perfect raster, without redrawing
