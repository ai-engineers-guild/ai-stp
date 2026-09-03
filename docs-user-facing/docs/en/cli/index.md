---
title: "CLI"
description: "How a person and an agent use the ai_stp CLI: JSON envelopes, mutability, and the command groups."
---

# CLI

The CLI is the product's working surface. It discovers facts, records passports,
selects a composition, and asks a harness provider to apply a plan. The website
shows the catalog and the account. It does not write native harness state.

Every command that a person copies from this help center should be run with
`--json`. The CLI then prints exactly one envelope on stdout and nothing else.

## How to read an envelope

With `ok: true`, the result is in `data`. `warnings` may still be worth showing.
With `ok: false`, `error.code` is a stable code from the closed registry;
`next_actions` names a sensible next command, not a permission.

Do not guess the next step from the process exit class alone. Retry only when
the envelope says `retryable: true`. After an unconfirmed timeout, read status
before applying again.

## Mutability and confirmation

These two fields answer different questions.

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

A read command on a fresh install returns typed emptiness. It does not silently
run `device init`.

## Machine help is the parser

```bash
ai-stp help --agent --json
```

Documentation groups commands so a person can find the right page. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and the
CLI disagree, follow the CLI.

The full list, one row per command, is the [command map](commands.md).

## Command groups

| Group | Page | When you open it |
| --- | --- | --- |
| Observe | [Observe](observe.md) | first run, health, machine help |
| Configuration | [Configuration](config.md) | values this install should honour |
| Telemetry | [Install telemetry](telemetry.md) | the optional anonymous install ping |
| Device | [Device](device.md) | identity of this installation |
| Passports | [Passports](passport.md) | developer and device facts |
| Sign-in | [Sign-in](auth.md) | account session and `link web` |
| Consent | [Consent](consent.md) | unverified publishers and major lines |
| Project | [Project](project.md) | discover, index, symbols, project passport |
| Toolchain | [Toolchain](toolchain.md) | managed tools and harness survey |
| Harness program | [Harness program](harness.md) | the harness binary, not the setup |
| Agent Skill | [Agent Skill CLI](skill.md) | the CLI's own skill, not kind `skill` |
| Registry | [Registry](registry.md) | catalog search, fetch, local ports |
| Component | [Component commands](component.md) | discover → passport → publish |
| Select | [Select](select.md) | eligibility, proposal, reports |
| Install | [Install](install.md) | plan, approve, apply, recover |
| Target | [Target](target.md) | daily status, diff, backups, named rollback |
| Setup | [Setup commands](setup.md) | compose, import, update, publish |
| Provider | [Provider](provider.md) | the binary that writes native state |
| Sync | [Sync](sync.md) | private account stream |
| Grants | [Access grants](grant.md) | major-line access |
| Reports | [Reports](report.md) | closed report cases |
| Owner | [Owner objects](owner.md) | server-side objects you own |
| Publication | [Publication](publication.md) | attest, plan, confirm |
| Eval | [Eval](eval.md) | local reference evaluation |

## A working loop

```text
doctor / capabilities / help --agent
→ device + developer passport
→ registry search / show
→ select propose → confirm
→ install plan → approve → apply
→ target status
```

The agent may skip a step only when the previous envelope already made it
unnecessary. It may not skip a mechanical check.

## What the CLI never does

- call a model API or ask for a model key;
- write the harness target itself — only the public provider does;
- put secrets, `.env` bodies, or tokens into a passport;
- treat `author_verified` as proof that a component version is safe.

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| a mutating command without `--json` | mixed human text on stdout | add `--json` and read one envelope |
| stale plan | the plan bytes changed | build a new plan, show it, confirm again |
| confirmation missing | `explicit_flag` or `plan_digest` was required | read the descriptor; do not invent a flag name |
| command absent from machine help | this install does not have it | stop; do not substitute a similar command |

The first-run path in prose is the [Quickstart](../quickstart.md).
