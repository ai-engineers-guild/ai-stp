---
title: "Component source"
description: "Parse, resolve, and search external component sources, and read GitHub archived evidence."
---

# Component source

These commands treat an external component source as untrusted structured
intent until a commit is bound, and they keep official GitHub archived
evidence for one exact local version.

Parsing does not fetch. Resolving binds one full commit SHA. Searching names
does not select a candidate. Evidence commands talk about the archived
repository state, not about whether the version is safe.

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp component source parse` | `read` | `none` | parse a slug, GitHub identity, local path, or collection |
| `ai-stp component source resolve` | `read` | `none` | bind a GitHub intent to one exact full commit SHA |
| `ai-stp component source search` | `read` | `none` | search catalog names; package and GitHub hits need a flag |
| `ai-stp component source evidence refresh` | `apply` | `none` | refresh official GitHub archived evidence for one version |
| `ai-stp component source evidence show` | `read` | `none` | show the latest local archived evidence and freshness |
| `ai-stp component source evidence history` | `read` | `none` | bounded append-only archived evidence history |

`--json` is global. Always pass it.

## Parse

Parse an external source string as structured intent. The result is
untrusted until resolve (or another exact proof) binds it.

```bash
ai-stp component source parse --source owner/repo --json
ai-stp component source parse --source https://github.com/owner/repo --json
ai-stp component source parse --source ./hooks/check --root . --json
```

`--source` is required. It may be a published slug, a GitHub identity, a
local path, or a collection. `--root` is used only to normalize a relative
local path.

Success fields include `kind`, `canonical`, `owner`, `ref`, `local_path`,
`collection_owner`, `collection_handle`, and `provenance_proven`. `kind` is
one of `published`, `github`, `github/exact`, `local`, `collection`.
`provenance_proven` stays false until an exact identity is proven.

## Resolve

Resolve binds a GitHub shorthand or credential-free HTTPS URL to one
lowercase 40-character commit SHA.

```bash
ai-stp component source resolve --source owner/repo --json
ai-stp component source resolve \
  --source https://github.com/owner/repo \
  --commit abcdef0123456789abcdef0123456789abcdef01 \
  --json
```

`--commit` is optional: omit it to resolve the named ref to a SHA, or pass
the exact SHA you already have. `--root` only normalizes a relative local
path.

The answer uses the same identity schema as parse. After a successful
resolve, `kind` is `github/exact` and `provenance_proven` is true. A range,
a floating tag without a SHA, or a URL with credentials is refused.

## Search

Search is name-only. It never selects a candidate and never installs.

```bash
ai-stp component source search --query context7 --json
ai-stp component source search --query context7 --registry-discovery --json
```

Without `--registry-discovery`, hits are catalog names. With it, supported
package names and known GitHub candidates are included as well. Each hit
keeps `source`, `catalog_status`, `trust_lane`, `author_verified`, and
`component_verified` as separate fields. A GitHub hit that is
`not_in_catalog` is still just a name.

Success fields: a list of candidates with `name`, `source` (`catalog`,
`package`, or `git`), `exact_coordinate`, `stable_id`, `catalog_status`,
`trust_lane`, `author_verified`, `component_verified`.

## Evidence show, refresh, history

Archived GitHub evidence is an official observation of the source
repository: whether it is archived, when the observation was fetched, and
whether it is still fresh. It is not a safety scan.

```bash
ai-stp component source evidence show --id <stable_id> --version 1.0 --json
ai-stp component source evidence refresh --id <stable_id> --version 1.0 --json
ai-stp component source evidence history --id <stable_id> --version 1.0 --json
ai-stp component source evidence history --id <stable_id> --version 1.0 --limit 20 --json
```

`--id` and `--version` are required. `--version` is the exact recorded
`X.Y`. `--limit` on history is the newest observations to return, from 1 to
100.

`refresh` is `apply`: it writes a new observation. It has `confirmation:
none`. Naming the exact id and version **is** the decision.

Success fields for show and refresh: `stable_id`, `version`,
`passport_digest`, `source_repository`, `repository_id`,
`repository_full_name`, `repository_state`, `archived`, `fetched_at`,
`expires_at`, `freshness`, `observation_id`. `freshness` is `fresh`,
`stale`, or `unavailable`. `repository_state` is `active`, `archived`, or
`unavailable`. History returns a bounded list of those observations.

## Happy path

```text
component source parse --source owner/repo
→ component source resolve --source owner/repo
→ component source search --query <name>
→ setup update plan  or  component adopt
```

For a version you already released:

```text
component source evidence show --id <id> --version 1.0
→ component source evidence refresh --id <id> --version 1.0   # if stale
→ component source evidence history --id <id> --version 1.0
```

## Named success fields

| Command | Fields to read |
| --- | --- |
| `parse` / `resolve` | `kind`, `canonical`, `provenance_proven`, `ref` |
| `search` | each candidate's `name`, `source`, `catalog_status`, `trust_lane` |
| `evidence show` / `refresh` | `freshness`, `archived`, `repository_state`, `fetched_at` |
| `evidence history` | the bounded observation list |

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | `--source`, `--id`, or `--version` is missing or malformed | correct the request; a range is not a version |
| `AI_STP_NOT_FOUND` | the local object or version does not exist | `component version list --id <id>` |
| `AI_STP_DEPENDENCY_UNAVAILABLE` | GitHub or the registry could not be reached | retry only if `retryable: true`; otherwise work from cache |
| `AI_STP_PRECONDITION_FAILED` | the source is not a credential-free GitHub identity | strip credentials; use HTTPS without a userinfo field |
| `freshness: stale` | the last observation has expired | `evidence refresh` for that exact version |
| `freshness: unavailable` | the official archive could not be observed | read `repository_state`; do not invent a substitute |
| search without `--registry-discovery` | package and GitHub lanes were not queried | pass the flag if you meant to search those lanes |
| treating a search hit as a pin | search never selects | resolve or plan an exact coordinate next |

Do not put tokens in `--source`. Do not pass `NAME=value` anywhere in this
group. Do not invent `--commit` on parse: that option exists on resolve
only.

## Related links

- [Component commands](component.md)
- [Discover and adopt](component-discover.md)
- [Component passport](component-passport.md)
- [Publish a component](component-publish.md)
- [Setup commands](setup.md)
- [Registry](registry.md)
- [Publishing](../publishing/index.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups source commands so a person can find them. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and
the CLI disagree, follow the CLI.
