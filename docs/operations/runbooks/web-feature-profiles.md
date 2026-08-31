---
description: "Building, verifying, and rolling back web deployment profiles."
last_verified: "2026-08-29"
---

# Web deployment profiles

The canonical contract belongs to `SPEC-046`; the architecture decision is `ADR-0089`.

Before 2026-08-29 this page named two other identifiers, neither of which owned
this subject: one belongs to CLI publication and access reports, while the
other belongs to the runner class used for checks and does not exist in the
public tree. The line intended to identify the source of truth pointed to
documents that said nothing about profiles.
Profiles are build-time configuration for an exact standalone artifact, not a
runtime feature service.

`public_saas` is the default site-build profile. This is fixed in
`apps/web/config/features.yaml`, dev Compose, and the `just web-build` recipe;
the production Dockerfile and production Compose also explicitly use
`public_saas`. `self_hosted` is enabled only by an explicit
`AI_STP_WEB_PROFILE=self_hosted` override.

## Profiles

- `public_saas` — public SaaS: content hub, contact, and legal pages are enabled;
- `self_hosted` — packaged distribution: catalog, documentation, and account
  surface without SaaS content, contact, or public policy pages.

The complete value set lives in `apps/web/config/features.yaml`. A new key must
not be added without an owner, issue, consumer, and test.

## Local verification

```bash
cd apps/web
# Default site artifact: public SaaS.
AI_STP_WEB_PROFILE=public_saas bun run build
AI_STP_WEB_PROFILE=self_hosted bun run build
bun run test:feature-profiles
```

Build overrides accept only exact `true`/`false` values:

```bash
AI_STP_FEATURE_CONTENT_HUB=false bun run build
AI_STP_FEATURE_SAAS_PUBLIC_PAGES=false bun run build
AI_STP_FEATURE_CATALOG_USAGE_METRICS=true bun run build
```

`public_saas` enables `catalog_usage_metrics`; `self_hosted` leaves it disabled.
An override does not enable server-side counter writes and does not replace the
attribution/terms gate in `SPEC-050`. An API null is not displayed as zero.

After a profile change, restart the dev server completely. A value changed only
in the runtime environment of an already built image does not change the artifact.

## Result verification

For `public_saas`, human and machine content/contact/legal routes, `/feed.xml`,
navigation, sitemap, and `llms.txt` contain SaaS surfaces. Under `self_hosted`,
those route trees and the feed return 404, and links and discovery entries are
absent. A disabled human surface and its machine pair both return 404. The
`test:feature-profiles` command builds both profiles sequentially without
Docker and verifies the standalone server at `127.0.0.1:3100` through
Playwright. The unit inventory gate matches every human `page.tsx` against the
machine registry (`SPEC-036`).

## Rollback

Roll back by deploying the previous exact image or by producing a new
`self_hosted` build. Do not change the profile inside an already built container
or substitute static assets from another build.
