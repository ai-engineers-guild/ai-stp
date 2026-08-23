---
description: "What ai_stp components are and how they get into a setup."
---

# Components

Components are the building parts of a setup. Each has a kind, a version,
provenance, compatibility constraints and a passport.

One kind does not stand in for another. An MCP server stays an `mcp`, and the
instructions for using it stay the content of an `instruction` or a `skill`.

## Choosing quickly

| If you need to | Kind | Why |
| --- | --- | --- |
| Add rules, memory or a working style | [`instruction`](instruction.md) | it is textual policy for the agent or the harness |
| Describe a repeatable agent workflow | [`skill`](skill.md) | a skill holds the procedure, its material and its helper scripts |
| Connect an external tool to the agent | [`mcp`](mcp.md) | MCP gives the agent a managed interface to a service or a local tool |
| Act on a harness event | [`hook`](hook.md) | a hook is bound to the lifecycle and needs care |
| Give a person or an agent a named command | [`command`](command.md) | a command makes a repeatable entry point clear and checkable |
| Add a role or a specialised subagent | [`agent`](agent.md) | an agent describes an area of responsibility and its limits |
| Extend the harness itself with a package | [`plugin`](plugin.md) | a plugin installs a native harness extension |
| Pin parameters and modes | [`setting`](setting.md) | a setting holds configuration, without secrets and without behaviour |

## The component matrix

| Kind | What it holds | What `ai_stp` checks | The typical risk |
| --- | --- | --- | --- |
| `instruction` | Markdown, rules, memory, constraints | provenance, version, compatibility, scope | rules that are too broad or contradict each other |
| `skill` | `SKILL.md`, assets, scripts, references | structure, compatibility, executable helpers | hidden side effects in scripts |
| `mcp` | the MCP server description and how it starts | source, permissions, no secrets in the passport | external access to data or tools |
| `hook` | the event, the action, the conditions | the event, the target, recovery, confirmation | state changed automatically |
| `command` | a slash or CLI command and its arguments | the name, the scope, the help, command conflicts | an ambiguous or dangerous shortcut |
| `agent` | the role, its instructions, its limits | the role's boundaries, compatibility, permissions | a subagent with authority that is too wide |
| `plugin` | a native harness extension | the package, the version, the source, the install route | supply chain and post-install behaviour |
| `setting` | parameters, modes, preferences | allowed values, and that there are no secrets | leaked private data, or configuration drift |

## How a component gets into a setup

=== "1. Passport"

    A component is described by a passport: kind, version, source,
    compatibility, constraints and check results. The passport is what the CLI,
    the catalog and the agent can all read.

=== "2. Candidate"

    `ai_stp` draws candidates from the public catalog, the local registry, or
    the user's exactly pinned objects. The trust line decides whether an object
    may be shown and installed automatically.

=== "3. Setup graph"

    The setup compiler builds the component graph and checks that versions, the
    harness, dependencies and constraints are consistent with one another.

=== "4. Provider"

    Only the harness's public provider writes the target's final state. Before
    anything changes there is a plan, a digest and a backup.

??? warning "Why files cannot simply be copied into a target"
    Harnesses differ in formats, directories, safety rules and lifecycle.
    Copying directly breaks provenance and rollback. So `ai_stp` builds a
    checkable plan first, and only then hands the applying to the provider.

## Versions

A published component version is immutable and has the form `X.Y`. If the
content changes, there is a new version.

## Compatibility

A component can fit one harness and be inadmissible for another. Mechanical
compatibility constraints apply before any reasoning by the agent.

More on the statuses: [supported harnesses](../harnesses.md).
