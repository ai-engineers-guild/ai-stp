---
title: "Component card"
description: "How to read a public component page and its versions."
---

# Component card

A component card is the public page for one catalog component. It shows
the latest offered version, its passport facts, checks, and media. It
does not adopt the component, write a passport, or install it.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/catalog/components/{stable_id}` | anyone |
| Machine | `/{locale}/ai/catalog/components/{stable_id}` | anyone |
| Human version | `/{locale}/catalog/components/{stable_id}/versions/{version}` | anyone |
| Machine version | `/{locale}/ai/catalog/components/{stable_id}/versions/{version}` | anyone |

`{stable_id}` must be a component id. A setup id, a truncated ULID, or
a name 404s. Unpublished, blocked, or unknown ids also 404. The page
does not say which of those happened.

Anyone can read a public card. Like, unlike, and report need a session.
**Edit bio and media** appears only when the session owns the object;
it goes to `/{locale}/objects/component/{stable_id}/edit`.

## What this screen is for

Use the card to decide whether this exact version is a candidate:

- kind (`instruction`, `skill`, `mcp`, `hook`, `command`, `agent`,
  `plugin`, `setting`, `cli`);
- harness names;
- `author_verified` and `component_verified` as separate bits;
- source repository, commit, and path;
- safety checks and requirements;
- context budget (potential tokens, not measured usage).

The card does **not**:

- run `component adopt` or `component passport update`;
- apply a hook, start an MCP server, or enable a plugin;
- store environment values you type into a cost estimate;
- treat GitHub stars as a security signal.

Memory, rules, and helper tools are content of `instruction`, `skill`,
or `setting`. They are not extra kinds on this page.

## What is on the screen

**Back to catalog** returns to
`/{locale}/catalog?include_experimental=1&resource=components`.

### Header

| Element | What it shows |
| --- | --- |
| Type icon | the closed-kind glyph |
| Title | `latest_name` |
| Badges | component type, named harnesses |
| Version | `v{latest_version}` |
| GitHub stars / Archived | when metadata exists |
| View source | pinned repository links from the passport |

Actions:

| Action | Needs session | Effect |
| --- | --- | --- |
| Like / Liked | yes | toggles a reaction |
| Copy URL / Share | no | canonical version URL |
| Copy ID | no | `stable_id` |
| Copy CLI command | no | `ai-stp registry version --kind component --id {stable_id} --version {version}` |
| Report component | yes | `/{locale}/reports?object_kind=component&stable_id=…&version=…&digest=…` |
| Edit bio and media | owner | presentation editor |

### Relationships and body

Linked countries and regional services are related, not exclusive. A
component may name several markets. Opening a service does not hide
other services.

The main column:

| Block | Content |
| --- | --- |
| Description | Markdown from SEO summary, else passport, else catalog blurb |
| Media | up to five images, videos, or YouTube ids |
| Model sections | extra SEO sections when present |
| Technical details | lifecycle, projection kind, published at, harness, SPDX license |
| Requirements | environment names, permissions, endpoints, required components — **names only**, never values |
| Safety checks | scan status, percent, required vs extra engines |

The rail:

| Block | Content |
| --- | --- |
| Author | publisher avatar, display name, `author_verified` |
| Usage | detail views, artifact downloads |
| Context budget | potential tokens; runtime-derived kinds say so |
| CLI copy | exact `registry version` line |
| Version history | offered `X.Y` numbers; gaps are intentional |

**Public passport JSON** is behind an accordion. Copy it as JSON. It is
the machine record summarized above, not a secret store. Secrets must
not appear there; if you see something that looks like a token, report
the version.

### Safety percent

The catalog percent is `passed / (passed + failed + warning)`. Required
checks gate publication. Extra scanners can be incomplete without
failing the percent. Finding payloads that might contain secrets are
hidden. How each engine works: [Security checks](../security-checks.md).

`author_verified` answers “did the platform confirm this publisher?”.
`component_verified` answers “did this exact version pass the gate?”.
Neither follows from the other.

### Exact version page

`/versions/{version}` is one immutable passport. It adds OS/arch,
support evidence, and the digest of that version. Offered numbers may
skip; missing minors are not a catalog bug.

## Matching CLI commands

```bash
ai-stp registry show --kind component --id <stable_id> --json
ai-stp registry version --kind component --id <stable_id> --version <x.y> --json
ai-stp registry fetch --json
ai-stp link web --json
ai-stp select blast-radius --json
```

`registry show` lists published versions. `registry version` is one
`X.Y`. `registry fetch` copies bytes into the local cache. `link web`
prints the canonical website URL. `select blast-radius` is local: it
shows which setups and targets already reference the component.

Adopting or publishing is not this page:

```bash
ai-stp component discover --json
ai-stp owner object show --json
```

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| `Page not found` | bad id, private, blocked, or never published | return to [Catalog](catalog.md) |
| `The service is temporarily unavailable` | API down | retry; use CLI cache if you already fetched |
| No media | owner published none | not an error |
| No versions | nothing offered | do not invent an `X.Y` |
| Context budget unavailable | artifact not tokenized | run a local impact command from the CLI |
| Cost estimate empty | you did not type a rate | optional; the rate is not saved |
| Like rejected | no session | [Sign-in](login.md) |
| Report missing digest | latest version had no digest yet | open a concrete `/versions/{version}` |
| Edit bio missing | you are not the owner | expected |

Machine projection prints `stable_id`, digest, `trust_lane`,
`author_verified`, `component_verified`, harness, and the install
command template. It does not render the gallery.

## Related pages

- [Catalog](catalog.md) — search that led here.
- [Setup card](catalog-setup.md) — setups that may pin this component.
- [Publishers](publishers.md) — the author rail target.
- [Reports](reports.md) — how a report is filed.
- [Objects](objects.md) — owner presentation edit.
- [Components](../components/index.md) — kind boundaries.
- [Trust and safety](../trust-and-safety/index.md) — two axes.
- [Registry](../cli/registry.md) — show, version, fetch.

??? question "Can I install from this page?"
    No. Copy the CLI command, then select and apply in the CLI through
    the harness provider. The website never writes native state.
