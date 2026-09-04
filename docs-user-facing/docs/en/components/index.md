---
title: "Components"
description: "What ai_stp components are and how they get into a setup."
---

# Components

Components are the building parts of a setup. Each has a kind, a version,
provenance, compatibility constraints and a passport.

One kind does not stand in for another. An MCP server stays an `mcp`, and the
instructions for using it stay the content of an `instruction` or a `skill`.
Memory, rules, parameters, and auxiliary tools are content of `instruction`,
`skill`, or `setting`. They are not kinds of their own.

`marketplace` is native packaging, not a component kind.

The executable is `ai-stp` (package `ai-stp-cli`). Always pass `--json`.
There is no `component inspect` and no `setup show`. The only kind-specific
validate is `ai-stp component skill validate`.

## Eight chapters

Each kind has its own page. Read the chapter before scaffolding or
adopting that kind. The eight chapters share one formula: the question
the kind answers, what it is not, the neighbours table, the recommended
package, native layouts, the checks that actually run, the CLI path,
then red flags. Compare kinds by that spine; do not learn a new shape
per page.

| Kind | Chapter | The question it answers |
| --- | --- | --- |
| `instruction` | [`instruction`](instruction.md) | what must the agent keep in mind while it works? |
| `skill` | [`skill`](skill.md) | how should the agent do this class of task? |
| `mcp` | [`mcp`](mcp.md) | which external tool interface is connected? |
| `hook` | [`hook`](hook.md) | what must run automatically when this event happens? |
| `command` | [`command`](command.md) | which checkable operation can be called by name? |
| `agent` | [`agent`](agent.md) | which named role should carry this class of work? |
| `plugin` | [`plugin`](plugin.md) | which package extends the harness itself? |
| `setting` | [`setting`](setting.md) | which non-secret parameters should be pinned? |

Name collisions that the chapters spell out:

- kind `skill` versus the CLI Agent Skill (`ai-stp skill install`);
- kind `plugin` versus a marketplace;
- MCP **server** versus plugin `.mcp.json` **client config**;
- `AGENTS.md` (instruction) versus kind `agent`.

Exact native paths come from `ai-stp component discover --json`. Each
finding carries `layout_source`. Do not invent a neighbour's path.

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

The catalog percent and the required-versus-optional split are on
[Security checks](../security-checks.md). `author_verified` and
`component_verified` are independent axes. Neither is a safety guarantee.

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

Typical local path:

```bash
ai-stp component discover --root . --json
ai-stp component adopt --path <source_path> --json
ai-stp component passport validate --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
ai-stp publication plan --id <stable_id> --version 1.0 --json
ai-stp publication confirm --plan-id <id> --plan-hash <hash> --confirm --json
```

Shared `.agents/skills` are returned once, with `harness_id=null`. An MCP
server package likewise belongs to no single harness. `undefined` owns only
portable conventions; automatic install is not considered safe.

## Versions

A published component version is immutable and has the form `X.Y`. There is
no patch number. If the content changes, there is a new version. Updating a
component inside a setup is a new setup version. `--major` on
`component version release` opens the next major line, which is a separate
access boundary.

## Compatibility

A component can fit one harness and be inadmissible for another. Mechanical
compatibility constraints apply before any reasoning by the agent.

Discovery coverage differs by harness and kind. The bounded layout matrix
and `layout_source` live in each kind chapter and in
`ai-stp toolchain harness-capabilities --json`.

| Harness | Declared kinds (bounded matrix) |
| --- | --- |
| Claude Code | global and project: instruction, skill, agent, command, setting, MCP, plugin |
| Codex | global: instruction, command/prompt, setting, shared skill; project: instruction, setting, agent, hook, shared skill |
| Pi | global: instruction, skill, plugin, command, setting; project: skill, plugin, command, setting |
| OpenCode | global and project: skill, agent, command, plugin, setting |
| Grok Build | global: skill, plugin, hook, setting, shared command; project: skill, plugin, hook, setting |
| Cursor | global: instruction, setting, plugin; project: instruction, plugin |
| Antigravity | global: setting, plugin, skill, agent, hook, MCP; project: plugin, skill, agent, hook, MCP |
| `undefined` | portable conventions only; automatic install is not considered safe |

Plugin packs, when proven by an exact manifest, can carry nested members
of other kinds. Those members keep their own kinds. Details are on
[`plugin`](plugin.md), [`mcp`](mcp.md), and [`hook`](hook.md).

More on the statuses: [supported harnesses](../harnesses.md).
How to prepare a tree: [Authoring](../publishing/authoring.md).
Trust lines: [Trust and safety](../trust-and-safety/index.md).
Security scan inventory: [Security checks](../security-checks.md).
CLI discovery: [Discover and adopt](../cli/component-discover.md).

## Related pages

- [Setups](../setups/index.md) — exact pins of these kinds.
- [Catalog](../catalog/index.md) — how a card names a kind.
- [Quickstart for people](../quickstart/human.md) — first catalog read.
- [Component commands](../cli/component.md) — discover → passport → publish.
