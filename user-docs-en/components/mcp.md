---
description: "MCP components: connecting tools and services to an agent."
---

# `mcp`

An `mcp` describes an MCP server: its source, how it starts, its compatibility
with a harness, the permissions it expects, and the limits on its use. Through
MCP an agent gets structured access to a tool surface: files, a browser, a SaaS
API, databases or local helpers.

`ai_stp` holds the configuration and the checks. Secrets, tokens and passwords
do not go into a passport.

## When you need an MCP

| Task | Does it need `mcp`? | Note |
| --- | --- | --- |
| The agent must read GitHub issues | yes | MCP defines the connection and the tool surface |
| The agent must know the code review rules | no | that is an `instruction` or a `skill` |
| The agent must call a local scanner | possibly | if the scanner is offered as an MCP server |
| An endpoint and access mode must be recorded | yes | but without the token value |
| A command must run from a shortcut | no | that is a `command` |

## How `ai_stp` reduces the risk

| Risk | The mechanism |
| --- | --- |
| Secrets in the config | the passport holds no secret values |
| Unexpected permissions | required permissions and warnings are shown |
| A substituted source | the version pins the source, the commit and path, or the package |
| The wrong harness | compatibility is checked before the provider plan |
| An unsafe install | unknown objects need explicit consent |

!!! warning "MCP widens what an agent can reach"
    Even a good MCP server can give an agent access to data or operations it
    did not have before. Install it as a tool with permissions, not as "one
    more Markdown file".

## What the user sees

=== "In the catalog"
    What the MCP is for, the author, the trust line, the supported harnesses
    and the required permissions.

=== "In the install plan"
    Which entries the provider will add or change, which secrets must be
    supplied through the environment or the system store, and how to roll back.

=== "After applying"
    `status` must show the active MCP, the source of the version, and the
    result of the provider's check.
