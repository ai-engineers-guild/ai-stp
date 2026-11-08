---
description: "Shared product tokens and interface boundaries."
last_verified: "2026-11-08"
---

# Product design

The executable design sources are `apps/web/src/theme/tokens.json`, theme icons
and `apps/web/src/components/{atoms,molecules,organisms,layouts,screens}`.
Read [web DESIGN](../../apps/web/DESIGN.md) before changing an interface.

Desktop projects the same product tokens into `apps/desktop/src/generated/theme.*`
with `just desktop-gen`. The token file's `platform.desktop` group owns its small-
control contrast and multilingual font overrides; unspecified roles inherit the
product values. Do not edit generated CSS or duplicate color, type and icon scales.
Pinned local IBM Plex and Noto assets cover the five Desktop interface languages.

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
