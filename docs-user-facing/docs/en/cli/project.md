---
title: "Project"
description: "Discover project roots, index them without secrets, read public symbols, and record a project passport."
---

# Project

A project in `ai_stp` is a directory you name, not a disk the CLI goes
looking through. Discovery scans only the root you pass. The home
directory is refused. Indexing is bounded and skips secrets and binary
content. The project passport pins that index together with the
toolchain and configuration that were in effect.

These commands do not compose a setup and do not write a harness
target. They describe one tree so later selection has a place to stand.

## Commands

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp project discover` | `read` | `none` | List the projects inside a directory you name. Scans nothing else. |
| `ai-stp project index` | `read` | `none` | Index one project root, bounded, skipping secrets and binary content. |
| `ai-stp project symbols` | `read` | `none` | Read a project's public symbols, entry points and tests. No call graph. |
| `ai-stp project passport` | `apply` | `none` | Record a project passport revision pinning the index, toolchain and config. |

`--root` is required on every command in this group. There is no
configured fallback and no “current directory” implied by silence.

## Typical path

```bash
ai-stp project discover --root <root> --json
ai-stp project index --root <root> --json
ai-stp project symbols --root <root> --json
ai-stp project passport --root <root> --json
```

`<root>` is the exact project root, not the home directory, not a
parent of many repositories unless you meant to discover inside that
parent. `discover` is the command that lists candidates inside a
directory. `index`, `symbols`, and `passport` each take one project
root.

`project index` and `project symbols` are reads: they write nothing.
`project passport` stores a revision in the local registry. It is
idempotent — an unchanged project adds nothing — but idempotent is not
read-only.

`discover` may return several candidates. `index`, `symbols`, and
`passport` each take one of those `root` values. Do not pass the
discovery parent into `index` unless that parent is itself the
project. Nested repositories are listed separately so you can choose.

## `project discover`

List the projects inside a directory you name. Scans nothing else.

```bash
ai-stp project discover --root <root> --json
```

The root is named rather than searched for. There is no mode where this
command goes looking on its own.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `discovery_root` | the directory you named, as resolved |
| `complete` | whether the scan finished inside its bounds |
| `candidates` | each with `root`, `kind`, `state`, `markers`, `reason` |
| `diagnostics` | skipped paths, each with `code`, `path`, `reason` |
| `schema_version` | the schema major of this report |

`kind` on a candidate is `project` or `nested_repository`. `state` is
`new` or `established`. Diagnostic `code` is `excluded`, `entry_limit`,
`symlink`, or `unreadable`.

If `complete` is `false`, the list is not the whole tree. Read
`diagnostics` before treating silence as “nothing here”.

## `project index`

Index one project root, bounded, skipping secrets and binary content.

```bash
ai-stp project index --root <root> --json
```

Reads and reports. The passport that records an index is a different
command. A short answer that looks complete is worse than a complete
answer that says where it stopped, so `state` is `complete` or
`partial`, and `stopped_by` names the bound when the index is partial.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `root` | the project root that was indexed |
| `state` | `complete` or `partial` |
| `stopped_by` | which bound fired, or `null` |
| `files` | each with `path`, `kind`, `language`, `lines`, `size_bytes`, `digest` |
| `excluded` | each with `path` and `reason` |
| `schema_version` | the schema major of this report |

File `kind` is `manifest`, `lock`, `agent_surface`, `source`,
`document`, `config`, or `text`. Content of excluded files is not in
the envelope. Secrets and binary bytes are not in the envelope.

## `project symbols`

Read a project's public symbols, entry points and tests. No call graph.

```bash
ai-stp project symbols --root <root> --json
```

This is a read of public names, not a model of how they call each
other. `method` on each language says how strong the answer is:
`syntax_tree` means a parser read the file; `line_scan` means the
words were recognised line by line. Reporting both as plain counts
would hide that difference.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `root` | the project root that was read |
| `state` | whether the read finished inside its bounds |
| `stopped_by` | which bound fired, or `null` |
| `languages` | each with `language`, `state`, `method`, `files`, `symbols`, `entry_points`, `tests`, `reason` |
| `schema_version` | the schema major of this report |

Language `state` is `available` or `not_available`. A language that is
present in the tree but has no parser in this build is still listed,
with a reason.

## `project passport`

Record a project passport revision pinning the index, toolchain and
config.

```bash
ai-stp project passport --root <root> --json
```

The result is a passport view (`kind` is `project`) with `stable_id`,
`revision_id`, `parent_revision_ids`, `owner_id`, `facts`,
`created_at`, and `schema_version`. See [Passports](passport.md) for
how to read that shape.

The facts pin what was observed, not what you wish were there. Changing
the tree and recording again adds a revision. It does not edit the
previous one.

## What a successful envelope contains

Discover, index, and symbols each return the fields named in their
sections. `project passport` returns the passport-view fields. Every
envelope also carries `ok`, `warnings`, `next_actions`, `request_id`,
`operation_id`, and `schema_version`.

Home paths in `root` and `path` fields are folded for display. That
rendering is not a different directory on disk.

## What these commands never do

- scan the home directory, or a whole disk;
- keep secret or binary file contents in the index;
- build a call graph, a dependency graph of packages, or a model
  embedding;
- compose a setup or write a harness target;
- put tokens or `.env` bodies into the project passport.

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` missing `--root` | every command in this group needs it | pass `--root <root>` |
| `AI_STP_VALIDATION_ERROR` home directory | discovery refuses to scan home | name a project directory inside it |
| `state: partial` on index or symbols | a size, depth, entry, or time bound was reached | read `stopped_by`; do not treat the answer as complete |
| `complete: false` on discover | the scan stopped inside its bounds | read `diagnostics` |
| `AI_STP_VALIDATION_ERROR` unreadable root | the path does not exist or cannot be read | pass an exact existing project root |
| expecting `index` to record a passport | indexing is a read | `project passport --root <root> --json` |

## Related pages

| Page | Why |
| --- | --- |
| [Passports](passport.md) | how to read a passport view |
| [Configuration](config.md) | `projects.discovery_roots` |
| [Select](select.md) | a project passport anchors a session |
| [Target](target.md) | daily state of one project and harness |
| [Component commands](component.md) | native components inside a project |
| [Quickstart](../quickstart.md) | first-run path does not require a project |

!!! note "Flags from `ai-stp help --agent --json`"
    If `help --agent` disagrees with a flag on this page, the CLI wins.
    Optional flags are not listed here. Read them from the descriptor.
    Every command here requires `--root`.
