---
title: "Setup card"
description: "How to read a public setup page, its pins, and its composition."
---

# Setup card

A setup card is the public page for one catalog setup. A setup is the
complete configuration of one harness: exact component pins, not a
folder of current files. Replacing any pin is a new setup version.

The page shows that graph. It does not compose, update, or apply it.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/catalog/setups/{stable_id}` | anyone |
| Machine | `/{locale}/ai/catalog/setups/{stable_id}` | anyone |
| Human version | `/{locale}/catalog/setups/{stable_id}/versions/{version}` | anyone |
| Machine version | `/{locale}/ai/catalog/setups/{stable_id}/versions/{version}` | anyone |

`{stable_id}` must be a setup id. A component id 404s. Unknown,
blocked, or unpublished setups 404 without saying which.

Anyone can read a public setup. Like and report need a session. There
is no presentation editor for setups on the website: bio and media
edit is a component-owner flow.

## What this screen is for

Use the card to inspect the composition you might later select:

- target harness;
- purpose, posture, target role (role may be absent);
- every pinned component with its exact `X.Y`;
- aggregated requirements of the setup plus its pins;
- potential context budget of the whole graph;
- `author_verified` and `component_verified` on the **setup version**.

The card does **not**:

- run `setup compose`, `select propose`, or `install apply`;
- substitute a newer component for you;
- write native files into the harness;
- treat listed regional services as exclusive markets.

A third-party component inside the graph keeps its own publisher. The
setup author is not automatically the author of every pin.

## What is on the screen

**Back to catalog** returns to
`/{locale}/catalog?include_experimental=1&resource=setups`.

### Header

| Element | What it shows |
| --- | --- |
| Icon | setup artwork, not a component-type glyph |
| Title | `latest_name` |
| Badges | Setup, named harnesses |
| Version | `v{latest_version}` |
| GitHub stars / Archived | when metadata exists |
| View source | passport source when declared |

Actions match the component card: Like, Copy URL, Copy ID, Copy CLI
command, Report setup. The CLI line uses `--kind setup`. Report opens
`/{locale}/reports?object_kind=setup&stable_id=…&version=…&digest=…`.

### Relationships and body

Countries and linked services are related, not exclusive.

The main column:

| Block | Content |
| --- | --- |
| Description | passport or catalog text |
| Technical details | lifecycle, published at, primary harness, SPDX license |
| Composition | exact components this setup includes |
| Aggregated requirements | union of setup and pin requirements |

Each composition row names:

- `stable_id` and pinned `version`;
- component type;
- owner / author (may differ from the setup publisher);
- third-party source mark when the pin is not first-party;
- link to the public component card when the pin is in the catalog.

A pin that cannot be loaded is omitted from the live table rather than
shown as a guessed type. That is a dead-end for that member, not a
license to invent it.

The rail:

| Block | Content |
| --- | --- |
| Author | setup publisher, `author_verified` |
| Usage | detail views, artifact downloads |
| Context budget | potential tokens for always-loaded vs on-use members |
| Local full report | copy of `ai-stp select impact --setup-id … --setup-version …` |
| CLI copy | `ai-stp registry version --kind setup --id … --version …` |
| Version history | offered `X.Y`; gaps are intentional |

**Public passport JSON** is the setup passport, including the pin list.
Copy it; do not paste secrets into it.

### Context budget

The panel estimates **potential** context, not actual model usage. A
rate you type for a cost estimate stays in the browser. No pricing API
is called. Runtime-integrated members say that package bytes would be
misleading.

Always-loaded members are included every time the setup loads.
Conditional members are added only when the agent uses them.

### Trust on a setup

`author_verified` on the setup is the setup publisher. Each pin has its
own pair of axes on its component card. A verified setup author does
not verify a third-party MCP inside the graph. The `setup_pin_aggregate`
check joins exact pins and their published check summaries; it is not
a substitute for reading a failed pin.

## Matching CLI commands

```bash
ai-stp registry show --kind setup --id <stable_id> --json
ai-stp registry version --kind setup --id <stable_id> --version <x.y> --json
ai-stp registry acquire --json
ai-stp select impact --setup-id <stable_id> --setup-version <x.y> --json
ai-stp link web --json
```

`registry acquire` fetches one exact published setup graph for local
offline compilation. `select impact` compares context, token cost, and
capabilities of exact **local** setup versions — the website only
copies the command.

Composition and apply stay in the CLI:

```bash
ai-stp setup compose plan --json
ai-stp select propose --json
ai-stp install plan --json
```

Those pages: [Setup commands](../cli/setup.md),
[Select](../cli/select.md), [Install](../cli/install.md).

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| `Page not found` | bad setup id or not public | [Catalog](catalog.md) with resource=setups |
| Composition row missing | that pin could not be read | open the version page; do not fill the hole from memory |
| No tokenized components | budget empty | run `select impact` locally |
| Context budget error | exact artifact unavailable | fetch first (`registry acquire` / `registry fetch`) |
| Report missing digest | no passport digest on latest | open `/versions/{version}` |
| Like requires sign-in | no session | [Sign-in](login.md) |
| Install from the browser | not offered | copy CLI, then provider apply |

Machine projection lists purpose, target role (or its absence),
posture, pins, trust lane, and the two verified bits. It does not
render the composition gallery.

## Related pages

- [Catalog](catalog.md) — Both-mode shows setups first.
- [Component card](catalog-component.md) — each pin.
- [Setups](../setups/index.md) — how a graph is assembled in the CLI.
- [Concepts](../concepts/index.md) — setup belongs to one harness.
- [Trust and safety](../trust-and-safety/index.md) — pins do not inherit
  author verification.
- [Registry](../cli/registry.md) — show, version, acquire.
- [Provider](../cli/provider.md) — the only writer of native state.

!!! note "A setup is a pin list"
    If the author updated one `skill` or disabled a `hook`, that is a
    new `X.Y`. The card you are reading is one immutable graph.
