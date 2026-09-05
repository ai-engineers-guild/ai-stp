---
title: "Catalog"
description: "Search, Catalog QL, Both-mode, trust lines, and safety percent."
---

# Catalog

The catalog is the public index of setups and components. Anyone can
read it. It does not install, compose, or pin. A card is evidence for a
later CLI decision.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/catalog` | anyone |
| Machine | `/{locale}/ai/catalog` | anyone |

Query string is kept across the Human / Machine switch. Unknown keys are
not ignored: the page shows `Invalid catalog filter` instead of a
silent drop.

Default query when you open the page with no parameters:

- `resource=all` (Both);
- `include_experimental=1` (experimental objects are in the list);
- `sort=relevance`, `sort_direction=desc`;
- `view=list`;
- `page_size=25`.

Likes on cards require a session. Search, filters, and passport reads
do not.

## What this screen is for

Use Catalog to find a candidate, read its trust axes, and copy a CLI
show/version command.

Catalog does **not**:

- run `select` or `install`;
- write a provider plan;
- treat `author_verified` as proof that a version is safe;
- hide experimental objects unless you turn that filter off;
- invent tags outside the vocabulary.

Both-mode lists **setups first, then components**. Each group keeps the
sort you chose. Pagination in Both walks setup pages first, then
component pages.

## What is on the screen

### Search and Catalog QL

The search box placeholder is `Search components and setups`. Shortcut
`Ctrl`/`Cmd` `K` focuses it. Help text:

> Use plain words or Catalog QL: NAME, TAGS, HARNESS, TYPE, AUTHOR and
> VERIFIED with :, AND, OR, NOT, IN, NOT IN and parentheses. Example:
> `TYPE:skill AND HARNESS IN (codex, claude-code)`.

| Form | Meaning |
| --- | --- |
| plain words | full-text term |
| `FIELD:value` | equality on an allowlisted field |
| `FIELD IN (a, b)` | membership |
| `FIELD NOT IN (a, b)` | exclusion |
| `AND` / `OR` / `NOT` | boolean connectives |
| `( … )` | grouping, depth bounded |

Allowlisted fields: `NAME`, `TAGS`, `HARNESS`, `TYPE`, `AUTHOR`,
`VERIFIED`. A query longer than 500 characters, too many tokens, or an
unknown field is rejected at the API boundary. Structural filters from
the form are combined with the QL AST using `AND`.

`Did you mean` may offer a correction. It does not run the correction
until you accept it.

### Resource, experimental, layout

| Control | Values | Default |
| --- | --- | --- |
| Catalog resource | Both / Setups / Components | Both |
| Include experimental | on / off | on |
| Result layout | Cards / List | List |
| Sort results | Relevance / Recently updated / Most liked | Relevance |
| Direction | Ascending / Descending | Descending |

Main objects are labelled **Main** (`authoritative`). Experimental
objects are labelled **Experimental**. The note under results:

> Main and experimental objects are shown together. Author verification
> is not proof that the contents are safe.

Turning experimental off hides that lane for this search only. It is
not a consent record for later `select`.

### Filters

**Filters & sorting** opens the panel. **Apply filters** writes the
query string. **Reset all** returns the defaults above.

| Filter | Query key | What it keeps |
| --- | --- | --- |
| Tag | `tags` | vocabulary tags (invalid ids error) |
| Harness | `harness_id` / `harness_ids` | passports that name that harness |
| Component type | `component_type` / `component_types` | `instruction`, `skill`, `mcp`, `hook`, `command`, `agent`, `plugin`, `setting`, `cli` |
| Author | `authors` | publisher account ids, comma-separated |
| Only verified | `verified_only` | both `author_verified` and `component_verified` current |
| Countries | `country_code` / `country_codes` | linked markets; **Not specified** is no country list |
| Regional services | `service_domain` / `service_domains` | linked services; list follows selected countries |
| Updated from / to | `updated_from` / `updated_to` | inclusive catalog-update dates |
| Support tier | `support_tier` | `primary` or `beta` |
| Support state | `support_state` | `verified`, `stale`, `missing`, `not_verified` |

Chips on the search row dismiss one filter. Unknown keys, invalid tags,
invalid support values, or a broken QL string produce
`Invalid catalog filter` with the reason. They never call search.

### Result cards

Each card shows kind (Setup or the component type), name, version,
harness badges, tags, publisher, `author_verified`,
`component_verified`, likes, and a safety summary when checks exist.

`author_verified` and `component_verified` are **independent**. A
confirmed author can still publish an unverified version. The verified
filter requires both.

More actions on a card:

| Action | Needs session | Effect |
| --- | --- | --- |
| Copy URL | no | clipboard |
| Copy ID | no | `stable_id` |
| Copy CLI command | no | `ai-stp registry version --kind … --id … --version …` |
| Like / Unlike | yes | saved to [Likes](likes.md) |
| Report | yes | opens [Reports](reports.md) with kind, id, version, digest |

Empty copy:

| Resource | Empty title |
| --- | --- |
| Both | No catalog objects match this query. |
| Setups | No setups match this query. |
| Components | No components match this query. |
| Main only | No main results for this query. |

Usage metrics (detail views, artifact downloads) appear when
`catalog_usage_metrics` is compiled in. They are counts, not a safety
signal.

## Matching CLI commands

Anonymous catalog reads:

```bash
ai-stp registry search --json
ai-stp registry show --kind component --id <stable_id> --json
ai-stp registry show --kind setup --id <stable_id> --json
ai-stp registry version --kind component --id <stable_id> --version <x.y> --json
ai-stp registry version --kind setup --id <stable_id> --version <x.y> --json
```

`registry search` is the CLI twin of this page. `registry show` is the
object. `registry version` is one immutable `X.Y`. Fetch into the local
cache is a different command:

```bash
ai-stp registry fetch --json
```

Canonical website URL for an object:

```bash
ai-stp link web --json
```

Selection and install are **not** catalog commands. They start at
[Select](../cli/select.md) and [Install](../cli/install.md).

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| Invalid catalog filter | unknown key, bad tag, bad QL | drop the unknown parameter; fix QL |
| No catalog objects match | typed empty | widen filters; keep experimental on |
| The service is temporarily unavailable | API down | retry; CLI cache may still `registry show` |
| Like does nothing visible | no session | [Sign-in](login.md), then like again |
| Report form missing fields | you did not open it from a version | open the card, then Report |
| Both-mode page looks like only setups | you are still on a setup page of the mixed pager | go forward past setup pages |
| Card 404 after click | unpublished, blocked, or unknown id | stay on search; do not guess ids |

A machine catalog document lists the active query as fields, then
setups and components. Empty machine output is the same empty message,
not a stack trace.

## Related pages

- [Component card](catalog-component.md) — one public component.
- [Setup card](catalog-setup.md) — one public setup and its pins.
- [Catalog (meaning)](../catalog/index.md) — how to read a result.
- [Regional services](services.md) — country and service filters.
- [Publishers](publishers.md) — author pages.
- [Trust and safety](../trust-and-safety/index.md) — two verified axes.
- [Security checks](../security-checks.md) — what the percent covers.
- [Registry](../cli/registry.md) — CLI search and fetch.
- [Components](../components/index.md) — the closed kinds.

!!! warning "Verified is two bits"
    `verified_only` requires both axes. Ticking it because the author
    looks familiar still hides unverified versions of that author.
