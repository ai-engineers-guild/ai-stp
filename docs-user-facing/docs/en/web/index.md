---
title: "Web"
description: "What the website does, what it does not apply, and where each section lives."
---

# Web

The website is the public catalog and the account. It shows setups and
components, publisher pages, legal revisions, and the signed-in workspace.
It does not assemble a setup, write a harness target, or call a model.

The working surface for selection, checks, and installation is the CLI plus
the harness provider. Read the catalog here; apply a plan there.

```text
Website → catalog evidence, account, publication confirm
CLI     → passports, select, install plan
Provider → native harness state
```

## URLs and who can see them

Every page has two projections of the same facts. `{locale}` is `en` or `ru`.

| Projection | Pattern | Who it is for |
| --- | --- | --- |
| Human | `/{locale}/…` | a person in the browser |
| Machine | `/{locale}/ai/…` | an agent reading Markdown |

The fixed **Human** / **Machine** switch at the bottom of the viewport keeps
the path, query string, and locale. It does not change access: a private
machine URL still needs the same session cookie as the human twin.

Anonymous visitors can open Home, Catalog, Regional services, Publishers,
Content (when `content_hub` is on), this help center, Contact and Legal (when
`saas_public_pages` is on), and Sign-in. Signed-in visitors also get Account,
Profile, Devices, Objects, Access, Reports, Likes, Onboarding, and
Publication plans.

A signed-out request to a private URL is sent to
`/{locale}/login?returnTo=…`. An expired cookie is cleared first and lands
on login with `reason=session_expired`. A new account with
`onboarding_pending` is sent to Onboarding before any other private page.

## What this surface is for

Use the website to:

- install the CLI from the landing command;
- search the public catalog and read a passport;
- like, share, or report a published version;
- sign in with Google or GitHub and link a CLI device;
- edit a public profile and privacy flags;
- confirm a publication plan the CLI already built;
- invite or revoke major-line access;
- file a report against an exact version digest.

Do not use the website to:

- compose, pin, or apply a setup;
- write files into Claude Code, Codex, Grok Build, or any other harness;
- run safety scanners (those run on publication, not in the browser);
- merge two accounts;
- open staff moderation (`/staff/reports` is not a user page).

## What is on every screen

The human header is sticky. It always shows Home (the `ai_stp` mark),
Catalog, Regional services, and Documentation. Documentation is an
**external** link: the MkDocs help center from `AI_STP_USER_DOCS_URL`
(in development, `http://localhost:8011`). It is not rewritten into a
projection.

When `content_hub` is compiled in, Content appears in the header. When
`saas_public_pages` is compiled in, Contact appears (shortcut `C`). After
sign-in, Objects, Access, Reports, and Devices move into the account menu
together with Profile, My likes, and Sign out. Shortcut `P` opens Account
or Sign-in. `Ctrl`/`Cmd` `K` focuses catalog search when that page is open.

The footer repeats Catalog, Regional services, Documentation, and Content,
then (in the public SaaS profile) Contact, Privacy, Cookies, Service rules,
and Licensing. `llms.txt` is a machine index, not a help article.

Theme (light / dark / system) and locale (`en` ↔ `ru`) sit in the header.
Locale changes the path prefix only; identifiers, field names, Catalog QL
tokens, and CLI commands stay Latin.

The machine header renders the same navigation as Markdown links, plus
`llms.txt` and a locale `<select>`. Shortcuts are printed in the machine
footer.

## Feature flags

The public SaaS profile turns `content_hub` and `saas_public_pages` on.
A self-hosted profile turns both off: Content, Contact, and the legal
footer columns disappear. Catalog, account, and the CLI path remain.

## Map of web sections

