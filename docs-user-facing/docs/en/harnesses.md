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

=== "Beta: Pi and OpenCode"

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

## Choosing a target

1. Run `ai-stp doctor --json`.
2. Check which harness was detected.
3. Open the setup or component in the catalog.
4. Compare harness support and the trust line.
5. Read the provider plan before applying.

!!! tip "For the MVP"
    If you are unsure, start with Claude Code or Codex. For beta lines, keep
    the install plan and do not delete the backup until you have checked the
    result.
