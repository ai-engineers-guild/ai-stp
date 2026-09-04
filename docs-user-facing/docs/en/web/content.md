---
title: "Content hub"
description: "Articles, blog posts, changelog, and release notes on the website."
---

# Content hub

Content is the website's publication stream: field notes for safer
setups, plus an exact record of what changed. It is not the help
center, not the catalog, and not OpenAPI.

The feature flag is `content_hub`. The public SaaS profile turns it on.
Self-hosted turns it off: the header and footer omit Content, and the
routes 404.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human index | `/{locale}/content` | anyone, if flagged |
| Machine index | `/{locale}/ai/content` | anyone, if flagged |
| Human entry | `/{locale}/content/{type}/{slug}` | anyone, if published |
| Machine entry | `/{locale}/ai/content/{type}/{slug}` | anyone, if published |

`{type}` is one of:

| Type key | Index label |
| --- | --- |
| `article` | Article |
| `blog_post` | Field note |
| `changelog` | Changelog |
| `release_notes` | Release notes |

Those four keys are the closed set. A fifth type 404s.

Entries are localized: English and Russian files share `type` and
`slug`. Anyone may read a **published** entry. There is no session
gate, no like, and no comment thread.

**Drafts 404.** A file with `draft: true` is parsed in the repository
and never listed, never routed, never machine-projected. Internal
drafts are not a preview URL.

## What this screen is for

Use Content to read product writing that is not a command reference:

- how to keep a trust boundary visible;
- what changed in the registry;
- release notes for a numbered line.

Use the [help center](docs.md) for how-to pages that track the CLI and
the website. Use the [catalog](catalog.md) for objects you might
install.

Content does **not**:

- publish a component;
- change a legal policy (that is [Legal](legal.md));
- accept user submissions in the browser;
- show future `published_at` dates (those fail the snapshot).

## What is on the screen

### Index

| Element | Content |
| --- | --- |
| Title | Content |
| Description | Field notes for building safer coding-agent setups, plus an exact record of what changed. |
| Publication types | the four type labels |
| Featured | newest published entry, large |
| Latest publications | the rest, newest first |

Each row shows type, `published_at` (ISO date), title, description.
**Read publication** opens `/{locale}/content/{type}/{slug}`.

An empty index (no published entries in this locale) still renders the
header and an empty latest list. That is a typed empty, not a 404.

### Entry

| Element | Content |
| --- | --- |
| Back | ← Content |
| Type | Article / Field note / Changelog / Release notes |
| Date | `published_at` |
| Title | frontmatter title |
| Description | frontmatter description |
| Tags | up to twelve strings |
| Body | Markdown; images from `/content/illustrations/…` |

Human / Machine switch keeps type and slug. Machine index lists titles
and URLs. Machine entry is the article as Markdown.

JSON-LD is emitted for crawlers. It is not a passport.

## Matching CLI commands

There is no content-hub CLI. Catalog and help remain:

```bash
ai-stp registry search --json
ai-stp help --agent --json
ai-stp link web --json
```

`link web` can print a canonical website URL when the target is a
supported kind. Content slugs are not catalog `stable_id`s. Do not
pass an article slug to `registry show`.

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| Header has no Content | `content_hub` off | use MkDocs and Catalog |
| `/{locale}/content` 404 | flag off, or path typo | [Web map](index.md) |
| Entry 404 | unknown type/slug, other locale, or **draft** | open the index; do not guess drafts |
| Empty latest list | nothing published in this locale | switch locale or wait |
| Image missing | illustration not in the snapshot | the article still reads |
| Search on MkDocs finds the topic | help center is a different tree | that is expected |
| Cannot comment | no comments | file a [Report](reports.md) on an object, or [Contact](contact.md) |

Draft files exist in `docs-user-facing/content/` for authors. They are
not a public preview. Asking for `?draft=1` does not unhide them.

## Content vs docs vs legal vs catalog

| Tree | URL | Mutability | Drafts |
| --- | --- | --- | --- |
| Content hub | `/{locale}/content/{type}/{slug}` | published snapshot | 404 |
| Help center | MkDocs and `/{locale}/docs` | git-published Markdown | no draft flag |
| Legal | `/{locale}/legal/{slug}` | immutable policy revision | n/a |
| Catalog | `/{locale}/catalog/…` | immutable object `X.Y` | unpublished 404 |

Types are closed. `blog_post` is labelled Field note in the UI; the
path still says `blog_post`. Do not invent `tutorial` or `rfc`.

Locale parity: a published English entry has a Russian twin with the
same type and slug, and the reverse. Switching `en` ↔ `ru` in the
header keeps type and slug.

Machine content is the article body. It is not a passport and not
OpenAPI.

## Related pages

- [This documentation](docs.md) — how-tos versus field notes.
- [Catalog](catalog.md) — objects, not articles.
- [Legal](legal.md) — versioned policies, not changelog.
- [Home](home.md) — product landing, not a blog index.
- [Publishing](../publishing/index.md) — publishing **components**.
- [Trust and safety](../trust-and-safety/index.md) — themes the
  articles often return to.

!!! note "Four types, one hub"
    `article`, `blog_post`, `changelog`, and `release_notes` share a
    listing. They are not four websites. Kind `skill` is a component,
    not a content type.