| Help page | Human URL | Visible to | What it is |
| --- | --- | --- | --- |
| [Home](home.md) | `/{locale}/` | anyone | landing, CLI install, catalog entry |
| [Catalog](catalog.md) | `/{locale}/catalog` | anyone | search, Catalog QL, Both-mode |
| [Component card](catalog-component.md) | `/{locale}/catalog/components/{stable_id}` | anyone | one public component |
| [Setup card](catalog-setup.md) | `/{locale}/catalog/setups/{stable_id}` | anyone | one public setup and its pins |
| [Regional services](services.md) | `/{locale}/services` | anyone | CIS atlas into catalog filters |
| [Publishers](publishers.md) | `/{locale}/publishers/{account_id}` | anyone | public publisher page |
| [Content](content.md) | `/{locale}/content` | anyone, if flagged | articles and notes |
| [This documentation](docs.md) | MkDocs host and `/{locale}/docs` | anyone | this help center |
| [Contact](contact.md) | `/{locale}/contact` | anyone, if flagged | stored message, no secrets |
| [Legal](legal.md) | `/{locale}/legal/{slug}` | anyone, if flagged | versioned policies |
| [Sign-in](login.md) | `/{locale}/login` | anyone | OAuth and device code |
| [Account](account.md) | `/{locale}/account` | signed-in | id, identities, privacy |
| [Profile](profile.md) | `/{locale}/account/profile` | signed-in | public display, not a passport |
| [Devices](devices.md) | `/{locale}/devices` | signed-in | browsers and CLI installs |
| [Objects](objects.md) | `/{locale}/objects` | signed-in | owned components and setups |
| [Access](access.md) | `/{locale}/access` | signed-in | invitations and grants |
| [Reports](reports.md) | `/{locale}/reports` | signed-in | your cases, not staff triage |
| [Likes](likes.md) | `/{locale}/likes` | signed-in | saved catalog objects |
| [Onboarding](onboarding.md) | `/{locale}/onboarding` | pending account | service rules and consent |
| [Publication](publications.md) | `/{locale}/publications/{plan_id}` | signed-in | confirm a CLI-built plan |

Exact version pages hang off the object they belong to:

- `/{locale}/catalog/components/{stable_id}/versions/{version}`
- `/{locale}/catalog/setups/{stable_id}/versions/{version}`
- `/{locale}/objects/{kind}/{stable_id}/versions/{version}`

Country and service detail pages hang off Regional services:

- `/{locale}/countries/{code}`
- `/{locale}/services/{canonical_domain}`

Device approval also lives at `/{locale}/device-login`. Invitation accept
lives at `/{locale}/invitations/{invitation_id}`. Profile preview lives at
`/{locale}/account/profile/preview`. Privacy lives at
`/{locale}/account/privacy`. Presentation edit lives at
`/{locale}/objects/component/{stable_id}/edit`.

Those extra URLs are documented on the section pages above. They are not
separate help-center chapters.

## Matching CLI commands

The website copies only commands the CLI actually parses. The canonical
templates are:

```bash
uv tool install ai-stp-cli
ai-stp auth login --provider github --json
ai-stp registry search --json
ai-stp registry show --kind component --id <stable_id> --json
ai-stp registry version --kind component --id <stable_id> --version <x.y> --json
ai-stp link web --json
```

The full map is the [command map](../cli/commands.md). If this page and
`ai-stp help --agent --json` disagree, follow the CLI.

## Dead-ends that apply everywhere

| What you see | What it means | What to do |
| --- | --- | --- |
| `Page not found` | unknown path, draft content, or an id the catalog does not publish | open [Catalog](catalog.md) or Home |
| `The service is temporarily unavailable` | the API did not answer | retry later; local CLI cache may still read |
| `Your session expired` | the HttpOnly cookie is gone or stale | sign in again; `returnTo` is preserved |
| empty list | a typed zero, not a crash | change filters, publish from the CLI, or like an object |
| missing Content or Contact | the compiled profile turned the flag off | use Catalog and the CLI; that is expected on self-hosted |

A 404 never names whether the object is private, draft, or absent.

## Related pages

- [Quickstart for people](../quickstart/human.md) — install the CLI and
  read the catalog from a shell.
- [Quickstart for agents](../quickstart/agent.md) — session ritual and
  machine help.
- [Concepts](../concepts/index.md) — harness, setup, component, passport,
  trust line.
- [Catalog (meaning)](../catalog/index.md) — how to read a result before
  you trust it.
- [Components](../components/index.md) — the eight kinds.
- [Setups](../setups/index.md) — composition happens in the CLI.
- [Trust and safety](../trust-and-safety/index.md) — `author_verified` is
  not `component_verified`.
- [CLI](../cli/index.md) — the surface that applies a plan.

!!! note "The website does not install"
    Copying a CLI command from a catalog card is the start of a local
    flow. The browser never runs `install apply` and never talks to a
    provider.
