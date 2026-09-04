---
title: "command"
description: "Command components: named shortcuts a person or an agent can invoke."
---

# `command`

A `command` is a named way into a repeatable action: a slash command, a
prompt template, or another shortcut the harness actually documents.

A command answers the question: **which checkable operation can be
called by name?**

It does not answer "how should the agent do this class of task?"
([`skill`](skill.md)), "what must run automatically on an event?"
([`hook`](hook.md)), or "which CLI family does `ai-stp` itself expose?"
(those pages live under [`cli/`](../cli/index.md)).

!!! warning "Kind `command` is not the `ai-stp` CLI"

    This page is the **component kind** `command` that goes into a setup.

    The `ai-stp` executable (package `ai-stp-cli`) has its own command
    groups — `component`, `select`, `install`, and the rest. Those are
    documented under [CLI](../cli/index.md). They are not catalog
    components, they are not selected into a setup, and there is no
    `ai-stp component command validate`.

    Codex names this surface **command/prompt**. Discovery still reports
    kind `command`.

    | Object | Where it lives | Lives in a setup? |
    | --- | --- | --- |
    | Kind `command` (this page) | harness slash/prompt surface | yes |
    | `ai-stp …` CLI groups | [CLI map](../cli/commands.md) | no |

## Neighbours

| Kind | The main difference |
| --- | --- |
| `skill` | a skill activates on the meaning of the task; a command is invoked by name |
| `hook` | a hook starts on a lifecycle event; a command starts when called |
| `instruction` | an instruction is already in context; a command is an entry point |
| `plugin` | a plugin may *contain* a `commands/` directory; each file is still kind `command` |
| `agent` | an agent is a role; a command is a shortcut that role may use |
| `mcp` | MCP is a tool protocol; a command is not a server |
| `setting` | a setting holds parameters; a command holds an invocation |

Choose `command` when a person or an agent should start the work by
name. Choose `skill` when the agent should recognise the task without a
slash. Choose `hook` when the work must happen on an event.

## Recommended package structure

`command` is declarative. `--language` is `none`. A command is usually a
single Markdown file. Claude Code authors commands as files in a
directory-shaped layout; adoption accepts that single file without an
extra wrapper manifest.

Portable package (what `discover` / `adopt` transfer from `source/`):

```text
run-tests/
└── run-tests.md                   # {name}.md at the package root
```

When you start from `ai_stp`, scaffold first. The authoring directory is
wider than the published package: `discover` / `adopt` transfer `source/`
when portable and `projections/<harness>/` when a harness was selected,
not the whole tree.

```text
run-tests/                         # component-scaffold/6
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
└── source/
    └── run-tests.md
```

```bash
ai-stp component scaffold plan \
  --type command \
  --language none \
  --harness portable \
  --name run-tests \
  --output ./run-tests \
  --json

ai-stp component scaffold apply \
  --type command \
  --language none \
  --harness portable \
  --name run-tests \
  --output ./run-tests \
  --expected-plan-digest <digest> \
  --json
```

`--language` for a command is `none`. The kind is declarative.

There is no `ai-stp component command validate`. Structural readiness is
`component passport validate`. Kind-specific specification checking
exists only for [`skill`](skill.md).

Give the command a short name, an explicit description, and bounded
arguments. The agent should read available commands from machine help,
not invent them from memory — that rule is for `ai-stp` itself
(`ai-stp help --agent --json`) and is the right habit for harness
commands too.

If a command changes the outside world, it must be legible in the
install plan and must not get around the general rules: digest,
confirmation, backup and rollback.

## Standards and frameworks

