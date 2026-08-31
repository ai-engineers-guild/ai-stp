---
description: "Decision to maintain public user documentation separately from internal docs/ and build it with MkDocs Material."
last_verified: "2026-08-10"
---

# ADR-0077: Public user documentation

Status: accepted.

## Context

`docs/` in the repository is already the internal normative corpus: ADRs,
active specifications, contracts, and engineering and operational rules. The
agent reads it before making changes, and mixing the product help center into
it makes both use cases worse: users have to see internal implementation
details, while the agent has more difficulty distinguishing rules from
explanatory text.

At the same time, the MVP needs a separate, readable public docs site: plain
Markdown in the repository, proper navigation, search, a static build, and
minimal operational cost. The stack must be neither Vue nor a separate,
complex frontend application solely for documentation.

## Options

1. Keep public documents in `apps/web/content` and render them with Next.js.
   This retains a single web runtime, but continues mixing product documentation
   with the application and requires more custom UI.
2. Maintain public documents in `docs/`. This is simpler for tooling, but breaks
   the boundary of the internal normative corpus.
3. Introduce `docs-user-facing/docs/` as a separate Markdown source and build it with a
   second MkDocs Material configuration.
4. Introduce Docusaurus, Fumadocs, or Astro Starlight. These stacks suit a richer
   docs portal, but add an unnecessary JavaScript/runtime layer and a new
   maintenance model to the MVP.

## Decision

Option 3 is accepted. Public user documentation lives in `docs-user-facing/docs/` and is
built with the separate `docs_scripts/user-mkdocs.yml` configuration. Internal
`docs/` remains the source of normative documents and does not become a help
center.

The first MVP site is Russian-language, static, and built with the same Python
docs toolchain as the internal site. Markdown remains the primary format; MDX,
runtime components, and an in-browser editor are outside this decision.

## Consequences

- `docs-user-facing/docs/` becomes the source for public user guide pages: quick start,
  concepts, CLI, catalog, components, setups, publication, trust, security, and
  troubleshooting.
- Building public docs requires no new lock file and uses the already pinned
  dependencies of the docs group.
- Production may serve the `user-docs` artifact as a static site through a
  separate container or Caddy route. The Web/API import revision from `SPEC-031`
  reads `docs-user-facing/docs/` as its technical source.
- Any future migration to Docusaurus, Fumadocs, or Starlight requires a new ADR
  because it changes the runtime and maintenance model of public documentation.

## Reconsideration conditions

The decision is reconsidered if user documentation requires interactive
playground components, versioning by major line, a full bilingual locale
pipeline, API reference with live examples, or authenticated docs pages that
static MkDocs Material cannot provide without complex customization.
