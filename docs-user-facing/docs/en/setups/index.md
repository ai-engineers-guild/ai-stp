---
title: "Setups"
description: "How ai_stp assembles a complete setup from exact component versions."
---

# Setups

A setup is the complete configuration of one harness. It contains exact
component versions, native projections and compatibility constraints. Saved
versions are immutable; changing content creates new versioned facts.

```bash
ai-stp help --path setup --json
ai-stp help --path configuration --json
```

The assembler checks the graph and prepares native packages. Installation
components from the existing setup-system repositories are integrated into
ai-stp; only the selected provider writes final harness state. All requested
scope roots are prepared before publication. Interrupted writes resume from
durable journals and exact receipts. No backup or rollback system is introduced.

The harness executable remains managed by its user. An active agent cannot
half-update its running configuration; use the staged handoff and restart.
