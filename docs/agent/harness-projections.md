---
description: "Differences among native Agent Skill projections for seven harnesses."
last_verified: "2026-08-25"
---

# Harness Projections

| Harness | Projection |
|---|---|
| Claude Code | Plugin/Skill and an explicit import through `CLAUDE.md` in the control layer |
| Codex | Plugin/Skill and a compatible `AGENTS.md` instruction |
| Pi | Package, resources, Skill, and local target settings |
| OpenCode | Native Skill, plugin, agent, and command |
| Grok Build | Native marketplace, plugin, and Skill |
| Cursor | Plugin with a `.cursor-plugin/plugin.json` manifest |
| Antigravity | Skill and agent in the shared Gemini home, plus a plugin in `antigravity-cli` |

The native surface in this table is a delivery form, not a component type: the catalog taxonomy expresses it through `projection_kind` under `ADR-0015`.

The single canonical procedure is not copied manually. A projection preserves its semantics or reports a loss. Runtime capability is confirmed separately for the exact harness version.
