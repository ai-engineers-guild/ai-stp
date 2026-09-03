---
title: "Concepts"
description: "The ai_stp concepts a user and an agent need."
---

# Concepts

These are the words `ai_stp` uses with one meaning each. If a sentence uses
two of them as if they were the same object, the sentence is wrong.

## Harness

A harness is the CLI environment a coding agent runs in. `ai_stp` does not
replace it and does not call models.

Primary support: Claude Code, Codex, Grok Build. Beta: Pi, OpenCode, Cursor,
Antigravity. Unknown: limited `undefined`.

More: [supported harnesses](../harnesses.md).

## Setup

A setup is the complete configuration of one harness. It belongs to that
harness from the moment it is created, and it pins exact component versions.

Any change to what it contains produces a new version of the setup. Versions
are `X.Y`, not SemVer: there is no patch number, and a published `X.Y` is
immutable.

More: [setups](../setups/index.md).

## Component

A component is one part of a setup, of one of eight kinds. Memory, rules,
parameters and helper tools are the *content* of an `instruction`, a `skill`
or a `setting` — not kinds of their own.

The eight kinds, and how to choose among them, live on
[component kinds](../components/index.md). This page does not repeat that
list.

## Provider versus assembler

Two different objects do two different jobs.

The **setup assembler** is the deterministic `ai_stp` layer. It validates the
component graph, refuses incompatibilities, and creates a native package for
the provider. It does not write the harness's files.

The **provider** is the public NDDev setup manager for that harness. It is
the only writer of the harness's final state. Before it writes, it produces a
plan. After it writes, it records status that `ai_stp` can read.

If those two roles collapse into one sentence — "ai_stp installed the
files" — the install path is being described incorrectly. `ai_stp` planned
and compiled; the provider applied.

## Passport

A passport is a versioned, machine-readable description of an object. Through
passports, `ai_stp` ties together provenance, compatibility, constraints and
check results.

A passport never holds secrets, `.env` bodies, tokens, or private paths.

## Trust line

The trust line decides how an object reaches a result set:

- `authoritative`;
- `experimental`;
- `local_owner_or_pinned`.

An unverified object takes no part in automatic installation without the
user's explicit consent.

`author_verified` and `component_verified` are independent axes. Neither
follows from the other.

More: [trust and safety](../trust-and-safety/index.md).

## Digest-bound plan

Any write that can change a target, a publication, or a local version starts
as a plan. The plan has a digest. Apply repeats the computation and refuses
if the digest no longer matches.

Typical tokens:

- `--expected-plan-digest` for scaffold, passport update, compose, install
  approve, and setup import;
- `--plan-hash` for a publication plan;
- `--set-digest` for a setup publication set;
- `--confirm` when the confirmation kind is an explicit flag.

A stale digest is not a hint to force the old plan through. Build a new plan
and confirm that one. See [troubleshooting](../troubleshooting/index.md).

## Three modes

`ai_stp` works in three overlapping modes. They are not product editions.

=== "Local"

    Device identity and a developer passport are enough. You can discover
    native components, adopt them, compose a setup from local and pinned
    sources, and ask a provider to apply — without an account.

    ```bash
    ai-stp device init --json
    ai-stp passport developer init --json
    ai-stp doctor --json
    ```

=== "Anonymous"

    The public catalog can be read without signing in. Search, show, and
    version are catalog reads. They do not grant, publish, or sync.

    ```bash
    ai-stp registry search --kind setup --query frontend --json
    ai-stp registry show --kind setup --id <stable_id> --json
    ```

=== "Signed-in"

    An account is required for publication, synchronisation, grants, owner
    objects, and device binding to the cloud session.

    ```bash
    ai-stp auth login --provider github --json
    ai-stp auth status --json
    ```

Local work stays local until you publish or sync. Anonymous catalog reads
never become a session. Signing in does not by itself install anything.

## Device

A device is the identity of this installation: a stable identifier and a
signing key. The private key lives in the operating system's secret store
when a trusted backend is present, and in an owner-only file otherwise.
`doctor` names the tier. There is no silent fallback that pretends a
plaintext file is a keychain.

```bash
ai-stp device init --json
ai-stp device show --json
```

`device reset` is destructive, needs `--confirm`, and is not a way to retry
`doctor`. Details: [Device](../cli/device.md).

## Project

A project is one indexed root. `ai_stp` discovers it, indexes it without
reading secrets or binary content, and can record a project passport that
pins the index, toolchain and config.

```bash
ai-stp project discover --root . --json
ai-stp project index --root . --json
ai-stp project passport --root . --json
```

A setup is installed into a project-harness pair. Status, diff, backups and
the named rollback of that pair are [target](../cli/target.md) commands.

Details: [Project](../cli/project.md).

## Related pages

- [Quickstart for people](../quickstart/human.md) — install and first catalog
  read.
- [Quickstart for agents](../quickstart/agent.md) — session ritual.
- [Supported harnesses](../harnesses.md) — primary, beta, `undefined`.
- [Components](../components/index.md) — the eight kinds.
- [Setups](../setups/index.md) — exact pins, one harness.
- [CLI](../cli/index.md) — envelopes and command groups.
- [Catalog](../catalog/index.md) — how to read a public result.
- [Trust and safety](../trust-and-safety/index.md) — two verification axes.
