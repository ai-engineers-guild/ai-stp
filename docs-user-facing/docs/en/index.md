---
title: "ai_stp"
description: "ai_stp user documentation."
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

## Where to start

- [Quickstart](quickstart.md): install the CLI, check the environment and see
  the first commands.
- [Harnesses](harnesses.md): what the MVP supports, what is in beta, and what
  the `undefined` mode means.
- [Concepts](concepts/index.md): harness, setup, component, passport and trust
  line.
- [Components](components/index.md): how `skill`, `mcp`, `hook`, `command`,
  `agent`, `plugin`, `instruction` and `setting` differ.
- [Trust and safety](trust-and-safety/index.md): why a verified author is not
  the same thing as safe content.
- [Troubleshooting](troubleshooting/index.md): recovering when an install or a
  check does not pass.

## What the MVP does

The MVP supports Claude Code, Codex and Grok Build as primary harnesses. Pi and
OpenCode are available as beta lines, and an unknown harness falls back to the
limited `undefined` mode.

The main path looks like this:

```text
CLI → passports → project index → search → setup assembly → checks
→ install plan → backup → apply through the provider → status
```

The web surface shows the public catalog and the account. Assembly, checks and
installation are done by the CLI, the agent and the harness's own provider.

??? question "How to read this documentation"
    If `ai_stp` is new to you, start with the quickstart and the harnesses
    page. If you are already assembling a setup, go straight to components:
    each page explains what one kind is for, where its boundary is, and what it
    risks.
