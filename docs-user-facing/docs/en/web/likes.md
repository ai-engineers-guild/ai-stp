---
title: "Likes"
description: "Saved likes for catalog objects."
---

# Likes

Likes is the signed-in shelf of catalog objects you marked Like. It is
a personal list for later. It is not a recommendation engine, not a
trust line, and not an install queue.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/likes` | signed-in |
| Machine | `/{locale}/ai/likes` | same session |

The account menu label is **My likes**. Likes is not in the primary
header. No session → login with `returnTo=/{locale}/likes`.

Other people cannot see your list. Publisher pages do not show who
liked an object. The public card only shows a count.

## What this screen is for

Use Likes to reopen a component or setup you saved while browsing.

Likes does **not**:

- pin a version (the card still moves with `latest_version`);
- grant access to a private object;
- replace `select` or `install`;
- include experimental objects you never liked (the list is not a
  catalog search);
- survive as a public badge of quality.

Unlike from a card or from this list removes the object from here.

## What is on the screen

Header: heart icon, **Saved objects**, title **My likes**, subtitle
**Components and setups you saved to revisit later.**, and a count.

Empty:

- **You have not liked anything yet**
- **Browse the catalog and choose Like on a component or setup you
  want to keep.**
- Button **Browse catalog** →
  `/{locale}/catalog?include_experimental=1`

Non-empty: the same `CatalogResults` mixed layout as the catalog
(setups and components as cards/list), without the experimental lane
split (liked ids only). Actions on a card still include Unlike, Copy
CLI command, Copy ID, Report.

Human / Machine: machine Likes lists `object_kind` and `stable_id`
plus links to the public cards.

Like on a catalog card requires a session. Anonymous clicks send you
to Sign-in; after return, like again.

## Matching CLI commands

There is no likes CLI. Related catalog reads:

```bash
ai-stp registry show --kind component --id <stable_id> --json
ai-stp registry show --kind setup --id <stable_id> --json
ai-stp registry version --kind component --id <stable_id> --version <x.y> --json
ai-stp link web --json
```

A like is not a pin. If you need the bytes later, `registry fetch` or
`registry acquire` in the CLI. If you need it installed,
[Install](../cli/install.md).

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| Empty shelf | no reactions | browse the catalog |
| Redirect to login | no session | sign in |
| Card 404 from this list | object left the public catalog | Unlike it; it cannot be opened |
| Count on a card ≠ your list | count is global | expected |
| Liked but still experimental | like is not consent | `select` still asks for experimental consent |
| Mixed list looks unordered | same mixed renderer as catalog | open the card; do not infer rank |
| No Like without sign-in | session required | [Sign-in](login.md) |

Do not treat a high like count as `component_verified`. The axes stay
independent.

## Typical path

1. Sign in (likes are account-scoped).
2. Open [Catalog](catalog.md), Both-mode, experimental on or off as
   you wish.
3. On a card, choose Like. The heart fills; the global count
   increments.
4. Open My likes from the account menu. The object is there with the
   same card actions.
5. Unlike removes it from this shelf and decrements the count. It
   does not delete the catalog object.

If the session expires between 3 and 4, the shelf is empty until you
sign in again — the reaction is on the server, not in localStorage.

## What a like is not

| Action | Like? | Real command or page |
| --- | --- | --- |
| Pin `X.Y` | no | `registry version --version` |
| Consent to experimental | no | CLI `consent allow` |
| Grant a major line | no | [Access](access.md) |
| Install | no | `install plan` / provider |
| Verify content | no | `component_verified` on the version |

Machine projection of `/likes` is a list of kind + `stable_id` links.
An agent should not treat that list as an eligibility matrix.

The mixed renderer on this page does not paginate like the catalog:
the server returns the reaction list as a whole. A missing card is a
404 on click, not a silent hole in the JSON. Unlike is the only write.

If you liked an object to “remember the digest”, copy the version URL
or the `registry version` command at like-time. The shelf stores
`stable_id`, not a frozen `X.Y`.

## Related pages

- [Catalog](catalog.md) — where Like lives on a card.
- [Component card](catalog-component.md) — unlike there too.
- [Setup card](catalog-setup.md) — same control.
- [Sign-in](login.md) — session for reactions.
- [Select](../cli/select.md) — choosing a composition for real.
- [Trust and safety](../trust-and-safety/index.md) — likes ≠ verified.

!!! note "A shelf, not a pin"
    Liking `1.4` today does not freeze `1.4`. Open the version URL or
    copy `registry version` with an explicit `--version`.
