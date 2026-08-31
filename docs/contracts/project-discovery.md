---
description: "Machine form of complete project discovery within an explicitly named scope."
last_verified: "2026-08-09"
---

# Project discovery

The requirements owner is `SPEC-004`; the traversal decision is `ADR-0053`.

`project discover --root <path> --json` is a read command. It does not create a
registry, Project, or passport and returns:

- `discovery_root` — the explicitly selected scope with a redacted home prefix;
- `complete` — proof that neither an access error nor an entry limit interrupted traversal;
- `candidates` — deterministically sorted unique roots;
- `diagnostics` — observed reasons for every omission.

A candidate contains `root`, `kind`, `state`, `markers`, and `reason`. `kind` accepts
`project` and `nested_repository`; `state` accepts `new` and `established`; the `git`
marker covers both a `.git` directory and a `.git` worktree file. A package manifest
inside a monorepo does not create a Project, but a separate Git marker is always shown.

A diagnostic contains a redacted `path`, closed `code`, and safe `reason`:

| Code | Meaning | Affects `complete` |
|---|---|---|
| `excluded` | the directory is excluded by vendor/VCS/cache/build policy | no |
| `symlink` | the symlink was not traversed | no |
| `entry_limit` | the directory contains more than the permitted number of entries | yes |
| `unreadable` | the directory or path cannot be checked | yes |

`complete=false` prohibits the agent from calling the list exhaustive. The agent shows
diagnostics and suggests narrowing the root or fixing access, then repeats the read.
No diagnostic authorizes automatic registration of a discovered root.
