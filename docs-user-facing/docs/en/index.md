---
title: "Overview"
description: "Understand ai_stp, its trust model, and the path from catalog to installed setup."
---

<!--
THESIS: public docs explain ai_stp from the user's daily path, while internal docs keep architecture and requirements out of the help center.
OWN-WORLD: restrained MkDocs Material reading surface, English prose, narrow pages, explicit navigation, code examples only where they help action.
STORY: a developer and their agent understand what ai_stp does, install the CLI, read catalog evidence, assemble a setup, and recover safely.
FIRST VIEWPORT: search, left navigation, concise product definition, and direct links to quickstart and trust guidance before deeper reference.
FORM: MVP documentation site, category-standard static docs chosen deliberately for reliability; FINISH: unreviewed and undocumented is unfinished.
-->

# ai_stp

`ai_stp` helps a developer and their coding agent select, verify and safely
install a complete setup for an AI harness.

A setup covers instructions, skills, MCP, hooks, commands, agents, plugins and
settings. `ai_stp` records provenance, compatibility, exact versions and trust
decisions so that an agent never has to guess at a configuration.

The website owns the account and the public catalog. It displays results. It
does not select a composition, assemble a setup, or write native harness
state. That work belongs to the [CLI](cli/index.md), the agent, and the
harness's own public provider.

## Where to start

- [Quickstart for people](quickstart/human.md): install the CLI, check the
  environment and read the catalog.
- [Quickstart for agents](quickstart/agent.md): start every session from
  `doctor` and `help --agent`.
- [CLI](cli/index.md): the working surface — JSON envelopes, plans, and
  confirmation.
- [Web](web/index.md): account, catalog cards, publications, and reports.
- [Harnesses](harnesses.md): primary support, beta lines, and `undefined`.
- [Concepts](concepts/index.md): harness, setup, provider, assembler, device,
  project, and the three modes.
- [Components](components/index.md): the closed kinds and how they differ.
- [Catalog](catalog/index.md): how to read a public result and how the CLI
  searches it.
- [Trust and safety](trust-and-safety/index.md): why a verified author is not
  the same thing as safe content.
- [Troubleshooting](troubleshooting/index.md): recovering when an install or a
  check does not pass.

## What the MVP supports

Primary support is for **Claude Code**, **Codex**, and **Grok Build**.

Beta lines are **Pi**, **OpenCode**, **Cursor**, and **Antigravity**. Catalog
and compatibility work; the provider path may still ask for extra confirmation.

An unknown harness falls back to limited **`undefined`**. Reading, import and
local checks are allowed. Automatic installation is not considered safe.

The main path looks like this:

```text
CLI → passports → project index → search → setup assembly → checks
→ install plan → backup → apply through the provider → status
```

??? question "How to read this documentation"
    If `ai_stp` is new to you, start with the [human](quickstart/human.md) or
    [agent](quickstart/agent.md) quickstart and the harnesses page. If you
    are already assembling a setup, go straight to
    [components](components/index.md): each page explains what one kind is
    for, where its boundary is, and what it risks. Command flags always come
    from `ai-stp help --agent --json`; this site names commands so a person
    can find the right page.
