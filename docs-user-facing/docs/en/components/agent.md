---
title: "agent"
description: "Agent components: named roles and specialised subagents inside a setup."
---

# `agent`

An `agent` describes a specialised role inside a harness: its area of
responsibility, its inputs, its limits, the tools it may use, and the
result expected of it.

An agent answers the question: **which named role should carry this
class of work?**

It does not answer "how should that role do the work?" ([`skill`](skill.md)),
"what standing rules apply to everyone?" ([`instruction`](instruction.md)),
or "which package extends the harness?" ([`plugin`](plugin.md)).

An agent component is not a setup of its own. It belongs to one
harness's setup and inherits its boundaries.

!!! warning "Kind `agent` is not AGENTS.md, and not the CLI Agent Skill"

    A file named `AGENTS.md` is the cross-harness **instruction**
    convention. Kind `agent` is a role definition, usually a file under
    an `agents/` directory.

    The CLI also ships one canonical Agent Skill that teaches an agent
    how to drive `ai-stp` itself. That object is installed with
    [`ai-stp skill install`](../cli/skill.md). It is **not** a catalog
    component and it is **not** this kind.

    | Object | Kind / command family | Lives in a setup? |
    | --- | --- | --- |
    | Role file under `agents/` | kind `agent` (this page) | yes |
    | `AGENTS.md` | [`instruction`](instruction.md) | yes |
    | CLI Agent Skill | `ai-stp skill install` / `status` / `remove` | no |

## Neighbours

| Kind | The main difference |
| --- | --- |
| `skill` | a skill is the procedure; an agent is the role that can use several skills |
| `instruction` | an instruction is standing text for the session; an agent is a named role |
| `command` | a command is a shortcut; an agent is who (or what role) runs |
| `plugin` | a plugin may *contain* an `agents/` directory; each file is still kind `agent` |
| `mcp` | MCP is a tool interface the role may be allowed to call |
| `hook` | a hook fires on an event; an agent waits to be delegated to |
| `setting` | a setting holds parameters; an agent holds a role description |

Choose `agent` when you need a bounded role with a checkable result.
Choose `skill` when you need the procedure that role will follow.
Choose `instruction` when the text applies without a role name.

## Recommended package structure

`agent` is declarative. `--language` is `none`. A role is usually a
single Markdown file. Claude Code authors agents as files in a
directory-shaped layout; adoption accepts that single file without an
extra wrapper manifest.

Portable package (what `discover` / `adopt` transfer from `source/`):

```text
reviewer/
└── reviewer.md                    # {name}.md at the package root
```

When you start from `ai_stp`, scaffold first. The authoring directory is
wider than the published package: `discover` / `adopt` transfer `source/`
when portable and `projections/<harness>/` when a harness was selected,
not the whole tree. Codex agents are TOML under `agents/`.

```text
reviewer/                          # component-scaffold/3
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
└── source/
    └── reviewer.md
```

```bash
ai-stp component scaffold plan \
  --type agent \
  --language none \
  --harness portable \
  --name reviewer \
  --output ./reviewer \
  --json

ai-stp component scaffold apply \
  --type agent \
  --language none \
  --harness portable \
  --name reviewer \
  --output ./reviewer \
  --expected-plan-digest <digest> \
  --json
```

`--language` for an agent is `none`. The kind is declarative.

Describe the purpose of the role, the tools it may use, what a finished
result looks like, and when to call it. Do not describe a global
replacement for every instruction, secrets, or permission to change the
outside world unconfirmed.

| Describe | Do not describe |
| --- | --- |
| the purpose of the role | a global replacement for every instruction |
| the tools it may use | secrets or personal tokens |
| what a finished result looks like | an uncontrolled background daemon |
| when to call the role | permission to change the outside world unconfirmed |

There is no `ai-stp component agent validate`. Structural readiness is
`component passport validate`. Kind-specific specification checking
exists only for [`skill`](skill.md).

## Standards and frameworks

