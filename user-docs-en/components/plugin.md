---
description: "Plugin components: native harness extensions."
---

# `plugin`

A `plugin` is a native extension of a harness. It can add commands, UI,
integrations, MCP configuration, skills or other surfaces, where the particular
harness supports them.

`ai_stp` treats a plugin as a component of its own, because installing one
usually carries more supply-chain and runtime risk than a Markdown instruction.

## Plugin or another component?

| If the extension | Kind |
| --- | --- |
| only gives the agent rules | `instruction` |
| describes a workflow | `skill` |
| connects one MCP server | `mcp` |
| adds a harness package or extension | `plugin` |
| changes parameters only | `setting` |

## What is checked

| Check | Why |
| --- | --- |
| source and version | so a substituted package is not installed |
| supported harness | the plugin format is not universal |
| post-install behaviour | to know what changes after installing |
| dependencies | to judge the supply chain |
| provider plan | to see the exact changes to the target |

=== "Catalog"
    Shows what it is for, the author, the version, compatibility and the trust
    line.

=== "Plan"
    Shows which files, indexes or package surfaces the provider will change.

=== "Rollback"
    Must return the target to its state before the install, as far as that
    harness's provider allows.

!!! danger "A verified author is not a safe plugin"
    A verified author helps you understand provenance. It does not prove the
    plugin's content is safe. Look at the component's own independent checks.
