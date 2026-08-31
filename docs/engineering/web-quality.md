---
description: "Web operating rules: SEO, machine discovery, browser storage, selectors, and quality gates."
last_verified: "2026-08-29"
---

# Web Surface Quality

## Human and Machine

Human and Machine are two modes of displaying one server truth. Human uses a light, readable presentation. Machine uses a separate dark technical projection: a textual site index, Markdown-like headings, links with visible URLs, and no decorative media. Forms, routes, data, and server authorization remain the same. The switch stores only the string `light` or `dark` under the key `ai_stp_display_mode`; domain data and permissions do not depend on the mode.

## Machine discovery and SEO

The public surface exposes `robots.txt`, `sitemap.xml`, web manifest, locale-aware metadata, Open Graph, and Twitter summary. For LLM clients, `/llms.txt`, `/llms-full.txt`, and `/agents.md` are available. These files serve as navigation and brief context, but not as a second contract: the fields and enums belong to `docs/contracts/` and `schemas/v1/`.

Private routes are forbidden in `robots.txt` and are not included in the sitemap. This is not a security boundary: authorization and the absence of private data in HTML are ensured by the server.

## Cookies and browser storage

- `ai_stp_session` — signed or server-side opaque session, `HttpOnly`, `SameSite=Lax`, `Secure` in production.
- `ai_stp_csrf` — browser-readable double-submit token, `SameSite=Lax`, `Secure` in production; domain data is absent in it.
- `sessionStorage` is used only for temporary preview of the public profile within the tab.
- `localStorage` is used only by the theme library for `ai_stp_display_mode`.
- Storing secrets, OAuth tokens, private keys, and private object metadata in browser storage is prohibited.

## Stable selectors

The unified catalog is located at `apps/web/src/lib/ui-selectors.ts`. Values are used via `data-ui`; classes and localized text are not an API for browser tests. Real `id` remain on landmarks, form controls, and anchor targets where they are needed for HTML semantics. A new selector value must be unique, readable, and pass `apps/web/tests/unit/ui-selectors.test.ts`.

## Keyboard, touch, and motion

- Interactive elements in the compact mobile header retain a hit area of no less than `44×44px`, even if the label is hidden for width; the accessible name remains via `aria-label`.
- Global shortcuts `C`, `P`, and `Ctrl+K`/`Cmd+K` do not work when entered in `input`, `textarea`, `select`, or `contenteditable`. Single-letter shortcuts are also ignored when using modifiers.
- During `prefers-reduced-motion: reduce`, continuous and decorative animations stop, and transitions are shortened without disabling visible focus, hover, and state changes.

## Quality gates

From `apps/web`, `bun run lint`, `bun run type-check`, `bun run test`, `bun run build`, `bun run test:e2e`, and `bun run audit` are executed. Visual checks include desktop/mobile, keyboard, reduced motion, and absence of footer overlap. Lighthouse is run against the production build, not the dev server.
