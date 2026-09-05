---
type: blog_post
slug: first-content
locale: en
title: The agent is the consumer. The web is not the installer.
description: "ai-stp-cli 0.0.15 puts the catalog, CLI and harness providers in one product. The website does not apply setups."
published_at: 2026-08-11
tags: [product, web]
draft: false
---

ai_stp is a system for creating, validating, storing, selecting and installing complete AI harness configurations. The primary consumer is the user’s coding agent, driving a strict CLI. The website owns the account and the public catalog and displays results. It does not select a composition, it does not assemble a bundle, and it does not write native harness state.

The distribution on PyPI is `ai-stp-cli`. The executable is `ai-stp`. Copying `uv tool install ai-stp` installs a package this project does not publish. Current line: `0.0.15`.

## What the product actually is

A **harness** is the CLI environment a coding agent runs in. A **setup** is the complete configuration of one harness; it belongs to that harness from creation. A **component** is a part of a setup of one of the closed kinds: `instruction`, `skill`, `mcp`, `hook`, `command`, `agent`, `plugin`, `setting`, `cli`. `command` is a named slash invocation; `cli` is a standalone executable. Memory, rules, parameters and helper tools are content of those kinds, not extra kinds.

A published version pins exact component versions and is immutable. Trust is origin, version and consent. Compatibility — graph, target and policy — decides before apply. `author_verified` and `component_verified` are independent. Only the harness’s public provider writes native files.

That split is the product, not a temporary architecture. The agent can reason about candidates. It cannot override a mechanical refusal. The web can show a card. It cannot apply the card.

## Who writes what

Local work needs no account. `device init` and a developer passport are enough to inspect, adopt and compose privately. The public catalog is readable anonymously from the CLI and from the website.

Google or GitHub sign-in unlocks private objects, sync, publication, devices and grants. Sign-in does not move assembly onto the website. The path stays:

```text
CLI → passports → project index → search → setup assembly → checks
→ install plan → backup → apply through the provider → status
```

The CLI returns one JSON envelope per command. Flags, schemas and `next_actions` come from `ai-stp help --agent`, not from memory of a blog post. Documentation groups commands so a person can find the right page. If a page and the installed CLI disagree, the CLI wins.

ai_stp does not call model interfaces and does not require a model key. The one outgoing request the CLI makes on its own behalf is an optional anonymous install ping, off until the operator says otherwise.

## Harnesses on this line

Primary support is Claude Code, Codex and Grok Build. Those are the production path: passports, compatibility, setup assembly, provider plan and apply.

Pi, OpenCode, Cursor and Antigravity are beta. Catalog and compatibility exist. Parts of the provider path, the native surface or the UX are still stricter and may ask for more confirmation. An unknown harness is `undefined`: fine for reading, import and local checks, refused for automatic installation.

A setup is not portable by rename. The same English words mean different files and events in different CLIs. Moving a composition to another harness is an explicit new version.

## What this line does not pretend to be

There is no team shared setup. A setup belongs to an account, not to a git repository. A colleague who clones the project assembles their own. Grants can share a private object with another account; that is an author–recipient relationship, not two people editing one working setup.

There is no in-product model API. There are no ratings, no public comment threads, and no promise that a published object is harmless. Verified means the platform confirmed an identity or a version’s current checks. It does not transfer responsibility for reading `mcp`, `hook` and `plugin` permissions.

## Where to start

Install from PyPI with `uv tool install ai-stp-cli`, then let the agent read `doctor` and machine help. The website is for the catalog, the account, devices and publication status. When you are ready to change a target, you are back in the CLI, and the writer is the provider.

See also: [Quickstart](https://ai-stp.aiguild.space/en/docs/quickstart) in the help center — [for people](https://ai-stp.aiguild.space/en/docs/quickstart/human) and [for agents](https://ai-stp.aiguild.space/en/docs/quickstart/agent).
