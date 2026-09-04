---
title: "Toolchain"
description: "Install and remove managed tools, read the pinned profile, and survey harnesses and native capabilities."
---

# Toolchain

The managed toolchain is a pinned profile, not a random `pip install`.
`toolchain install` writes into the managed directory and runs nothing
from the tool it just placed. `toolchain harnesses` reports whether a
supported harness is on this machine. `toolchain harness-capabilities`
says what the product can natively read and what this build can
project. It is not a claim that a component is active.

This is not [Harness program](harness.md). Installing the harness
binary is `harness install`. This is not [Provider](provider.md). The
provider is the binary that later writes native state.

## Commands

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp toolchain install` | `apply` | `none` | Install one pinned tool into the managed directory. Runs nothing from it. |
| `ai-stp toolchain remove` | `destructive` | `explicit_flag` | Remove one managed tool, touching only paths this CLI created. |
| `ai-stp toolchain profile` | `read` | `none` | Show the managed toolchain profile as it resolves on this machine. |
| `ai-stp toolchain harnesses` | `read` | `none` | Report every supported harness and whether it is on this machine. |
| `ai-stp toolchain harness-capabilities` | `read` | `none` | Per harness and kind: what the product natively reads, what this build can project, and why any gap is a gap. Not a claim that a component is active — ask the provider for that. |

`--tool` is required on `install` and `remove`. `remove` also requires
`--confirm`. Exact tool identifiers come from `toolchain profile`, not
from memory.

## Typical path

Read the profile, then install one pinned tool, then look at harnesses:

```bash
ai-stp toolchain profile --json
ai-stp toolchain install --tool <tool> --json
ai-stp toolchain harnesses --json
ai-stp toolchain harness-capabilities --json
```

`<tool>` is an identifier the profile pins. If `doctor` reported a
missing tool, the name is in that check's `detail` or in the profile's
`ecosystems[].tools`. Do not invent a package name.

To take a managed tool back:

```bash
ai-stp toolchain remove --tool <tool> --confirm --json
```

`--confirm` is required. Without it the command refuses with
`AI_STP_USER_DECISION_REQUIRED`. Removal touches only paths this CLI
created. Anything not on the ownership list is left in place and
reported as kept.

## `toolchain profile`

Show the managed toolchain profile as it resolves on this machine.

```bash
ai-stp toolchain profile --json
```

This is a read. It downloads nothing and installs nothing.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `profile` | which profile this is |
| `platform` | the platform it resolved for |
| `ecosystems` | each with `ecosystem`, `title`, `state`, `tools`, `reason` |
| `schema_version` | the schema major of this report |

Ecosystem `state` is `available` or `not_available`. Each pinned tool
carries identity, version, digest, and digest source. `digest_source`
is `vendor_published` or `pinned_on_download`.

## `toolchain install`

Install one pinned tool into the managed directory. Runs nothing from
it.

```bash
ai-stp toolchain install --tool <tool> --json
```

Plan first, then verify, then unpack beside the target, then move a
single pointer. Nothing from the archive is executed. Nothing outside
the user's own data directory is written, so there is no path here that
would want a password.

`action` in the result is what happened, not what was attempted:

| `action` | Meaning |
| --- | --- |
| `installed` | the tool was placed and verified |
| `already_installed` | the pinned bytes were already current |
| `needs_user_action` | something outside the managed directory would have to change |

`needs_user_action` is not a prompt for a secret. The `reason` says
exactly what would have to change.

## `toolchain remove`

Remove one managed tool, touching only paths this CLI created.

```bash
ai-stp toolchain remove --tool <tool> --confirm --json
```

Destructive. The ownership manifest is the list. Deciding at removal
time which files “look like ours” is how a cleanup takes a user's own
data with it, so anything not on the list is left in place.

`action` is `removed`. `kept` names paths that were not this CLI's.

## `toolchain harnesses`

Report every supported harness and whether it is on this machine.

```bash
ai-stp toolchain harnesses --json
```

This is a survey of presence, not a program lifecycle. `harness status`
answers a different question: what program stands under one prefix
this CLI installed. The two vocabularies are kept disjoint.

Successful `data` names:

| Field | What it is |
| --- | --- |
| `harnesses` | one row per supported harness |
| `schema_version` | the schema major of this report |

Each row names `harness_id`, `title`, `support` (`primary` or `beta`),
`state` (`configured`, `installed`, `unknown_version`, or `available`),
`installations`, `configuration`, and `reason`. An installation names
`path`, `version`, `version_source`, `surface` (`cli` or `desktop`),
and `diagnostic`.

Presence is not permission to compose for that harness. Eligibility is
[Select](select.md). Support levels are [Harnesses](../harnesses.md).

## `toolchain harness-capabilities`

Per harness and kind: what the product natively reads, what this build
can project, and why any gap is a gap. Not a claim that a component is
active — ask the provider for that.

```bash
ai-stp toolchain harness-capabilities --json
```

Successful `data` names `harnesses`. Each row is one harness, with
component kinds, native layouts, projection ability, and `gaps`. A gap
is a reason, not a hint to invent a workaround.

This command does not ask a provider whether a component is currently
active in a target. That question belongs to [Provider](provider.md)
and [Target](target.md).

## What a successful envelope contains

`install` and `remove` return a tool installation in `data`:

| Field | What it is |
| --- | --- |
| `tool_id` | the identifier you passed |
| `version` | the pinned version |
| `action` | `installed`, `already_installed`, `needs_user_action`, or `removed` |
| `reason` | why that action is the outcome |
| `binary` | where the managed binary is, or `null` |
| `paths` | paths this command created |
| `kept` | paths this command refused to touch |
| `offline_capable` | whether the result can be reproduced from cache |
| `schema_version` | the schema major of this report |

`profile`, `harnesses`, and `harness-capabilities` return the fields
named in their sections. Every envelope also carries `ok`, `warnings`,
`next_actions`, `request_id`, `operation_id`, and `schema_version`.

## What these commands never do

- execute the tool they just installed;
- write outside the managed directory;
- install the harness program (`harness install`) or the provider
  (`provider fetch`);
- claim that a component is active in a target;
- put a secret into the profile or the installation record.

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` missing `--tool` | install and remove require it | pass `--tool <tool>` from the profile |
| `AI_STP_NOT_FOUND` | the profile pins no tool by that name | `toolchain profile --json` and use an identifier it lists |
| `AI_STP_PRECONDITION_FAILED` no artifact for this platform | the tool is pinned, but not for this machine | read `details.available`; do not fetch a random binary |
| `AI_STP_USER_DECISION_REQUIRED` on remove | `--confirm` was missing | `toolchain remove --tool <tool> --confirm --json` |
| `action: needs_user_action` | something outside the managed directory must change | read `reason`; do not supply a password to the CLI |
| treating `harness-capabilities` as “it is installed” | that table is native read plus projection | `toolchain harnesses` and `harness status` |

## Related pages

| Page | Why |
| --- | --- |
| [Observe](observe.md) | `doctor` after a tool is missing |
| [Harness program](harness.md) | the harness binary, not the tool |
| [Provider](provider.md) | the binary that writes native state |
| [Harnesses](../harnesses.md) | primary vs beta support |
| [Agent Skill CLI](skill.md) | a different missing-first-run object |
| [Quickstart for people](../quickstart/human.md) | the toolchain tab of first run |

!!! note "Flags from `ai-stp help --agent --json`"
    If `help --agent` disagrees with a flag on this page, the CLI wins.
    Optional flags are not listed here. Read them from the descriptor.
    `toolchain install` requires `--tool`. `toolchain remove` requires
    `--tool` and `--confirm`.