There is no independent agent-role specification comparable to the
[Agent Skills Specification](https://agentskills.io/specification). A
skill is the portable workflow; an agent is the role.

Cite `layout_source` from `ai-stp component discover --json` when
classification is uncertain. Codex custom agents are documented only
from `.codex/agents` — do not invent a second directory.

NVIDIA SkillSpector and Cisco Skill Scanner are skill scanners. They
are not this kind's validator.

## Native layouts per harness

Discovery only reports layouts that are declared. Exact paths on a
machine come from `ai-stp component discover --json`. Each finding
carries `layout_source`. If classification is uncertain, show that
field; do not guess a neighbour's path.

From the discovery matrix:

| Harness | Global | Project | Notes that are in the discovery contract |
| --- | --- | --- | --- |
| Claude Code | yes | yes | under `agents/`; inside a proven `.claude-plugin/plugin.json` pack, `agents/` members are agents |
| Codex | no | yes | custom agents only from `.codex/agents`; a proven `.codex-plugin/plugin.json` pack does not add an agents subtree in the contract |
| Pi | no | no | not a declared agent layout |
| OpenCode | yes | yes | |
| Grok Build | no | no | not a declared agent layout |
| Cursor | via plugin pack | via plugin pack | agents are read inside a proven `.cursor-plugin/plugin.json` pack |
| Antigravity | yes | yes | |
| `undefined` | portable conventions | portable conventions | not a harness; automatic install is not considered safe |

Inside a proven Claude Code plugin, discovery reads `agents` (each
child is one agent). Inside a proven Cursor plugin, the same applies.
The walker does not invent agent files from an adjacent directory.

A single file in a directory-shaped layout needs no extra manifest —
that is how Claude Code agents are authored, and adoption accepts them.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

## Versions are `X.Y`, not SemVer

A published agent version is immutable and has the form `X.Y`. There is
no patch number. Changing the role text, its tools, or its limits is a
new version. Updating an agent inside a setup is a new setup version.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` opens the next major line. A major line is a separate access
boundary.

## What `ai_stp` checks

The catalog percent and the required-versus-optional split are explained
on [Security checks](../security-checks.md). For an agent, expect at
least:

- structure, digest, license, tags, source repository;
- bounded unpack and path denylist;
- secret scanning (`secrets_heuristic`, and Gitleaks when enabled);
- prompt-injection and hidden-content rules;
- language SAST and SCA when scripts and lockfiles are present.

A passed scan reduces known risk. It is not a guarantee that the role is
harmless. Required checks that fail or cannot run block publication.

Before install, also look at:

| Check | Why it matters |
| --- | --- |
| Scope of the role | a vague role becomes "do everything" |
| Tools it may use | a role that inherits every MCP server is not bounded |
| What "done" looks like | without a checkable result the role cannot be reviewed |
| Who is the author | a verified author does not make the role automatically safe |
| Which `X.Y` is pinned | updating an agent makes a new version of the setup |
| Trust line | `experimental` needs explicit consent |

`author_verified` and `component_verified` are independent. Neither is a
safety guarantee.

## Related CLI commands

Only commands that exist. Flags always from the CLI pages, and always
`--json`. The executable is `ai-stp` (package `ai-stp-cli`). There is no
`component inspect` and no `setup show`. The only kind-specific validate
is `ai-stp component skill validate`.

**This kind, specifically:** there is no `component agent validate`. Use
passport validation.

```bash
ai-stp component passport validate --id <stable_id> --json
```

**Not this kind** — CLI Agent Skill (see [Agent Skill CLI](../cli/skill.md)):

```bash
ai-stp skill status --json
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

An agent can also be an embedded member of a compose manifest. See
[Setups](../setups/index.md).

## How an agent moves through `ai_stp`

=== "Author"
    The author publishes the role from a public GitHub source, or
    imports it locally. The version pins an exact commit and subpath.

=== "Catalog"
    The catalog shows the role, the supported harnesses, the
    constraints, the author's trusted status and the component's own
    independent status.

=== "Compiler"
    The compiler checks whether the harness supports that agent surface
    and that the file structure suits the provider's projection.

=== "Provider"
    The provider creates the native description of the role only after a
    plan, a digest and a confirmation. Status shows which roles are
    active and where they came from.

## Red flags

- Treating `AGENTS.md` as kind `agent`.
- Treating `ai-stp skill install` as if it published this component.
- A role with no limits, no expected result, and every tool enabled.
- Codex agents from anywhere except `.codex/agents`.
- Live tokens, private keys, or `.env` bodies in the package.
- Instructions to ignore previous instructions or to widen permissions
  at runtime.
- `experimental` trust line without `consent allow`.
- Harness not in the component's compatibility list.
- "Latest" or a branch name instead of an exact `X.Y` and commit.
- Treating `author_verified` as `component_verified`.
- A subagent that is allowed to change the outside world without a
  confirmation path.

??? question "Can an agent be used without publishing it"
    Yes. Your own, imported or exactly pinned agent can be used after
    local checks. It does not thereby become platform-verified, and it
    must be shown as exactly what it is: a local or pinned object
    (`local_owner_or_pinned`).

## Author checklist

1. Scaffold with `--type agent --language none` and keep the Markdown at
   the package root (under `source/` in the authoring tree).
2. Name the role, its limits, its tools, and what "done" looks like.
   Put standing rules in [`instruction`](instruction.md) and procedures
   in [`skill`](skill.md).
3. Declare authorization needs in the passport. No secrets.
4. Run `ai-stp component discover --root . --json` and read
   `layout_source` on the finding.
5. `component adopt --path <exact source_path>` — add `--kind agent` if
   the path is claimed by more than one kind.
6. Pin an exact public GitHub commit and subpath.
7. `component passport validate` → `component version release` to mint
   immutable `X.Y`.
8. Publish through [the publication path](../publishing/index.md).
9. In a setup, pin that `X.Y`. Updating later is a new setup version.

Related: [Authoring](../publishing/authoring.md),
[Components](index.md), [`instruction`](instruction.md),
[`skill`](skill.md), [CLI Agent Skill](../cli/skill.md).
