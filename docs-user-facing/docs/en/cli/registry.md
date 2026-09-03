---
title: "Registry"
description: "Search and show the public catalog, fetch exact versions, acquire a setup graph, and import local SX or APM snapshots."
---

# Registry

The registry commands read the public catalog without an account, fetch
exact published bytes into the local cache, acquire one setup graph for
offline compilation, and import a local SX or APM snapshot into the
local registry only. They do not apply a setup and they do not write a
harness target.

A search result is a candidate, not permission to install. Check the
harness, the exact `X.Y` version, the trust line, and the two
independent verification axes before you select anything.

## Commands

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp registry search` | `read` | `none` | Search the public catalogue without an account. |
| `ai-stp registry show` | `read` | `none` | Show one catalogue object and its published versions. |
| `ai-stp registry version` | `read` | `none` | Show one exact published version and its verified passport. |
| `ai-stp registry fetch` | `apply` | `none` | Fetch the exact bytes of one published version into the local cache. |
| `ai-stp registry acquire` | `apply` | `none` | Acquire one exact published setup graph for local offline compilation. |
| `ai-stp registry port discover` | `read` | `none` | Find compatible SX and APM snapshots under one explicit local root. |
| `ai-stp registry port inspect` | `read` | `none` | Inspect one setup-store mapping without importing or running its CLI. |
| `ai-stp registry port plan` | `plan` | `none` | Preview a local-only setup-store import and bind it to exact manifest bytes. |
| `ai-stp registry port import` | `apply` | `plan_digest` | Import a confirmed exact SX or APM snapshot into the local registry only. |

`--kind` is required on `search`, `show`, `version`, and `fetch`. It is
`component` or `setup`. `--id` is required on `show`, `version`,
`fetch`, and `acquire`. `--version` is required on `version`, `fetch`,
and `acquire`. Port commands require `--root`; inspect, plan, and
import also require `--adapter` (`sx` or `apm`). Import requires
`--expected-plan-digest`.

## Typical path

Anonymous catalog reads:

```bash
ai-stp registry search --kind component --json
ai-stp registry show --kind component --id <stable_id> --json
ai-stp registry version --kind component --id <stable_id> --version <version> --json
```

`<stable_id>` is the object's stable identifier. `<version>` is an
exact `X.Y`. A range is not a reference.

To put those exact bytes in the local cache, then acquire a setup
graph:

```bash
ai-stp registry fetch --kind component --id <stable_id> --version <version> --json
ai-stp registry acquire --id <stable_id> --version <version> --json
```

`acquire` is for a published *setup*. Its `--id` is a setup identifier.

To import a local setup-store snapshot, never touching the external
store or a harness target:

```bash
ai-stp registry port discover --root <root> --json
ai-stp registry port inspect --root <root> --adapter sx --json
ai-stp registry port plan --root <root> --adapter sx --json
ai-stp registry port import --root <root> --adapter sx --expected-plan-digest <plan-digest> --json
```

`<plan-digest>` is the digest `port plan` returned. If the snapshot
bytes changed, the digest no longer matches and import is refused.

If the network is down, a read may answer from cache and will say so
in `source`. Read `checked_at`. Do not treat a cache hit as a live
catalog.

## Catalog reads

### `registry search`

Search the public catalogue without an account.

```bash
ai-stp registry search --kind component --json
```

`--kind` is required and is `component` or `setup`. Optional query,
cursor, limit, and experimental-lane flags exist in machine help. They
are not required, so they are not copied here.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `kind` | `component` or `setup` |
| `items` | the authoritative-lane page |
| `experimental` | the experimental lane, when requested |
| `next_cursor` | opaque cursor for the next page, or empty |
| `source` | `online` or `cache` |
| `checked_at` | when the platform last confirmed these bytes |
| `schema_version` | the schema major of this report |

A card is not an object-level passport. Latest-version facts are
copied from that version's passport. `author_verified` and
`component_verified` are independent. See
[Catalog](../catalog/index.md) and
[Trust and safety](../trust-and-safety/index.md).

### `registry show`

Show one catalogue object and its published versions.

```bash
ai-stp registry show --kind component --id <stable_id> --json
```

Successful `data` names `kind`, `summary`, `versions`, `source`,
`checked_at`, and `schema_version`. `versions` is the published line,
not a local draft.

### `registry version`

Show one exact published version and its verified passport.

```bash
ai-stp registry version --kind component --id <stable_id> --version <version> --json
```

Successful `data` names `kind`, `lifecycle`, `passport`,
`passport_digest`, `published_at`, `trust`, `source`, `checked_at`,
and `schema_version`.

`trust` carries `author_verified`, `component_verified`, and
`trust_lane` (`authoritative` or `experimental`). Neither verification
flag may be computed from the other. `authoritative` additionally
requires both, and that implication is not a substitute for reading
the flags.

## Catalog writes to the local cache

### `registry fetch`

Fetch the exact bytes of one published version into the local cache.

```bash
ai-stp registry fetch --kind component --id <stable_id> --version <version> --json
```

Writes to the local cache and nothing else. The bytes are immutable
and addressed by content, so a second call is a no-op. This is not an
install.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `kind` | `component` or `setup` |
| `stable_id` | the object you fetched |
| `version` | the exact `X.Y` |
| `digest` | content digest of the bytes |
| `path` | where those bytes now are |
| `size_bytes` | length of the file |
| `source` | `online` or `cache` |
| `checked_at` | when the bytes were confirmed |
| `schema_version` | the schema major of this report |

The file at `path` hashes to `digest` and is `size_bytes` long. That
is the point of the envelope.

### `registry acquire`

Acquire one exact published setup graph for local offline compilation.

```bash
ai-stp registry acquire --id <stable_id> --version <version> --json
```

`--id` and `--version` are required. This materializes one published
setup and every exact component it pins. It is not `install apply`.
The next honest step is [Select](select.md) or [Install](install.md)
against the local graph.

Successful `data` names `stable_id`, `version`, `harness_id`,
`passport_digest`, `artifact_digest`, `components`, `source`,
`checked_at`, and `schema_version`. Each acquired component names
`stable_id`, `version`, `passport_digest`, and `artifact_digest`.

If the published graph pins two versions of one component, or a
component passport differs from the exact setup reference, the command
refuses with `AI_STP_CATALOG_INTEGRITY` or `AI_STP_CONFLICT`. Do not
“pick one” by hand.

## Local setup-store port

These four commands talk to a directory you name. They do not run the
foreign CLI. They do not change the external store. They do not write
a harness target. `adapter` is `sx` or `apm`.

### `registry port discover`

Find compatible SX and APM snapshots under one explicit local root.

```bash
ai-stp registry port discover --root <root> --json
```

Successful `data` names `root`, `stores`, and `diagnostics`. Each
store names `adapter`, `contract_version`, `root`, `manifest`,
`snapshot_digest`, and `cli_status` (`available`, `absent`, or
`not_required`).

### `registry port inspect`

Inspect one setup-store mapping without importing or running its CLI.

```bash
ai-stp registry port inspect --root <root> --adapter sx --json
```

Successful `data` names `descriptor`, `mappings`, `unknown_fields`,
and `diagnostics`. Unknown fields are listed, not silently imported.

### `registry port plan`

Preview a local-only setup-store import and bind it to exact manifest
bytes.

```bash
ai-stp registry port plan --root <root> --adapter sx --json
```

This is a `plan`. It has no effect of its own. Successful `data` names
`plan_digest`, `inspection`, `importable_count`, `omitted_count`,
`conflicts`, and `trust_consequences`.

`trust_consequences` is a closed list. Typical members are
`local_only`, `author_verified_false`, `component_verified_false`,
`external_store_unchanged`, and `harness_target_unchanged`. An import
does not become platform-verified by arriving through this port.

### `registry port import`

Import a confirmed exact SX or APM snapshot into the local registry
only.

```bash
ai-stp registry port import --root <root> --adapter sx --expected-plan-digest <plan-digest> --json
```

`--expected-plan-digest` is required. Confirmation is `plan_digest`:
what is imported can only ever be something already described. If the
bytes changed, build a new plan.

Successful `data` names `plan_digest`, `imported`,
`external_store_changed` (always `false`), and
`harness_target_changed` (always `false`). Each imported object names
`external_id`, `stable_id`, `revision_id`, and `state` (`imported` or
`already_imported`).

## What a successful envelope contains

Each command returns the fields named in its section. Every envelope
also carries `ok`, `warnings`, `next_actions`, `request_id`,
`operation_id`, and `schema_version`.

`source` on catalog reads is `online` or `cache`. Cache is a successful
answer when the platform already confirmed the bytes. It is not a live
refresh. Read `checked_at`.

If `catalog.enabled` is false, catalog commands refuse with
`AI_STP_DEPENDENCY_UNAVAILABLE`. That is configuration, not an outage.
See [Configuration](config.md).

## What these commands never do

- apply a setup or write a harness target;
- run a foreign SX or APM CLI;
- change the external setup store;
- treat `author_verified` as `component_verified`;
- accept a version range in place of exact `X.Y`;
- skip consent, eligibility, or an install plan digest;
- put secrets into a passport or a search card.

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` missing `--kind` | search, show, version, and fetch require it | `--kind component` or `--kind setup` |
| `AI_STP_VALIDATION_ERROR` missing `--id` / `--version` | that command names one exact object | pass the required options |
| `AI_STP_DEPENDENCY_UNAVAILABLE` catalog off | `catalog.enabled` is false | `config show --json`; do not treat it as downtime |
| `source: cache` | the platform was not reached | read `checked_at`; do not treat it as a live catalog |
| `AI_STP_CATALOG_INTEGRITY` | published bytes or passports do not match | stop; do not install from a broken graph |
| `AI_STP_CONFLICT` two versions of one component | the setup graph is not exact | do not pick a winner by hand |
| `AI_STP_USER_DECISION_REQUIRED` on port import | `--expected-plan-digest` was missing | pass the digest `port plan` returned |
| stale plan digest | the snapshot bytes changed | `port plan` again, then import the new digest |
| `AI_STP_VALIDATION_ERROR` missing `--root` / `--adapter` | port commands need an explicit store | `--root <root> --adapter sx` or `apm` |

## Related pages

| Page | Why |
| --- | --- |
| [Catalog](../catalog/index.md) | how to read a card |
| [Web catalog](../web/catalog.md) | the same objects on the website |
| [Trust and safety](../trust-and-safety/index.md) | trust lines and verification axes |
| [Consent](consent.md) | unverified publishers and major lines |
| [Select](select.md) | eligibility and proposal after a fetch |
| [Install](install.md) | plan, approve, apply |
| [Setup commands](setup.md) | compose and import native configuration |
| [Sign-in](auth.md) | `link web` for a canonical URL |
| [Quickstart for people](../quickstart/human.md) | first catalog read |

!!! note "Flags from `ai-stp help --agent --json`"
    If `help --agent` disagrees with a flag on this page, the CLI wins.
    Optional flags are not listed here. Read them from the descriptor.
    Catalog commands require `--kind` where the table says so. Port
    import requires `--expected-plan-digest`.
