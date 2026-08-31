---
title: Publishing and authoring
description: "Prepare repository-backed components and setups for publication."
---

## Publishing content-hub entries

The content hub is Git-native. Add one Markdown file per locale under
`docs-user-facing/content/en` and `docs-user-facing/content/ru`. Both files must use the same `type` and
`slug`. Supported types are `article`, `blog_post`, `changelog`, and
`release_notes`. Unknown fields, duplicate identities, future dates, missing
translations, and malformed slugs fail the build. Set `draft: true` to keep an
entry out of routes, feeds, and indexes.

Use `AI_STP_WEB_PROFILE=public_saas` to include the hub and `self_hosted` to omit its
public surface. Run `bun run test:feature-profiles` before publishing changes.

Every public content, contact, and policy page has two equal projections. The human
URL is `/{locale}/...`; the machine URL is `/{locale}/ai/...`. The fixed Human/Machine
switch preserves the locale, current route, and query string. New public routes must
implement both projections from the same source and keep the switch available.

Published versions come from a public GitHub repository at an exact commit and subpath. Validate locally, review the generated passport, then publish through the CLI. Secrets, private paths, caches, and generated output must never enter a passport.
