---
title: "Quickstart"
description: "Choose the human first-run path or the AI-agent session path."
---

# Quickstart

Two readers start in different places. The commands are the same CLI; the
ritual is not.

- A **person** installs the binary, creates local identity, and reads the
  catalog. Follow [Quickstart for people](human.md).
- An **AI agent** starts every session from `doctor` and machine help, and
  must not reconstruct flags from memory. Follow
  [Quickstart for agents](agent.md).

The executable is `ai-stp`. The PyPI distribution is `ai-stp-cli`. Copying
`uv tool install ai-stp` installs a package this project does not publish.

Selecting and applying a setup is not this chapter. After the first catalog
read, go to [Select](../cli/select.md) and [Install](../cli/install.md).

## Shared facts

| Fact | Page |
| --- | --- |
| JSON envelopes, mutability, confirmation | [CLI](../cli/index.md) |
| One row per command | [Command map](../cli/commands.md) |
| How to read a catalog card | [Catalog](../catalog/index.md) |
| `author_verified` is not safety | [Trust and safety](../trust-and-safety/index.md) |
| `ai-stp` not on `PATH` | [Troubleshooting](../troubleshooting/index.md) |

If `ai-stp help --agent --json` disagrees with a flag on either quickstart,
the CLI wins.
