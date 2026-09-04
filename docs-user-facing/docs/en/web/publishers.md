---
title: "Publishers"
description: "The public publisher page for an account."
---

# Publishers

A publisher page is the public face of one account: display name, bio,
HTTPS links, avatar, `author_verified`, and the objects that account
has in the catalog. It is not a passport, not a trust guarantee, and
not a private profile.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/publishers/{account_id}` | anyone |
| Machine | `/{locale}/ai/publishers/{account_id}` | anyone |

`{account_id}` is the account ULID, not a GitHub login and not a
display name. A malformed id 404s. A well-formed id with no public
projection also 404s: the site does not confirm that the account
exists.

Anyone may read a published page. The owner, when signed in on their
own id, sees **Edit public profile** to `/{locale}/account/profile`.
Visitors do not.

Privacy flags on [Account](account.md) control whether a rich profile
is shown at all. `Show profile publicly` and `Allow publisher listing`
are separate. An empty public projection still lists **published
objects** when the catalog has them.

## What this screen is for

Use the page to:

- see who publishes a catalog object (from the author rail);
- read a short bio and up to eight HTTPS links;
- browse that account's public components and setups, including
  experimental ones;
- copy a CLI deep link for the publisher.

The page does **not**:

- verify content (`author_verified` is identity, not safety);
- list private or unlisted objects;
- follow, message, or star the publisher;
- merge GitHub and Google identities (that is Account);
- change `component_verified` on any version.

## What is on the screen

**Back to catalog** returns to the catalog with experimental included.

| Element | Content |
| --- | --- |
| Avatar | published image, or initials from display name / id |
| Title | display name, or the word Publisher when empty |
| Badge | Author verified, when `author_verified` is true |
| Account id | monospace, copyable as text |
| CLI copy | canonical `link web` command for this publisher |
| Links | label + hostname, `rel=noopener`, HTTPS only |
| Bio | limited Markdown (lists, headings, emoji, tables, links, bold, code) |
| Edit public profile | owner only |
| Public profile badge | when the projection is not empty |

Empty projection copy:

> This publisher has not authored a public profile. Only the account
> id and published objects are shown.

### Published objects

Two groups, catalog cards:

| Group | Source |
| --- | --- |
| Components | search with `authors=[account_id]`, experimental included |
| Setups | the same for setups |

Each card is the ordinary catalog card: kind, version, harness, the two
verified bits, likes. There is no separate “unlisted” shelf. Objects
the account owns but has not published do not appear; those live under
[Objects](objects.md) for the owner.

Empty group: **No public objects listed.**

Human / Machine switch keeps the account id. Machine projection prints
`account_id`, `author_verified`, `display_name`, `bio`, and object
lists as links.

## Matching CLI commands

```bash
ai-stp link web --json
ai-stp registry search --json
ai-stp registry show --kind component --id <stable_id> --json
ai-stp registry show --kind setup --id <stable_id> --json
ai-stp owner objects --json
```

`link web` is what the page copies for the publisher target. `registry
search` with an author constraint is the CLI equivalent of the object
lists. `owner objects` is **your** objects when signed in; it is not a
way to dump someone else's private graph.

There is no `ai-stp publisher` command.

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| `Page not found` | bad id or no public projection | open the author from a catalog card |
| Empty profile text | publisher chose not to publish a bio | use account id + objects only |
| No public objects listed | nothing in the catalog for this author | do not infer hidden inventory |
| Author verified, failed checks | identity ≠ content | read the component card |
| Edit public profile missing | you are not this account | expected |
| Link refused by the browser | not HTTPS or unsafe URI | the profile editor rejects those on save |
| 404 after unpublishing the profile | privacy flag or empty revision | the catalog cards still name the id |

A catalog card may show a publisher even when this page is empty. The
id is enough to search. The missing bio is not a missing author.

## How objects land here

The lists are catalog searches with `authors=[account_id]` and
`include_experimental=true`. Private owner versions never appear.
Experimental objects appear with the same Main / Experimental
semantics as the catalog, but this page does not offer the
experimental toggle: if it is public enough to search, it is listed.

`author_verified` on the header is the publisher. Each card still
shows its own `component_verified`. A verified publisher with a
failed pin is the usual case to slow down for, not a contradiction.

Owner-only **Edit public profile** is the only write control. Likes
and reports on the cards behave as on the catalog (session required).

Machine publisher documents `account_id`, `author_verified`,
`display_name`, `bio`, then component and setup links. An agent
should not infer email or GitHub login from the id.

## Related pages

- [Profile](profile.md) — how the owner edits this page.
- [Account](account.md) — privacy flags that hide it.
- [Catalog](catalog.md) — author filter.
- [Component card](catalog-component.md) — author rail.
- [Objects](objects.md) — unpublished owned versions.
- [Trust and safety](../trust-and-safety/index.md) — verified author
  limits.
- [Publishing](../publishing/index.md) — how objects become public.

!!! warning "Do not treat a bio as a passport"
    Display name, avatar, and Markdown are presentation. Provenance,
    digest, and checks live on the component or setup version.
