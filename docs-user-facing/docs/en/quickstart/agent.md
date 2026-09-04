---
title: "Quickstart for agents"
description: "Start every ai-stp session from doctor and machine help; never reconstruct flags from memory."
---

# Quickstart for agents

This page is the first-run and every-session ritual for a coding agent that
drives `ai-stp`. A person installing the binary should use
[Quickstart for people](human.md).

The executable is `ai-stp`. The PyPI distribution is `ai-stp-cli`. There is
no `ai-stp docs` command. Documentation names commands so a person can find a
page. **You** must not reconstruct flags, schemas, or `next_actions` from
memory when the installed CLI already answers with them.

## Every session starts here

```bash
ai-stp doctor --json
ai-stp capabilities --json
ai-stp help --agent --json
```

Read `doctor` before inventing the next step. If a check is
`needs_user_action`, follow that check, not a remembered ritual.

`capabilities` answers which surfaces **this build** can talk to right now.
Do not infer harness support from a version string.

`help --agent --json` is the command registry of **this** install. If this
page and that envelope disagree, the CLI wins. If a command is absent from
machine help, stop. Do not substitute a similar command.

Copy every command with `--json` so stdout holds exactly one envelope.

## How to read an envelope

With `ok: true`, the result is in `data`. `warnings` may still be worth
showing. With `ok: false`, `error.code` is a stable code from the closed
registry; `next_actions` names a sensible next command, not a permission.

Do not guess the next step from the process exit class alone. Retry only when
the envelope says `retryable: true`. After an unconfirmed timeout, read
status before applying again.

## Mutability and confirmation

These two fields answer different questions. Details:
[CLI](../cli/index.md).

| `mutability` | Meaning |
| --- | --- |
| `read` | observes; creates nothing |
| `plan` | records a checkable plan or snapshot; does not change the target |
| `apply` | changes state |
| `destructive` | discards identity or managed bytes; always a separate decision |

| `confirmation` | Meaning |
| --- | --- |
| `none` | no extra token; this is not "safe to run unasked" |
| `explicit_flag` | pass the flag the descriptor names, usually `--confirm` |
| `plan_digest` | pass `--expected-plan-digest` of an unchanged plan |

A read command on a fresh install returns typed emptiness. It does not
silently run `device init`.

## If doctor says identity is missing

Ask the human to create local identity, or run the same commands they would.
This is not an account. Details: [Device](../cli/device.md),
[Passports](../cli/passport.md).

```bash
ai-stp device init --json
ai-stp device show --json
ai-stp passport developer init --json
ai-stp passport device refresh --json
```

`device init` is idempotent. `device reset` is destructive, needs
`--confirm`, and is not a retry of `doctor`.

## If doctor says the Agent Skill is missing

This is the CLI's own Agent Skill: the procedure you read to drive `ai-stp`.
It is **not** a component of kind `skill`. Mixing the two is how a workflow
file gets overwritten. Details: [Agent Skill CLI](../cli/skill.md).

```bash
ai-stp skill status --target <dir> --json
ai-stp skill install --target <dir> --json
```

`--target` is required. It is the directory the harness reads its native
skill from. Do not guess that directory. If you do not know it, ask the
human or the harness documentation.

Installing the file is not a substitute for reading machine help. After it
is present, still start every session with `doctor` and `help --agent`.

## Catalog reads are candidates

Anonymous catalog reads need no sign-in. `--kind` is required: `component`
or `setup`. A result is not permission to install.

```bash
ai-stp registry search --kind component --json
ai-stp registry show --kind component --id <stable_id> --json
```

Before any select or apply, check the harness, the exact `X.Y`, the trust
line, and the two independent verification axes. How to read a card:
[Catalog](../catalog/index.md). `author_verified` is not
`component_verified` and neither is a safety guarantee:
[Trust and safety](../trust-and-safety/index.md).

If the network is down, a read may answer from cache. Read `checked_at`.
Do not treat a cache hit as a live catalog.

## Working loop

```text
doctor / capabilities / help --agent
→ device + developer passport (only if doctor asked)
→ registry search / show
→ select propose → confirm
→ install plan → approve → apply
→ target status
```

Skip a step only when the previous envelope already made it unnecessary.
Do not skip a mechanical check. Do not write native harness files; only the
public provider does. Details: [Select](../cli/select.md),
[Install](../cli/install.md), [Provider](../cli/provider.md).

The full loop in prose for a person is [Quickstart for people](human.md).
The command groups are [CLI](../cli/index.md). One row per command:
[Command map](../cli/commands.md).

## What you must not do

- call a model API or ask for a model key;
- reconstruct flags from this page when `help --agent` is available;
- treat `author_verified` as proof that a version is safe;
- install from a catalog headline percent;
- skip `--json` on a mutating command;
- apply a stale plan digest;
- invent a harness skill directory when `--target` is missing.

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `ai-stp` not found | the tool is missing or not on `PATH` | tell the human to install `ai-stp-cli`; see [Quickstart for people](human.md) |
| doctor `device_identity` is not `ready` | identity was never created, or the store cannot read it | `ai-stp device init --json` if it was never created; otherwise read `detail` |
| command absent from `help --agent` | this install does not have it | stop; do not substitute a similar command |
| `AI_STP_VALIDATION_ERROR` missing `--target` | a destination directory is required | pass `--target <dir>`; do not guess the path |
| stale plan | the plan bytes changed | build a new plan, show it, confirm again |
| `ok: false` with `retryable: false` | repeating the same argv will not help | read `error.code` and `next_actions` |

## Related pages

- [Quickstart](index.md) — choose the human path or the agent path.
- [Quickstart for people](human.md) — install the binary and create identity.
- [Observe](../cli/observe.md) — `doctor`, `capabilities`, `help --agent`.
- [CLI](../cli/index.md) — envelopes and command groups.
- [Command map](../cli/commands.md) — one row per command.
- [Agent Skill CLI](../cli/skill.md) — the control-plane skill, not kind `skill`.
- [Troubleshooting](../troubleshooting/index.md) — after a red check.

!!! note "Commands here are a map, not a parser"
    If `help --agent` disagrees with a flag on this page, the CLI wins.
    Optional flags are not listed here. Read them from the descriptor.
