---
title: "Supported harnesses"
description: "Which AI harnesses ai_stp supports and what a support level means."
---

# Supported harnesses

A harness is the CLI environment a coding agent runs in. `ai_stp` does not
replace the harness and does not call models: it helps assemble a checkable
setup for one target, and only that harness's provider writes the final state.

## MVP status

| Harness | MVP status | What is available | What to remember |
| --- | --- | --- | --- |
| Claude Code | primary support | passports, compatibility, setup assembly, provider plan | the production path is designed for it first |
| Codex | primary support | passports, compatibility, setup assembly, provider plan | the second primary MVP target |
| Grok Build | primary support | passports, compatibility, setup assembly, provider plan | the third primary MVP target |
| Pi | beta | catalog and compatibility, limited provider path | behaviour may still be refined as integration proceeds |
| OpenCode | beta | catalog and compatibility, adapter/projection checks | the format is open, but not all of the UX is settled |
| Cursor | beta | catalog and compatibility, native plugin pack and cli-config | a plugin pack is recognised by its `.cursor-plugin` manifest |
| Antigravity | beta | catalog and compatibility, provider plan | its configuration lives inside `~/.gemini` rather than a home of its own |
| `undefined` | limited mode | reading, import, local checks | automatic installation is not considered safe |

## What "supported" means

Support in `ai_stp` is made of levels. A harness can pass one level and not yet
be ready for the next.

| Level | What is checked | Why it matters to you |
| --- | --- | --- |
| Detection | the CLI knows which target it is looking at | so a setup is not applied to the wrong place |
| Compatibility | components declare which harness they support | so the obviously unsuitable is filtered out |
| Projection | a setup can be turned into a native structure | so files and settings land in the right format |
| Provider plan | the provider builds a plan to change the target | so you see the diff before anything is applied |
| Apply | the provider applies the change and records it | so there is a rollback and a checkable result |

=== "Primary: Claude Code, Codex, Grok Build"

    For these the MVP is meant to give the shortest path: find a setup, check
    compatibility, see the plan, confirm, and apply through the provider.

=== "Beta: Pi, OpenCode, Cursor, Antigravity"

    Beta means `ai_stp` already tells the harness apart and can work with its
    objects, but part of the provider path, the UX or the checks may be
    stricter and may ask for manual confirmation.

=== "`undefined`"

    This mode exists so an object is not lost when the harness is unknown. It
    is fine for reading, import and local analysis, but not for confident
    automatic installation.

??? question "Why a setup belongs to one harness"
    Because the same words mean different files, permissions and events in
    different CLIs. A `skill` for Codex and a `skill` for Claude Code may mean
    something similar and still have different native surfaces. So a setup is
    created for one harness, and moving it means an explicit new version or an
    adaptation.

## What lands on disk for the three primary harnesses

`ai_stp` does not copy files into a target. The assembler builds a native
package; the provider writes it. Exact paths for a machine come from
`ai-stp component discover --json` (`source_path`, `layout_source`) and from
the provider plan. The kinds that discovery will look for are:

| Kind | Claude Code | Codex | Grok Build |
| --- | --- | --- | --- |
| `instruction` | global and project | global and project | not a declared native instruction layout |
| `skill` | global and project | shared skill (including `.agents/skills`) | global and project |
| `mcp` | global and project | names inside the settings file (`config.toml`) when the `mcp_servers` key is present | names inside `config.toml` when the key is present |
| `hook` | not a top-level declared layout in the discovery matrix | project: `.codex/hooks.json`, or `hooks/hooks.json` inside a proven plugin | global and project |
| `command` | global and project | global command/prompt | shared command, global |
| `agent` | global and project | project: `.codex/agents` | not a declared native agent layout |
| `plugin` | global and project; a pack is a plugin only through `.claude-plugin/plugin.json` | plugin root, skill, and hooks-directory; pack through `.codex-plugin/plugin.json` | global and project; `plugins/marketplaces` is not a plugin |
| `setting` | global and project | global and project (`config.toml`) | global and project (`config.toml`) |

A directory under `plugins/` without a manifest from a supported harness is
not a plugin. `CODEX.md` is not an official Codex instruction layout;
discovery reports it as `unsupported_manifest` and points at `AGENTS.md`.

Shared `.agents/skills` belong to no single harness and come back with
`harness_id=null`.

After apply, confirm with:

```bash
ai-stp target status --project <id> --harness <id> --json
ai-stp target diff --project <id> --harness <id> --json
```

## Official harness documentation

These are the vendors' own docs, not `ai_stp` pages. Layouts `ai_stp` will
act on are still only those `component discover` returns with a
`layout_source`.

| Harness | Official documentation |
| --- | --- |
| Claude Code | [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code) |
| Codex | [ChatGPT / Codex docs](https://learn.chatgpt.com/docs) (native instruction file: `AGENTS.md`) |
| Grok Build | [xAI Build docs](https://docs.x.ai/build) |
| Pi | [Pi docs](https://pi.dev/docs/latest) |
| OpenCode | [OpenCode docs](https://opencode.ai/docs) |
| Cursor | [Cursor docs](https://docs.cursor.com) |
| Antigravity | [Antigravity docs](https://antigravity.google/docs) |

If a classification is uncertain, show the `layout_source` field from
`component discover`. Do not invent a path because a neighbouring harness
uses one.

## Choosing a target

1. Run `ai-stp doctor --json`.
2. Check which harness was detected: `ai-stp toolchain harnesses --json`.
3. Open the setup or component in the catalog.
4. Compare harness support and the trust line.
5. Read the provider plan before applying.

```bash
ai-stp doctor --json
ai-stp toolchain harnesses --json
ai-stp toolchain harness-capabilities --json
```

!!! tip "For the MVP"
    If you are unsure, start with Claude Code, Codex, or Grok Build. For beta
    lines, keep the install plan and do not delete the backup until you have
    checked the result.

## Related pages

- [Concepts](concepts/index.md) — what a harness is, versus a setup.
- [Quickstart for people](quickstart/human.md) — first run when the program
  is missing.
- [Harness program](cli/harness.md) — install the binary, not the setup.
- [Provider](cli/provider.md) — the only writer of native state.
- [Components](components/index.md) — which kinds each harness accepts.
- [Setups](setups/index.md) — a setup belongs to one harness from creation.
- [Troubleshooting](troubleshooting/index.md) — `undefined` is not auto-install.
