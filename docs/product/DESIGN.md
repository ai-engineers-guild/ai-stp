---
description: "Shared web component, typography and theme boundaries."
last_verified: "2026-10-15"
---

# Web design

The executable design sources are `apps/web/src/theme/tokens.json`, theme icons
and `apps/web/src/components/{atoms,molecules,organisms,layouts,screens}`.
Read [web DESIGN](../../apps/web/DESIGN.md) before changing an interface.

Use registered components and tokens. Adapt an existing component first; creating
a new one requires a concrete gap, a Storybook story and a component test.
Raw select/table primitives and Radix imports belong inside their owning kit files.

IBM Plex Sans (`plexSans`) and IBM Plex Mono (`plexMono`) are the current self-hosted typefaces. Use theme
font tokens rather than another literal stack. Color, spacing and radius values
come from the token file, not a second table in prose.

Human/machine presentation and light/dark theme are independent. Preserve keyboard
access, visible focus, readable errors, localization and responsive layout through
the existing component and page tests. Machine views carry structured content;
the CLI remains the business engine.