There is no independent command specification comparable to the
[Agent Skills Specification](https://agentskills.io/specification). A
skill is the portable workflow; a command is the named entry.

Cite `layout_source` from `ai-stp component discover --json` when
classification is uncertain. Do not guess a neighbour's path.

NVIDIA SkillSpector and Cisco Skill Scanner are skill scanners. They
do not validate commands.

## Native layouts per harness

Discovery only reports layouts that are declared. Exact paths on a
machine come from `ai-stp component discover --json`. Each finding
carries `layout_source`. If classification is uncertain, show that
field; do not guess a neighbour's path.

From the discovery matrix:

| Harness | Global | Project | Notes that are in the discovery contract |
| --- | --- | --- | --- |
| Claude Code | yes | yes | under `commands/`; inside a proven `.claude-plugin/plugin.json` pack, `commands/` members are commands |
| Codex | command/prompt | no | global prompt directory in the bounded matrix |
| Pi | yes | yes | |
| OpenCode | yes | yes | |
| Grok Build | shared command | no | shared command at global scope in the bounded matrix |
| Cursor | via plugin pack | via plugin pack | commands are read inside a proven `.cursor-plugin/plugin.json` pack |
| Antigravity | no | no | not a declared command layout in the bounded matrix |
| `undefined` | portable conventions | portable conventions | not a harness; automatic install is not considered safe |

Inside a proven Claude Code plugin, discovery reads `commands` (each
child is one command). Inside a proven Cursor plugin, the same applies.
The official Cursor schema also names other keys; the walker does not
invent command files from an adjacent directory.

A single file in a directory-shaped layout needs no extra manifest —
that is how Claude Code commands are authored, and adoption accepts
them.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

## Versions are `X.Y`, not SemVer

A published command version is immutable and has the form `X.Y`. There
is no patch number. Changing the Markdown, the name, or the arguments is
a new version. Updating a command inside a setup is a new setup version.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` opens the next major line. A major line is a separate access
boundary.

## What `ai_stp` checks

The catalog percent and the required-versus-optional split are explained
on [Security checks](../security-checks.md). For a command, expect at
least:

- structure, digest, license, tags, source repository;
- bounded unpack and path denylist;
- secret scanning (`secrets_heuristic`, and Gitleaks when enabled);
- prompt-injection and hidden-content rules.

A passed scan reduces known risk. It is not a guarantee that the
shortcut is harmless. Required checks that fail or cannot run block
publication.

Before install, also look at:

| Check | Why it matters |
| --- | --- |
| Name conflicts | two shortcuts with the same name confuse both people and agents |
| Description | the agent must not guess what the command is for |
| What it changes | a command that mutates the outside world must be in the install plan |
| Who is the author | a verified author does not make the shortcut automatically safe |
| Which `X.Y` is pinned | updating a command makes a new version of the setup |
| Trust line | `experimental` needs explicit consent |

`author_verified` and `component_verified` are independent. Neither is a
safety guarantee.

## Related CLI commands

Only commands that exist. Flags always from the CLI pages, and always
`--json`. The executable is `ai-stp` (package `ai-stp-cli`). There is no
`component inspect` and no `setup show`. The only kind-specific validate
is `ai-stp component skill validate`.

**This kind, specifically:** there is no `component command validate`.
Use passport validation.

```bash
ai-stp component passport validate --id <stable_id> --json
```

**Not this kind** — `ai-stp` CLI groups (see [CLI](../cli/index.md)):

```bash
ai-stp help --agent --json
```

**Author, adopt, publish:**

```bash
ai-stp component discover --root . --json
ai-stp component adopt --path <source_path> --json
ai-stp component passport validate --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
ai-stp publication plan --id <stable_id> --version 1.0 --json
ai-stp publication confirm --plan-id <id> --plan-hash <hash> --confirm --json
```

**Find, select, install:**

```bash
ai-stp registry search --kind component --query <name> --json
ai-stp select eligibility --harness <id> --json
ai-stp install plan --json
```

A command can also be an embedded member of a compose manifest. See
[Setups](../setups/index.md).

## How a command moves through `ai_stp`

=== "Author"
    The author publishes the command from a public GitHub source, or
    imports it locally. The version pins an exact commit and subpath.

=== "Catalog"
    The catalog shows the name, the supported harnesses, the
    constraints, the author's trusted status and the component's own
    independent status.

=== "Compiler"
    The compiler checks for name conflicts, harness compatibility, and
    that the file structure suits the provider's projection.

=== "Provider"
    The provider creates the native command wherever that harness
    expects it, only after a plan, a digest and a confirmation.

## Red flags

- Treating an `ai-stp` CLI group as if it were this component kind.
- A skill (`SKILL.md` directory) labelled as a command, or the reverse.
- A `commands/` directory inside `.claude-plugin/` (the manifest
  directory holds `plugin.json` only; `commands/` sits at the plugin
  root).
- Unbounded arguments that make a dangerous call easy.
- Live tokens, private keys, or `.env` bodies in the package.
- `experimental` trust line without `consent allow`.
- Harness not in the component's compatibility list.
- "Latest" or a branch name instead of an exact `X.Y` and commit.
- Treating `author_verified` as `component_verified`.
- A command that changes the outside world but is invisible in the
  install plan.

??? question "Can a command be used without publishing it"
    Yes. Your own, imported or exactly pinned command can be used after
    local checks. It does not thereby become platform-verified, and it
    must be shown as exactly what it is: a local or pinned object
    (`local_owner_or_pinned`).

## Author checklist

1. Scaffold with `--type command --language none` and keep the Markdown
   at the package root (under `source/` in the authoring tree).
2. Give it a short name, a description a person can read, and bounded
   arguments. Put a procedure with assets in a [`skill`](skill.md)
   instead.
3. Declare what the command changes in the passport. No secrets.
4. Run `ai-stp component discover --root . --json` and read
   `layout_source` on the finding.
5. `component adopt --path <exact source_path>`.
6. Pin an exact public GitHub commit and subpath.
7. `component passport validate` → `component version release` to mint
   immutable `X.Y`.
8. Publish through [the publication path](../publishing/index.md).
9. In a setup, pin that `X.Y`. Updating later is a new setup version.

Related: [Authoring](../publishing/authoring.md),
[Components](index.md), [`skill`](skill.md), [`hook`](hook.md),
[CLI map](../cli/commands.md).
