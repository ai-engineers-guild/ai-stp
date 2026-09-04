---
type: release_notes
slug: web-0-1
locale: en
title: ai_stp 0.0.15 launch notes
description: "What is ready on the 0.0.15 line, which harnesses are primary or beta, and what the MVP still refuses."
published_at: 2026-08-09
tags: [release, cli]
draft: false
---

`ai-stp-cli` `0.0.15` is the current public line. The command is `ai-stp`. Install it with `uv tool install ai-stp-cli`, then run `ai-stp doctor --json`. This note is for operators who need an honest map of what the line will and will not do, not a list of web feature flags.

## Ready on this line

You can install the CLI, create a device and a developer passport, and read the public catalog without an account. You can discover native components in supported harness layouts, adopt them locally, and compile a setup from exact pins. You can ask for an install plan, approve it by digest, and apply it through the harness provider, with backup and status on the other side.

You can sign in, publish an immutable `X.Y` from a public GitHub commit, sync private revisions across your devices with `sync pull`, grant another account access to a major line, and file a closed report. The website shows the same public catalog and the account. It does not apply the setup.

Passports carry provenance, compatibility, constraints and check results in a form both a person and an agent can read. `author_verified` and `component_verified` stay independent. Mechanical compatibility and trust policy run before agent reasoning. ai_stp does not call a model API and does not require a model key.

## Harnesses

| Harness | Status on 0.0.15 |
| --- | --- |
| Claude Code | primary |
| Codex | primary |
| Grok Build | primary |
| Pi | beta |
| OpenCode | beta |
| Cursor | beta |
| Antigravity | beta |
| unknown | `undefined` — no automatic install |

Primary means the production path is designed for it first: passports, graph, provider plan, apply. Beta means the product already tells the harness apart and can work with its objects, but parts of the provider path or the native surface still ask for more confirmation. Start on a primary harness if you need the shortest checked path.

## What the MVP still is not

It is not a team product. A setup belongs to one account. Two people do not share one working project setup. Grants share objects; they do not create a shared editing session.

It is not a model router. There is no in-product call to a model interface.

It is not a promise of safety. Verified origin and current checks reduce known risk. They do not transfer responsibility for reading what an `mcp`, `hook` or `plugin` will do after the provider writes native state.

It is not a silent upgrader. Exact `X.Y` pins stay exact. Refusals stay refusals. A beta harness is labelled beta.

If the installed CLI’s machine help disagrees with a remembered flag, follow the CLI.

## How to tell this line from a web profile

Package version `0.0.15` is the CLI and catalog line this note describes. It is not a website deploy profile and not a MkDocs theme revision. `ai-stp version --json` prints `cli_version` for the binary on `PATH`. `doctor --json` reports whether that installation can work locally before you link an account.

The public catalog, publisher pages, and this content hub are readable without sign-in. Account, devices, objects, grants, and reports need OAuth and onboarding. Staff URLs are not a user surface.

## After you install

```bash
uv tool install ai-stp-cli
ai-stp doctor --json
ai-stp version --json
ai-stp capabilities --json
```

Doctor tells you whether the local installation can work before you link an account. Capabilities tell you which harnesses this binary knows. Neither installs a setup. The 142 commands live in the CLI registry, grouped in the help-center CLI map. Copy from `ai-stp help --agent --json`, not from memory.

This note does not date a next release. It does not document staff URLs. It does not list website feature flags. If the public catalog and this note disagree about a harness status, the catalog card is the live object and this note is the line description — file a report on the digest, do not invent a third status.

See also: [Quickstart](https://ai-stp.aiguild.space/en/docs/quickstart) in the help center — [for people](https://ai-stp.aiguild.space/en/docs/quickstart/human) and [for agents](https://ai-stp.aiguild.space/en/docs/quickstart/agent).
