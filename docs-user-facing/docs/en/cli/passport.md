---
title: "Passports"
description: "Create, show, and update the developer and device passports this installation keeps locally."
---

# Passports

A passport is a versioned, machine-readable description of an object.
This page is only the two passports that describe *you* and *this
machine*: the developer passport and the device passport. Component,
setup, and project passports are different objects with different
commands.

The developer passport declares preferences. The device passport
records what is observable on this machine. Those facts are not
interchangeable. A field that belongs to the environment is refused on
the developer passport, and a preference is not an observation.

## Commands

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp passport developer init` | `apply` | `none` | Create the developer passport of this installation. |
| `ai-stp passport developer show` | `read` | `none` | Show the developer passport at its current head. |
| `ai-stp passport developer update` | `apply` | `none` | Declare developer facts, adding one revision. |
| `ai-stp passport device refresh` | `apply` | `none` | Create this device passport, or bring it up to what is observable now. |
| `ai-stp passport device show` | `read` | `none` | Show this device passport at its current head. |

`passport developer init` is idempotent: running it twice is a no-op
rather than a second passport. `passport device refresh` writes a
revision only when something actually changed, but it can add history,
so the class is `apply`.

## Typical path

After the device identity exists:

```bash
ai-stp device init --json
ai-stp passport developer init --json
ai-stp passport developer show --json
ai-stp passport device refresh --json
ai-stp passport device show --json
```

To declare developer facts, adding one revision:

```bash
ai-stp passport developer update --set role=<role> --json
ai-stp passport developer show --json
```

`--set` is required on `update`. Repeat it for several fields. The form
is `name=value`; a comma-separated value becomes a list. Exact field
names come from `ai-stp help --agent --json` and from a refused call
that names the allowed set.

Local work does not need an account. Before sign-in the owner is a
local `account_…` minted on first use. Sign-in transfers ownership to
the server's account as an ordinary revision. It does not rewrite
history.

## Developer passport

The developer passport holds declared facts about the person using this
installation. The closed field list is:

| Field | What it is for |
| --- | --- |
| `role` | how you describe your role |
| `typical_tasks` | the work you usually ask the agent to do |
| `priorities` | what should win when goals compete |
| `preferred_languages` | languages you prefer to work in |
| `preferred_harnesses` | harnesses you prefer to compose for |
| `autonomy` | how far the agent may go without asking |

These never belong on the developer passport. They are environment
observations and they belong to the device:

- `operating_system`
- `architecture`
- `installed_harnesses`
- `harness_versions`
- `tool_versions`

Writing one of those with `passport developer update` is refused.

### `passport developer init`

Create the developer passport of this installation.

```bash
ai-stp passport developer init --json
```

It creates durable state. A second run returns the existing head. It
does not invent preferences: empty facts are valid until you declare
them with `update`.

### `passport developer show`

Show the developer passport at its current head.

```bash
ai-stp passport developer show --json
```

This is a read. If the passport was never created, the command refuses
with `AI_STP_NOT_FOUND`. Observing does not mint it.

### `passport developer update`

Declare developer facts, adding one revision.

```bash
ai-stp passport developer update --set role=<role> --json
```

Each successful call adds one revision on the current head. The
previous revision remains in history. There is no in-place edit.
Unknown names are refused. Environment names are refused. Secrets are
not representable here.

## Device passport

The device passport describes the environment: operating system,
architecture, installed harnesses, versions the toolchain can see.
It is not the device identity. The identity is `device_id` plus a key
pair; see [Device](device.md).

### `passport device refresh`

Create this device passport, or bring it up to what is observable now.

```bash
ai-stp passport device refresh --json
```

If nothing observable changed, the head stays where it was. If
something changed, a new revision is recorded. Either way the command
is an apply, not a read: it is allowed to add history.

Refresh does not install a harness, a toolchain, or an Agent Skill. It
records what is already there.

### `passport device show`

Show this device passport at its current head.

```bash
ai-stp passport device show --json
```

This is a read. If the passport was never created, the command refuses
and `next_actions` names `passport device refresh`.

## What a successful envelope contains

All five commands return the same result shape in `data`:

| Field | What it is |
| --- | --- |
| `kind` | `developer` or `device` on this page |
| `stable_id` | the passport's stable identifier |
| `revision_id` | the current head revision |
| `parent_revision_ids` | what this revision descends from |
| `owner_id` | the local or account owner |
| `facts` | the declared or observed facts at this head |
| `created_at` | when this revision was recorded |
| `schema_version` | the schema major of this view |

This is a view, not the passport bytes themselves. The envelope and its
facts are owned by the passport model. What the CLI adds is the local
position: which revision is current, and what it descends from.

The envelope also carries `ok`, `warnings`, `next_actions`,
`request_id`, `operation_id`, and `schema_version`.

`kind` on other commands may also be `project`, `component`, or
`setup`. Those are not this page. Project passports are
[Project](project.md). Component passports are
[Component passport](component-passport.md).

## What these commands never do

- put secrets, `.env` bodies, or tokens into a passport;
- copy OS or harness observations onto the developer passport;
- copy preferences onto the device passport;
- create a device identity (`device init` does that);
- publish anything to the catalog;
- write a harness target.

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_NOT_FOUND` on `developer show` | the developer passport was never created | `ai-stp passport developer init --json` |
| `AI_STP_NOT_FOUND` on `device show` | the device passport was never created | `ai-stp passport device refresh --json` |
| `AI_STP_VALIDATION_ERROR` on `update` | unknown field, environment field, or missing `--set` | use a developer field; read the allowed set in `details` |
| `doctor` reports no device | identity is missing, so device facts cannot be observed honestly | `ai-stp device init --json` first |
| expecting `device show` to print OS facts | that is the passport, not the identity | `ai-stp passport device show --json` |

## Related pages

| Page | Why |
| --- | --- |
| [Concepts](../concepts/index.md) | what a passport is |
| [Device](device.md) | identity, not environment |
| [Project](project.md) | `project passport` pins an index |
| [Component passport](component-passport.md) | passports of adopted components |
| [Sign-in](auth.md) | ownership transfer on first login |
| [Sync](sync.md) | pushing a developer-passport head |
| [Quickstart](../quickstart.md) | first-run identity and passports |

!!! note "Flags from `ai-stp help --agent --json`"
    If `help --agent` disagrees with a flag on this page, the CLI wins.
    Optional flags are not listed here. Read them from the descriptor.
    `passport developer update` requires `--set`.
