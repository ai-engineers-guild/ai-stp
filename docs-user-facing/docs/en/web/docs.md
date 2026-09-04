---
title: "This documentation"
description: "Where the help center is served and how it relates to /docs on the web and on the API host."
---

# This documentation

Three different `/docs` surfaces exist. They do not share a host, a
renderer, or a contract. Mixing them is the usual way to open OpenAPI
when you wanted a how-to, or a help article when you wanted a schema.

## URLs and who can see them

| Surface | Typical URL | Who can see it | What it is |
| --- | --- | --- | --- |
| MkDocs help center | `http://localhost:8011/` (RU), `http://localhost:8011/en/` (EN) | anyone | this documentation, built from `docs-user-facing/docs/` |
| Web projection | `/{locale}/docs` and `/{locale}/docs/{slug…}` | anyone | the same Markdown, rendered inside the website |
| Web machine docs | `/{locale}/ai/docs` and `/{locale}/ai/docs/{slug…}` | anyone | Markdown projection of that page |
| API OpenAPI | `{API host}/docs` | anyone who can reach the API | Swagger UI for HTTP contracts |
| API ReDoc | `{API host}/redoc` | anyone who can reach the API | ReDoc for the same OpenAPI |
| OpenAPI JSON | `{API host}/openapi.json` | anyone who can reach the API | the machine schema |

In development the same process serves both language lines at
`http://localhost:8011` (`AI_STP_USER_DOCS_URL`): Russian at `/` and
English at `/en/`. That is not a live `mkdocs serve` of one
`docs_dir` — English on that host is not a 404. The website is a
different origin. The API is a third origin; in development that is
commonly `http://localhost:8000`. Production puts the help center on
its own host (`AI_STP_DOCS_HOST`) and keeps `/docs` on the API host for
OpenAPI.

The header label **Documentation** is an **external** `docsHref`. It
always points at `AI_STP_USER_DOCS_URL`, never at `/{locale}/docs` and
never at the API. The Human / Machine switch does not rewrite that
link: external targets stay external.

Anyone may read the help center. There is no session gate. Search is
local to the MkDocs build or to the website docs search box.

## What this screen is for

Use the help center to learn the product path: install the CLI, read a
catalog card, understand trust axes, recover from a refusal.

Use `/{locale}/docs` when you are already on the website and want the
same articles without leaving the origin. The source files are the
same. The chrome is the website header, footer, and projection switch.

Use `{API host}/docs` only when you are implementing or debugging the
HTTP API. It is not written for a person choosing a setup.

This page does **not**:

- generate OpenAPI;
- import ADRs or `specs/active/` into the public tree;
- let you edit Markdown in the browser;
- replace `ai-stp help --agent --json` as the command parser.

Internal engineering docs stay in repository `docs/`. Public pages
link there only when the reader needs the owner of a rule.

## What is on the MkDocs site

Material for MkDocs, two language builds.

| Control | What it does |
| --- | --- |
| Search | indexes the built language line |
| Left nav | Overview, Quickstart (people / agents), Harnesses, Concepts, Catalog, CLI, Web, Components, Setups, Publishing, Trust and safety, Troubleshooting |
| Language alternate | Русский at `/`, English at `/en/` |
| Theme toggle | light / dark from `prefers-color-scheme` |
| Edit link | GitHub `edit/main/docs-user-facing/docs/{locale}/…` |

Russian is built at the site root. English is built into `/en/`.
Reversing that order would wipe English on every Russian build.

The Web chapter you are in is the map of the **website**, not of the
CLI. CLI pages live under [CLI](../cli/index.md).

## What is on `/{locale}/docs`

The website loads `docs-user-facing/docs/**/*.md` through Fumadocs.
`/{locale}/docs` is the index of that locale. Nested slugs follow the
directory tree: `/{locale}/docs/web/catalog` is this chapter's catalog
page.

| Control | What it does |
| --- | --- |
| Search documentation | filters titles in this locale |
| Documentation sections | nested tree from `.pages`, the same structure as MkDocs |
| Article body | title, description, rendered Markdown |

A missing slug 404s. There is no draft flag on help pages: if the file
is in the tree, it is served. Content-hub drafts are a different
store; see [Content](content.md).

Machine `/{locale}/ai/docs/…` is the same article as Markdown. It is
still not OpenAPI.

## The three `/docs` compared

| Question | MkDocs `:8011` | Website `/{locale}/docs` | API `/docs` |
| --- | --- | --- | --- |
| Source | `docs-user-facing/docs/` | the same files | generated OpenAPI |
| Locale | separate builds | `[locale]` prefix | not a help locale |
| Chrome | Material | website header | Swagger / ReDoc |
| Header Documentation | this host | not this target | not this target |
| Human / Machine | no (MkDocs theme only) | yes | no |
| Tells you how to install | yes | yes | no |
| Tells you the HTTP schema | no | no | yes |

Bookmark the MkDocs host for reading. Bookmark the API host for
clients. Do not assume a reverse proxy collapsed them: the API path
`/docs` is reserved and is not the help center (`ADR-0078`).

## Matching CLI commands

There is no `ai-stp docs` command. Machine help is:

```bash
ai-stp help --agent --json
```

That envelope is the command registry of **this** install. Flags,
schemas, and `next_actions` are not copied into Markdown. If a help
page and the CLI disagree, follow the CLI.

Canonical web links from a shell:

```bash
ai-stp link web --json
```

`link web` prints a round-trippable website URL. It does not open
MkDocs and does not open OpenAPI.

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| `localhost:8011` refused | the docs compose service is not up | start it, or use `/{locale}/docs` on the website |
| `/{locale}/docs/…` 404 | no Markdown at that slug | open the docs index or MkDocs nav |
| Header Documentation leaves the site | that is the external `docsHref` | expected |
| Swagger UI at `/docs` on the API host | you opened OpenAPI | go to `:8011` or `/{locale}/docs` for how-tos |
| English missing on `:8011/` | you are on the Russian root | open `:8011/en/` |
| Search finds no CLI flag | help pages are not the parser | run `ai-stp help --agent --json` |
| Edit on GitHub 404s | you are not on `main` or lack access | read the built page; do not paste secrets into a PR |

Self-hosted websites still compile this Markdown. They may point
`AI_STP_USER_DOCS_URL` at an internal host. The API OpenAPI path does
not move with that setting.

## Related pages

- [Web map](index.md) — which website section is which.
- [Home](home.md) — where the install command is copied.
- [Catalog](catalog.md) — the other public surface agents read.
- [Quickstart](../quickstart/index.md) — choose the human path or the
  agent path.
- [Quickstart for people](../quickstart/human.md) — first commands after
  install.
- [Quickstart for agents](../quickstart/agent.md) — session ritual.
- [CLI](../cli/index.md) — envelopes and mutability.
- [Command map](../cli/commands.md) — one row per command.
- [Trust and safety](../trust-and-safety/index.md) — what “verified”
  does not mean.

!!! note "Source of truth"
    Public how-tos live in `docs-user-facing/docs/`. Architecture and
    requirements live in `docs/` and `specs/active/`. The CLI binary
    owns flags. OpenAPI owns HTTP. Four owners, four places.
