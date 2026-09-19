---
title: "Quickstart for agents"
description: "Start every ai-stp session from task intents; run the CLI yourself; execute continuation argv only when the JSON field actor is cli; never reconstruct flags from memory."
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
ai-stp task intents --json
```

Pick one shipped intent. You run `ai-stp task start` yourself.
`envelope.continuations[0].actor` is a JSON field, not the user's identity.
When that field is `cli`, execute `argv` with your tools. When it is
`human`, do not execute that `argv`; relay `questions[0]` through
`ai-stp task answer` using bound `task`, `revision`, and `question-id`.
When it is `external`, show the payload once and stop. Do not execute
that `argv`. `provider-too-old` is not login. A device-code payload may
later take `ai-stp task continue` after the browser; never poll. Stop
when there are no continuations. Report payload
verification, not envelope `ok` alone.

Do not run `ai-stp doctor` or dump `ai-stp help --agent` as a prelude to every
request. Completing `inspect` is enough when the user asked what is wrong.
Use `ai-stp doctor --json` only when the user asked what is broken.

`help --agent --json` remains the full command registry of **this** install
when you must read a descriptor. If this page and that envelope disagree, the
CLI wins. If a command is absent from machine help, stop. Do not substitute a
similar command.

Copy every command with `--json` so stdout holds exactly one envelope. Prefer
the `argv` the CLI already emitted over typing expert leaves.

## How to read an envelope

With `ok: true`, the result is in `data`. `warnings` may still be worth
showing. With `ok: false`, `error.code` is a stable code from the closed
registry; `next_actions` is quoted display, not eval input. Use
`continuations[].argv`.

Do not guess the next step from the process exit class alone. Retry only when
the envelope says `retryable: true`. After an unconfirmed timeout, read
status before applying again. Do not replay `install apply`.

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
| `plan_digest` | machine binding of exact plan bytes. Task intents bind this in-process. Expert leaves take the digest from that family's plan command named by machine help. |

The `install`, `change`, and `switch` intents drain plan/approve/apply
in-process under task authority. Do not type `install plan` to obtain a
digest, and do not choreograph those leaves.

A read command on a fresh install returns typed emptiness. It does not
silently run `device init`.

## If inspect or doctor says identity is missing

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
`--confirm`, and is not a retry of `inspect`.

## If the Agent Skill is missing

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

Installing the file is not a substitute for reading `task intents`. After it
is present, still start every session there.

## Catalog reads are candidates

Anonymous catalog reads need no sign-in. `--kind` is required: `component`
or `setup`. A result is not permission to install.

Everyday install after a candidate exists:

```bash
ai-stp task start --intent install --idempotency-key install-session-01 --json
```

Expert catalog inspect:

```text
ai-stp registry search --kind component --json
ai-stp registry show --kind component --id <stable_id> --json
```

Before install, check the harness, the exact `X.Y`, the trust
line, and the two independent verification axes. How to read a card:
[Catalog](../catalog/index.md). `author_verified` is not
`component_verified` and neither is a safety guarantee:
[Trust and safety](../trust-and-safety/index.md).

If the network is down, a read may answer from cache. Read `checked_at`.
Do not treat a cache hit as a live catalog.

## Working loop

```text
task intents --json
→ task start (inspect | initialize | install | change | author | switch | account | publish)
→ execute continuation argv only when the JSON field actor is cli
→ task answer only for a blocked human question
→ payload verification
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
- reconstruct flags from this page when continuation `argv` or `help --agent`
  is available;
- choreograph `install plan`, `install approve`, or `install apply`;
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
| stale plan | the plan bytes changed | continue the same task; the engine replans. Do not type `install plan` |
| `ok: false` with `retryable: false` | repeating the same argv will not help | read `error.code` and `continuations` |

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
