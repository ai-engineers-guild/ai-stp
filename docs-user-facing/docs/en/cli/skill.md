---
title: "Agent Skill CLI"
description: "Install, inspect, and remove the canonical ai-stp Agent Skill at a named destination, not a skill component."
---

# Agent Skill CLI

This is the CLI's own Agent Skill: the procedure an agent reads to
drive `ai-stp`. It is **not** a component of kind `skill` inside a
setup. Those are [skill components](../components/skill.md). Mixing the
two is how an agent overwrites a user's workflow file, or skips
installing the control-plane skill because a catalog card exists.

The Skill is what an agent reads to learn how to drive this CLI, so an
installation that carries the binary and not the procedure has
delivered half a product. After it is present, the agent still starts
every session with `doctor` and `help --agent`.

The destination is named rather than discovered. Where each harness
looks for a native skill is a fact about that harness. This command
group will not search the disk for a likely folder. If you do not
know the directory, ask the harness documentation, not this CLI.

## Commands

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp skill install` | `apply` | `none` | Install the canonical Agent Skill at a named destination. |
| `ai-stp skill status` | `read` | `none` | Report what Agent Skill is at a destination and who owns it. |
| `ai-stp skill remove` | `apply` | `none` | Remove the Agent Skill this installation put at a destination. |

`--target` is required on all three. It is the directory the harness
reads its native skill from. There is no configured fallback. The CLI
does not guess the harness's skill directory.

`remove` is `apply`, not `destructive`. It takes back a file this
installation wrote. It does not discard identity or the local
registry.

## Typical path

```bash
ai-stp skill status --target <dir> --json
ai-stp skill install --target <dir> --json
ai-stp skill status --target <dir> --json
```

`<dir>` is the directory the harness reads its native skill from, not
a project root and not the managed toolchain directory. Exact layout
is a fact about that harness. Inventing those paths would be a guess
presented as support.

If `status` reports `owned`, you are done. If it reports `absent`,
install. If it reports `foreign` or `stale`, do not install over it.

To take back only what this installation wrote:

```bash
ai-stp skill remove --target <dir> --json
ai-stp skill status --target <dir> --json
```

## Two different `skill` words

| Object | Page | What it is |
| --- | --- | --- |
| Agent Skill CLI | this page | the procedure for driving `ai-stp` |
| Component kind `skill` | [skill](../components/skill.md) | a portable agent workflow inside a setup |

`skill install` does not publish a component. `component skill
validate` does not install this file. Catalog search for kind `skill`
does not tell you whether this destination is owned.

## `skill status`

Report what Agent Skill is at a destination and who owns it.

```bash
ai-stp skill status --target <dir> --json
```

Creates nothing, including the destination directory.

`state` is one of:

| `state` | Meaning |
| --- | --- |
| `absent` | no skill file is there |
| `owned` | this installation wrote it, and the digest still matches |
| `foreign` | something else put a skill there; it is not ours to replace |
| `stale` | this installation wrote it, and someone edited the file afterwards |

## `skill install`

Install the canonical Agent Skill at a named destination.

```bash
ai-stp skill install --target <dir> --json
```

Writes one file and its ownership record. It refuses to replace a
skill this installation did not write (`foreign`) and refuses to
overwrite a file that was edited after this installation wrote it
(`stale`).

Idempotent on an `owned` destination: installing the same text again
rewrites the same bytes and the answer is unchanged.

A `--harness` option exists in machine help to install the native
projection for one harness instead of the canonical skill. It is not
required. If you pass it, the value must be a harness this build
ships a projection for. Read the descriptor before adding it.

## `skill remove`

Remove the Agent Skill this installation put at a destination.

```bash
ai-stp skill remove --target <dir> --json
```

Removes only what the ownership record claims. A file this CLI did
not write is left alone and said so (`AI_STP_CONFLICT`). The local
registry and anything the user set up are a different thing and are
never touched: this is the control plane, not their data.

Removing an `absent` destination is a successful no-op: `state` stays
`absent`.

## What a successful envelope contains

All three commands return the same result shape in `data`:

| Field | What it is |
| --- | --- |
| `state` | `absent`, `owned`, `foreign`, or `stale` |
| `target` | the destination directory, as displayed |
| `digest` | the skill file digest, or `null` |
| `harness` | the projection that was installed, or `null` for canonical |
| `available_harnesses` | harnesses this build can project for |
| `schema_version` | the schema major of this report |

The envelope also carries `ok`, `warnings`, `next_actions`,
`request_id`, `operation_id`, and `schema_version`.

`foreign` can appear on a successful `status`. It is not a success on
`install` or `remove`: those refuse with `AI_STP_CONFLICT`.

## What these commands never do

- install a `skill` component into a setup;
- guess the harness skill directory when `--target` is missing;
- overwrite a foreign or stale file;
- touch the local registry, passports, or cached catalog bytes;
- start an agent session or call a model API;
- write a harness target.

After the file is present, the agent still starts every session with:

```bash
ai-stp doctor --json
ai-stp help --agent --json
```

The Skill tells it to do that. Installing the file is not a substitute
for reading machine help.

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` missing `--target` | a destination directory is required | pass `--target <dir>` |
| `AI_STP_VALIDATION_ERROR` unknown harness | no projection is shipped for that name | `capabilities --json` and use a supported harness |
| `AI_STP_CONFLICT` on install, `foreign` | a skill this installation does not own is already there | `skill status --target <dir> --json`; do not overwrite it |
| `AI_STP_CONFLICT` on install, `stale` | the installed skill was edited after this installation wrote it | `skill remove --target <dir> --json` only if you mean to discard those edits |
| `AI_STP_CONFLICT` on remove | that skill was not installed by this installation | leave it; this is not yours to delete |
| searching the catalog for a skill | that is kind `skill`, a component | [skill components](../components/skill.md) |

## Related pages

| Page | Why |
| --- | --- |
| [skill components](../components/skill.md) | the other meaning of `skill` |
| [Observe](observe.md) | `doctor` and `help --agent` after install |
| [Harness program](harness.md) | the program that will read this file |
| [Toolchain](toolchain.md) | a different missing-first-run object |
| [Component commands](component.md) | adopt and publish kind `skill` |
| [Quickstart](../quickstart.md) | the Agent Skill tab of first run |

!!! note "Flags from `ai-stp help --agent --json`"
    If `help --agent` disagrees with a flag on this page, the CLI wins.
    Optional flags are not listed here. Read them from the descriptor.
    Every command here requires `--target`.
