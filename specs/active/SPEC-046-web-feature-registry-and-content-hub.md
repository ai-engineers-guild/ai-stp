---
description: "SPEC-046: Typed web deploy profiles and a disableable content hub."
last_verified: "2026-08-29"
---

# SPEC-046: Web feature registry and content hub

## Purpose

Web receives a single typed registry of deploy surfaces. A disabled surface
simultaneously disappears from human and machine routes, navigation, sitemap, discovery,
and client entry points, while an unknown or incomplete configuration stops the build.
The registry's first consumer is the content section with articles, blog posts, changelog,
and release notes in Russian and English; its repository and staff authoring sources
are published through a single platform contract under `SPEC-054`.

## Scope

Included: versioned YAML deployment profiles, build-time environment overrides, strict
validation, typed keys, human/machine route gates, shared navigation, sitemap/robots,
`llms.txt`, Atom, four content types, and production build scenarios for enabled and
disabled profiles.

Excluded: user groups, percentage rollouts, A/B tests, remote polling, admin UI, a
database or Redis for flags, runtime enablement after the build, permission/authz,
and an external CMS.

## Terms

- `Feature key` — a stable typed identifier of a deploy surface.
- `Deploy profile` — a complete set of boolean values for all feature keys.
- `Compiled features` — the result of selecting a profile and build overrides,
  embedded in the exact web artifact.
- `Feature consumer` — a route, navigation item, discovery entry, or another area
  whose observable behavior is changed by a key.
- `Content hub` — a public surface with the `article`, `blog_post`, `changelog`,
  and `release_notes` types; authoring and serving belong to `SPEC-054`, while
  feature gating belongs to this specification.

## Requirements

- `REQ-4601`: `apps/web/config/features.yaml` has `schema_version`,
  `default_profile`, and a complete set of profiles. Unknown fields, profiles, feature
  keys, duplicate keys, missing keys, and non-boolean values are rejected before the
  Next build.
- `REQ-4602`: Allowed feature keys belong to the TypeScript registry. YAML stores
  only profile values and does not create new keys.
- `REQ-4603`: `AI_STP_WEB_PROFILE` selects the profile at build time. An explicit
  `AI_STP_FEATURE_<KEY>` with the value `true` or `false` takes precedence; an unknown
  override or an invalid override value causes the build to fail.
- `REQ-4604`: The compiled feature set is part of the web artifact's identity.
  The runtime environment cannot enable a surface absent from the artifact or change
  the profile after `next build`.
- `REQ-4605`: A disabled human surface returns a real HTTP 404 and receives
  `noindex`; its link is absent from the header, footer, and keyboard navigation before
  hydration.
- `REQ-4606`: The machine route for the same disabled surface returns 404. Human and
  machine navigation are built from one model and filtered by the same feature set.
- `REQ-4607`: Sitemap, robots, `llms.txt`, `llms-full.txt`, RSS/Atom, and other
  discovery surfaces do not publish the disabled section.
- `REQ-4608`: The server-only loader and YAML parser are not included in the client
  bundle. Client components receive only safe compiled booleans or already filtered
  navigation items.
- `REQ-4609`: Every declared feature key has an owner, an issue, and at least one
  verifiable consumer; dormant keys are prohibited.
- `REQ-4610`: `content_hub` is the first key. When enabled, index and detail pages
  are available for `article`, `blog_post`, `changelog`, and `release_notes`, with
  one example of each type and locale.
- `REQ-4611`: A content entry has a type, slug, locale, title, description,
  publication date, tags, draft flag, and body. Unknown fields, duplicate
  `(locale,type,slug)` tuples, future/invalid dates, and drafts in the public projection
  are rejected or excluded deterministically.
- `REQ-4612`: Content routes have canonical, hreflang, Open Graph, and an appropriate
  JSON-LD type. Draft/internal entries are not indexed and return 404.
- `REQ-4613`: The content index and detail pages have meaningfully distinct machine
  projections built from the same source, while links remain within the machine URL
  of the same locale.
- `REQ-4614`: RSS contains only published entries from the enabled content hub,
  uses absolute canonical URLs, and contains no secrets, private data, or drafts.
- `REQ-4615`: The production scenario builds two standalone artifacts: `public_saas`
  returns human/machine 200 and includes nav/sitemap/feed entries; `self_hosted`
  returns human/machine 404 and omits all discovery/navigation entries.
- `REQ-4616`: RU/EN have identical types and slugs or an explicit fallback policy.
  The MVP uses strict pairs without automatic fallback.
- `REQ-4617`: The registry contains exactly two product profiles: `public_saas`
  enables `content_hub` and `saas_public_pages`, while `self_hosted` disables them.
  In the second profile, contact and legal are absent from human/machine routes, header,
  footer, keyboard navigation, sitemap, and robots.
- `REQ-4618`: When `content_hub` is enabled, human, machine, and discovery consumers
  read a single active article set from the platform under `SPEC-054`; under the
  disabled profile, web does not request this set and preserves the complete
  404/absence contract.

## States and errors

A configuration error is a build failure that names the field/profile/key without
printing the complete environment. An unknown content type or slug returns 404. A
disabled surface does not degrade to an empty page or `200 noindex`.

## Security and privacy

Feature flags are not authz and do not bypass API authorization. YAML and Markdown
are repository-owned bounded input. Raw HTML and unsafe URLs are not published.
Environment values, cookies, OAuth tokens, and private entries are not included in
generated metadata, feeds, logs, or client bundles.

## Compatibility and migration

Existing human/machine URLs are preserved; the API is extended additively under
`SPEC-054`. Rollback selects a profile without `content_hub` or restores the previous
exact image; changing the built feature set at runtime does not take effect. Removing
a key requires simultaneously removing all consumers and profile values.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-4601` | Unit tests reject incomplete YAML, unknown fields, and invalid values. |
| `REQ-4602` | A registry test proves that YAML cannot declare a new key. |
| `REQ-4603` | Unit tests verify profile selection, override precedence, and failure on an invalid value. |
| `REQ-4604` | Two separate production builds retain the selected state after startup. |
| `REQ-4605` | Playwright verifies HTTP 404, `noindex`, and the absence of the link from the initial HTML. |
| `REQ-4606` | Playwright verifies machine 404, while a navigation test verifies the shared model. |
| `REQ-4607` | Playwright verifies sitemap, robots, `llms.txt`, `llms-full.txt`, and Atom under both profiles. |
| `REQ-4608` | Production bundle analysis does not find the YAML parser or server loader in client chunks. |
| `REQ-4609` | Static consumer coverage test. |
| `REQ-4610` | A source test confirms all four types in both locales. |
| `REQ-4611` | Source unit tests verify schema, uniqueness, dates, and drafts. |
| `REQ-4612` | A browser scenario verifies metadata, JSON-LD, and a draft's 404 response. |
| `REQ-4613` | A browser scenario compares human and machine index/detail pages generated from one source. |
| `REQ-4614` | An Atom test verifies that only published entries are included and that canonical URLs are absolute. |
| `REQ-4615` | Two sequential standalone builds using one scenario suite. |
| `REQ-4616` | Locale parity test for the content registry. |
| `REQ-4617` | Two local production builds and Playwright verify the SaaS and self-hosted surfaces. |
| `REQ-4618` | Profile E2E verifies the shared platform fixture across human/machine/discovery under the enabled profile and the absence of fetches/routes/links under the disabled profile. |
