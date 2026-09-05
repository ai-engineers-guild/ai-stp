---
title: "Component commands"
description: "The component command group: discover, passport, source, and publish."
---

# Component commands

A component is one part of a setup, of one of the closed kinds. The `component`
group is how this installation finds native files, records a local passport,
binds an external source, and prepares a version for publication.

The website shows the catalog. It does not discover a file on this machine,
write a local passport, or extract an embedded member. Those steps stay in the
CLI. Selection, assembly, and installation are other groups.

## Child pages

| Page | What it covers |
| --- | --- |
| [Discover and adopt](component-discover.md) | native discovery, local search, scaffold, adopt, forget |
| [Component passport](component-passport.md) | show, suggest, update, validate, quality |
| [Component source](component-source.md) | parse, resolve, search, GitHub archived evidence |
| [Publish a component](component-publish.md) | promote, version, fork, skill validate |

Read the child page before copying a mutating command. This overview names
every `component.*` path. It does not replace the happy path, success fields,
or refusals on those pages.

## What a component is

A component has a kind, an exact `X.Y` version, a passport, and a source. The
closed kinds are `instruction`, `skill`, `mcp`, `hook`, `command`, `agent`,
`plugin`, `setting`, and `cli`. `command` is a named slash invocation; `cli`
is a standalone executable. Memory, rules, parameters, and helper tools are
content of `instruction`, `skill`, or `setting`. They are not kinds of their
own.

A local draft is not a published version. Adopting a path registers it here.
Releasing an `X.Y` number freezes the current head. Publishing still needs a
server plan and an explicit confirmation. `author_verified` and
`component_verified` are independent: neither is a safety guarantee.

## Working loop

```text
discover / find / scaffold plan → apply
→ adopt
→ passport show → suggest → update → validate
→ source parse → resolve → evidence show
→ version release
→ component publish  or  publication plan
→ publication confirm
```

Skip a step only when the previous envelope already made it unnecessary. Do
not skip a mechanical check. Do not treat `component find` as a catalog
search: that is `registry search`. Do not treat `component publish` as the
final public write: that is `publication confirm` or `setup publish confirm`.

## Command table

`--json` is global. It is not a property of any single command. Always pass
it. `mutability` says what the command does. `confirmation` says which token
proves the decision.

### Discover and adopt

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp component discover` | `read` | `none` | list native components in harness roots and one project |
| `ai-stp component find` | `read` | `none` | search the local registry; no model, no network |
| `ai-stp component scaffold plan` | `plan` | `none` | preview exact scaffold files and digests |
| `ai-stp component scaffold apply` | `apply` | `plan_digest` | create exactly the confirmed scaffold |
| `ai-stp component template render` | `read` | `none` | render a portable template for one harness |
| `ai-stp component adopt` | `apply` | `none` | register one discovered path in the local registry |
| `ai-stp component forget` | `apply` | `none` | mark a registered component deleted, keep history |

### Passport

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp component passport show` | `read` | `none` | show the current local passport draft |
| `ai-stp component passport suggest` | `read` | `none` | suggest manifest facts without writing them |
| `ai-stp component passport update` | `apply` | `plan_digest` | add a confirmed JSON patch as a new revision |
| `ai-stp component passport validate` | `read` | `none` | name every structural blocker to publishing |
| `ai-stp component passport quality` | `read` | `none` | optional authoring hints; no trust change |

### Source

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp component source parse` | `read` | `none` | parse an external source as untrusted intent |
| `ai-stp component source resolve` | `read` | `none` | bind a GitHub intent to one full commit SHA |
| `ai-stp component source search` | `read` | `none` | search catalog names; extra lanes need a flag |
| `ai-stp component source evidence refresh` | `apply` | `none` | refresh official GitHub archived evidence |
| `ai-stp component source evidence show` | `read` | `none` | show the latest local archived evidence |
| `ai-stp component source evidence history` | `read` | `none` | bounded append-only evidence history |

### Publish

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp component publish` | `plan` | `none` | extract one embedded member into a publication plan |
| `ai-stp component version list` | `read` | `none` | every recorded version, and the next minor |
| `ai-stp component version release` | `apply` | `none` | give the current head an immutable `X.Y` |
| `ai-stp component fork` | `apply` | `none` | copy one recorded version under a new identity |
| `ai-stp component skill validate` | `read` | `none` | check a skill package against the Agent Skills Specification |

## Confirmation tokens

`plan_digest` is not always spelled `--expected-plan-digest`. Read the
descriptor. `component scaffold apply` takes `--expected-plan-digest`.
`component passport update` takes `--expected-revision` of the current head.
Neither command takes `--confirm`. A boolean beside an exact digest would ask
the same decision twice.

`component adopt`, `component forget`, `component version release`, and
`component fork` are `apply` with `confirmation: none`. Naming the path, the
id, or the version **is** the decision. Do not invent a `--confirm` flag.

`component publish` is a `plan`. It does not make the object public. Confirm
the returned plan with [Publication](publication.md).

## What this group never does

- write native harness state — only the public provider does, through
  [Install](install.md);
- call a model API or ask for a model key;
- put secrets, `.env` bodies, or tokens into a passport;
- treat `author_verified` as proof that a version is safe;
- restore a target from a backup — that is `install plan --action rollback`;
- grant major-line access — that is [Access grants](grant.md).

Consent for unverified publishers lives in [Consent](consent.md), not here.
Catalog search lives in [Registry](registry.md). Composing a mixed setup from
catalog, Git, package, and path sources lives in [Setup commands](setup.md).

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | a required option is missing or malformed | read the descriptor; add the named flag |
| `AI_STP_NOT_FOUND` | the id, path, or version is not here | discover or find first; do not guess an id |
| `AI_STP_USER_DECISION_REQUIRED` | a path answers to more than one harness or kind | pass `--harness` or `--kind` as the descriptor names them |
| `AI_STP_PLAN_STALE` | the scaffold or passport bytes changed | build a new plan, show it, confirm again |
| `AI_STP_CONFLICT` | the expected revision is no longer the head | `passport show`, then a new patch |
| `AI_STP_AUTH_REQUIRED` | a cloud publication step needs a session | `auth login`, then retry the publication command |
| command absent from machine help | this install does not have it | stop; do not substitute a similar command |

A mutating command without `--json` mixes human text onto stdout. Add `--json`
and read one envelope.

## Related links

- [Discover and adopt](component-discover.md)
- [Component passport](component-passport.md)
- [Component source](component-source.md)
- [Publish a component](component-publish.md)
- [Command map](commands.md)
- [Components](../components/index.md)
- [Publishing](../publishing/index.md)
- [Trust and safety](../trust-and-safety/index.md)
- [Select](select.md)
- [Setup commands](setup.md)
- [Publication](publication.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

Documentation groups commands so a person can find the right page. The
installed CLI is the source of flags, schemas, and `next_actions`. If this
page and the CLI disagree, follow the CLI.
