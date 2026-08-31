---
description: "Decision: web deployment surfaces are controlled by build-time Git/YAML profiles."
last_verified: "2026-08-12"
---

# ADR-0089: Build-time web feature profiles

Status: accepted.

## Context

Issues `#267` and `#284` require entire web surfaces to be disabled in routes,
navigation, the sitemap, the machine projection, and, where possible, client
bundles. The web application already uses the Next.js App Router, a standalone
image, and separate human/machine route trees. A runtime flag cannot
simultaneously change an already-built client bundle, preserve static
generation, and guarantee a single artifact identity.

## Options

1. An external flag platform. It provides audience selection and auditing, but
   adds a service, SDK, failure modes, and dependency without an MVP need.
2. A runtime env/config endpoint. It permits changing a flag without a build,
   but leaves code in the artifact, creates hydration/cache divergence, and
   turns static pages into dynamic rendering.
3. Versioned YAML profiles resolved at build time. They are simple, Git-native,
   verifiable, compatible with a standalone artifact, and provide bundler
   literal constants.

## Decision

Option 3 is accepted. The TypeScript registry owns keys and metadata; YAML owns
complete profile values. The profile and Boolean overrides are read only during
the build. Unknown or incomplete configuration is rejected immediately. The
result is embedded as constants and forms part of the image identity.

A feature flag is not an authorization check. Human and machine routes check one
built set; navigation, SEO, and machine discovery are projections of the same
route/feature annotations. The `public_saas` and `self_hosted` profiles are
complete product sets. The `content_hub` and `saas_public_pages` keys control
content and SaaS service pages; new keys are added only with a real consumer and
a test.

The content hub uses repository Markdown and the existing Fumadocs local source,
without an external CMS. There is no locale fallback: RU/EN entries form strict
pairs.

## Consequences

- Different exact web images are built for different profiles.
- Changing a profile requires rebuild/redeploy, while keeping the artifact
  deterministic.
- Operational emergency shutdown, user cohorts, and a remote provider are
  deferred until a demonstrated need and will require a new ADR.
- Every new route must annotate its feature in human/machine/discovery
  projections.
- The build matrix and scenario tests become release evidence.

## Reconsideration conditions

The decision is reconsidered if an operational need is demonstrated to disable a
surface without a rebuild faster than the permitted rollback, or if per-request
cohorts appear. Structural build flags then remain, while operational flags are
introduced as a separate category that does not promise bundle exclusion.
