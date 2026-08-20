---
description: "Размеры и поставка логотипа ai_stp."
last_verified: "2026-08-09"
---

# Логотип и иконки ai_stp

Источник: финальный mark (5 человек, за локти), true-alpha PNG.

**Safe-zone:** ~10% с каждой стороны при ресайзе.

**Gradient:** `#f4793f` → `#fb631b` → `#b0486e` → `#62347a` → `#2d1c4e`

## Размеры

| Файл | px | Назначение |
|------|-----|------------|
| logo-large.png | 512 | Большое лого / hero |
| logo-medium.png | 256 | Среднее лого |
| logo-small.png | 128 | Малое лого / UI |
| logo-mark.png | 512 | Основной mark |
| logo-mark-64.png | 64 | UI chip |
| icon-512.png | 512 | PWA / store |
| icon-192.png | 192 | Android / PWA |
| icon-48 / 32 / 16 | 48/32/16 | Toolbar / favicon ladder |
| favicon-32.png | 32 | Favicon |
| apple-touch-icon.png | 180 | iOS home screen |
| logo-mark.svg / icon.svg | vector wrapper | SVG (embedded PNG, true alpha) |
| logo-on-dark.svg / logo-on-light.svg | 64 | Контекстные обёртки |
| logo-lockup.svg | — | Mark + wordmark ai_stp |

## Каналы

- PNG: **RGBA**, background alpha = 0 (hollow center + outer field)
- Не класть чёрную/белую подложку под mark
- SVG: `<image href="data:image/png;base64,...">` — pixel-perfect raster, без перерисовки
