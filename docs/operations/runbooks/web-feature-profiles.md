---
description: "Building, verifying, and rolling back web deployment profiles."
last_verified: "2026-09-14"
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
- `corporate_hub` — corporate workspace, without editorial, regional services,
  Company, or Legal navigation and pages.

Public-only pages use `page.content.tsx`, `page.saas.tsx`, or `page.regional.tsx`; the editorial layout
and feed use matching gated extensions. `next.config.ts` enables these extensions
only for the corresponding compiled features; regional pages are omitted only
from corporate builds, retaining their existing packaged surface. Disabled page modules are omitted
from route discovery and compilation, not merely rendered as 404. The generic
machine route still denies their paths through the feature gate and middleware.
Corporate builds enable Next's native `skipMiddlewareUrlNormalize` setting to
keep middleware from reconstructing excluded machine targets; other profiles
leave it disabled.
Corporate builds reject overrides that reenable editorial or SaaS-public pages.
The standalone packager reads baked features from `required-server-files.json`
and copies only enabled Markdown trees and public assets. Corporate retains
`docs-user-facing/docs` but omits `content`, `legal`, and `public/content`.
Docker uses that packaged tree rather than copying the full public source again.
Feature-profile verification checks route manifests and packaged directories;
Playwright reads the artifact's Markdown instead of the source checkout.

Local context is the CLI's local environment, not the `self_hosted` website
profile: it has no website deployment. Do not introduce a local website build.
`AI_STP_WEB_PROFILE=local` is rejected as an unknown profile; local mode is
CLI-only and produces no web artifact. This deployment boundary does not remove
the public anonymous browsing session's local capability projection.
The development Compose web service mounts the single canonical corporate
overview fixture read-only at `/packages/contracts/src/ai_stp_contracts/fixtures/v1/corporate-overview.json`;
the app source is flattened at `/app`, so do not mount or copy the full packages tree.
Corporate shell and account-drawer links use `/corporate/` for shared catalog
and account pages. Middleware redirects legacy shared URLs and rewrites the
prefixed URLs to the incumbent pages, preserving queries and session gates.
Organization, Admins, and Landscape routes retain their existing handlers.
Consent controls remain available without linking to disabled legal pages.
The header uses the navigation drawer below the desktop breakpoint.

The complete value set lives in `apps/web/config/features.yaml`. A new key must
not be added without an owner, issue, consumer, and test.

## Local verification

Corporate profile editors upload raw bytes through the same-origin
`/api/corporate/organizations/{organizationId}/profiles/{kind}/{id}/media` BFF.
It forwards the canonical `/v1/corporate/.../profiles/.../media` API request
after session, CSRF, typed-target, revision, MIME, and size validation. Uploads
produce ready asset references; saving the profile is a separate mutation.
Processed public assets remain served by the API under `/v1/media/avatars/`.
Production nginx owns this path split. Real development API rewrites run before
filesystem fixture routes; mock development retains local fixture delivery.
The synthetic media handler is enabled only with `AI_STP_USE_MOCKS=true` and is
not evidence of production storage, tenant authorization, or processing.

```bash
cd apps/web
# Default site artifact: public SaaS.
AI_STP_WEB_PROFILE=public_saas bun run build
AI_STP_WEB_PROFILE=self_hosted bun run build
AI_STP_WEB_PROFILE=corporate_hub bun run build
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
The `test:feature-profiles` command builds all three profiles sequentially
without Docker and verifies the standalone server at `127.0.0.1:6767` through
Playwright. The unit inventory gate matches every human page, including gated
extensions, against the machine registry (`SPEC-036`).

## Rollback

Roll back by deploying the previous exact image or by producing a new
`self_hosted` build. Do not change the profile inside an already built container
or substitute static assets from another build.
