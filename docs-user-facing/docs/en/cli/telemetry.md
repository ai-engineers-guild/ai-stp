---
title: "Install telemetry"
description: "What the anonymous install ping is, how to turn it on and off, and what never goes into it."
---

# Install telemetry

`ai_stp` can send one anonymous request after a component has actually been
installed. It is **off** by default, and until you have answered the consent
prompt not a single request leaves.

It has exactly one purpose — to see what people install components on:

> Serena MCP was installed on Windows, in Codex 0.140.1

Nothing else. No profile, no history of actions, no store of events.

## Answering the consent question

To see the current state and what the request could carry at all:

```bash
ai-stp telemetry show --json
```

To answer — accept or decline. Both answers need `--confirm`, because consent
is an event and not a value that can be set in passing:

```bash
ai-stp telemetry consent --accept --confirm --json
ai-stp telemetry consent --decline --confirm --json
```

An agent must ask this once at the start of its work, not in the middle of an
installation. Nothing is blocked while you have not answered: the `not_asked`
state behaves exactly like a decline — no requests.

!!! note "A decline and a never-asked look the same from outside"
    On the wire these two states are identical, because in both nothing
    happens. Your traffic cannot distinguish someone who declined from someone
    who was never asked.

## What the request carries

One unauthenticated HTTPS `GET`. No body, no cookie, no catalog token, and no
GitHub authorisation.

| Field | Example | What it is |
| --- | --- | --- |
| `os` | `windows` | the operating system |
| `harness` | `codex` | the harness it was installed into |
| `harness_version` | `0.140.1` | its version, as the toolchain reports it |
| `ai_stp_version` | `0.0.2` | the CLI version |
| `component_type` | `mcp` | the component kind |
| `name` | `serena` | the component's public name |
| `source` | `platform` | where the object is publicly named |
| `id` | stable id or public repository URL | the component's address |
| `version` | `1.2` | the exact component version |
| `anon` | a random UUID | tells CLI installations apart |

The list is closed. A field outside this table means the contract changed, not
that the request grew on the fly.

## What never goes

Local paths, private repositories, your account identifier, the device key,
your email, the project name, the target path, environment variable names and
values, file contents, and the headers and arguments of MCP servers.

`anon` is a random identifier in the local data directory. It tells one CLI
installation from another and does nothing else: it does not equal `device_id`,
it is not tied to an account, and it is not joined with the catalog's public
counters. Delete the local data directory and it becomes a different one.

If a component cannot be named publicly — no name, no kind — no request is sent
at all, even with telemetry enabled.

## Exactly when it is sent

After a successful apply with the `install` or `update` action, one request per
component actually installed. A setup of three components produces three
requests.

Nothing is sent on `backup`, `rollback` or `remove`, on any read, in offline
mode, or in tests.

## If the request does not arrive

A network error, a timeout, and any answer other than success are swallowed
silently. The installation stays `verified`: its result is a property of your
target, not of a collector. There are no retries and no batching.

## Turning it off

```bash
ai-stp telemetry consent --decline --confirm --json
```

There is also the environment variable `AI_STP_TELEMETRY_SUPPRESS`: it silences
sending regardless of the recorded consent. That is an emergency switch for
environments where outgoing traffic is unacceptable, not a replacement for
answering the prompt.

Writing `telemetry.enabled=true` into the configuration directly is refused —
telemetry can only be turned on by explicit consent.

The machine boundary in full is in the `cli-telemetry.md` contract; here it is
retold for a person, not defined.
