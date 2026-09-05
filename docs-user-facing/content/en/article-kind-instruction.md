---
type: article
slug: kind-instruction
locale: en
title: "Standing rules are a component, not an agent role"
description: "An expanded guide to instruction: boundaries, precedence, native files, and safe distribution."
published_at: 2026-09-04
tags: [component, instruction]
draft: false
---

# `instruction`

![Component type: instruction](/content/illustrations/kind-instruction.jpg)

An `instruction` is standing text that shapes how an agent decides: rules,
project memory, working style, the limits of its authority, and harness
notes that are not a workflow, a shortcut, or a package.

An instruction answers the question: **what must the agent keep in mind
while it works?**

It does not answer "how should the agent do this class of task?"
([`skill`](https://ai-stp.aiguild.space/en/docs/components)), "which named shortcut do I type?"
([`command`](https://ai-stp.aiguild.space/en/docs/components)), or "which specialised role should run?"
([`agent`](https://ai-stp.aiguild.space/en/docs/components)).

!!! warning "AGENTS.md is an instruction, not an `agent`"

    A file named `AGENTS.md` is the cross-harness instruction convention.
    Kind `agent` is a role definition. Discovery will not treat `AGENTS.md`
    as a role, and it will not treat a role file as standing rules.

    `CODEX.md` is **not** a documented Codex instruction layout. Discovery
    returns it as `unsupported_manifest` and points at `AGENTS.md`.

    Memory, rules, preferences, and project conventions are *content* of
    `instruction` (or of [`setting`](https://ai-stp.aiguild.space/en/docs/components)). There is no `memory`
    kind.

    | Object | Kind | Lives in a setup? |
    | --- | --- | --- |
    | `AGENTS.md` / `CLAUDE.md` / rules text | `instruction` | yes |
    | A named role under `agents/` | `agent` | yes |
    | CLI Agent Skill (`ai-stp skill …`) | not this kind | no |

## Neighbours

| Kind | The main difference |
| --- | --- |
| `skill` | a skill is a repeatable procedure with supporting files; an instruction is standing context |
| `command` | a command is invoked by name; an instruction is already in the session |
| `agent` | an agent is a role that *uses* instructions; the instruction is the text, not the role |
| `plugin` | a plugin extends the harness; an instruction extends the agent's reading list |
| `mcp` | MCP connects a tool; an instruction may only *say* when that tool should be used |
| `hook` | a hook fires on a lifecycle event; an instruction does not run |
| `setting` | a setting holds parameters; an instruction holds prose |

Choose `instruction` when the agent must follow standing rules without a
procedure attached. Choose `skill` when the work has steps, scripts, or
references. Choose `command` when a person should start the work by name.

## Recommended package structure

`instruction` is declarative. `--language` is `none`. There is no
independent instruction specification comparable to the
[Agent Skills Specification](https://agentskills.io/specification); the
body is Markdown the harness will load as context.

Portable package (what `discover` / `adopt` transfer from `source/`):

```text
project-conventions/
└── AGENTS.md
```

When you start from `ai_stp`, scaffold first. The authoring directory is
wider than the published package: `discover` / `adopt` transfer `source/`
when portable and `projections/<harness>/` when a harness was selected,
not the whole tree.

```text
project-conventions/                 # component-scaffold/3
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
└── source/
    └── AGENTS.md
```

`source/AGENTS.md` is the canon. Claude Code projections use `CLAUDE.md`;
Cursor uses `rules/<name>.mdc`. Do not invent a second wrapper directory.

```bash
ai-stp component scaffold plan \
  --type instruction \
  --language none \
  --harness portable \
  --name project-conventions \
  --output ./project-conventions \
  --json

ai-stp component scaffold apply \
  --type instruction \
  --language none \
  --harness portable \
  --name project-conventions \
  --output ./project-conventions \
  --expected-plan-digest <digest> \
  --json
```

`--language` for an instruction is `none`. The kind is declarative.

Adoption accepts a path discovery already named. A directory must carry a
closed-set manifest (`SKILL.md`, `AGENTS.md`, `plugin.json`,
`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`,
`.cursor-plugin/plugin.json`, `hooks.json`, `package.json`, or
`pyproject.toml`). A single file in a file-shaped layout — including
`AGENTS.md` — is the component; it needs no extra wrapper.

There is no `ai-stp component instruction validate`. Structural readiness
is `component passport validate`. Kind-specific specification checking
exists only for [`skill`](https://ai-stp.aiguild.space/en/docs/components).

## Standards and frameworks

- [AGENTS.md](https://agents.md) — the cross-product instruction file.
  Discovery treats a project-root `AGENTS.md` as an instruction, not as
  kind `agent`.
- Harness pages that declared a layout appear on each finding as
  `layout_source` from `ai-stp component discover --json`. Show that
  field when classification is uncertain; do not guess a neighbour's
  path.
- Contrast with the [Agent Skills Specification](https://agentskills.io/specification)
  when you are tempted to put a workflow into an instruction: a procedure
  with `SKILL.md` is a `skill`.

Do not invent a `memory` kind, a `rules` kind, or extra frontmatter the
harness UI happens to display. Those are content of this kind or of
`setting`.

## Native layouts per harness

Discovery only reports layouts that are declared. Exact paths on a
machine come from `ai-stp component discover --json`. Each finding
carries `layout_source` — the official document that declared the
layout. If classification is uncertain, show that field; do not guess a
neighbour's path.

From the discovery matrix:

| Harness | Global | Project | Notes that are in the discovery contract |
| --- | --- | --- | --- |
| Claude Code | yes | yes | standing text; a directory under `skills/` with a plugin manifest is a **plugin**, not an instruction |
| Codex | yes | yes | `CODEX.md` is `unsupported_manifest`; use `AGENTS.md` |
| Pi | yes | no | global instruction only in the bounded matrix |
| OpenCode | no | no | not a declared instruction layout in the bounded matrix |
| Grok Build | no | no | not a declared instruction layout in the bounded matrix |
| Cursor | yes | yes | inside a proven `.cursor-plugin/plugin.json` pack, each file under `rules/` is an instruction |
| Antigravity | no | no | not a declared instruction layout in the bounded matrix |
| `undefined` | portable conventions | portable conventions | not a harness; automatic install is not considered safe |

Inside a proven Cursor plugin, discovery reads `rules` and classifies
each file as `instruction`. It does not invent instruction files from an
adjacent directory.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

If the same path answers to more than one harness, name `--harness` on
adopt. Use `portable` for the shared cross-product claim.

## Versions are `X.Y`, not SemVer

A published instruction version is immutable and has the form `X.Y`.
There is no patch number. Changing the Markdown is a new version.
Updating an instruction inside a setup is a new setup version.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` opens the next major line. A major line is a separate access
boundary.

## What `ai_stp` checks

The catalog percent and the required-versus-optional split are explained
on [Security checks](https://ai-stp.aiguild.space/en/docs/components). For an instruction, expect
at least:

- structure, digest, license, tags, source repository;
- bounded unpack and path denylist;
- secret scanning (`secrets_heuristic`, and Gitleaks when enabled);
- prompt-injection and hidden-content rules (`pi_content_pack`,
  `content_hidden`).

A passed scan reduces known risk. It is not a guarantee that the text is
harmless. Required checks that fail or cannot run block publication.

Before install, also look at:

| Check | Why it matters |
| --- | --- |
| Diff of the prose | an instruction can quietly widen authority |
| Harness compatibility | Claude-specific text must not land on an incompatible target |
| Scope | global rules apply more widely than a project file |
| Who is the author | a verified author does not make content automatically safe |
| Which `X.Y` is pinned | updating the text makes a new version of the setup |
| Trust line | `experimental` needs explicit consent |

`author_verified` and `component_verified` are independent. Neither is a
safety guarantee.

## Related CLI commands

Only commands that exist. Flags always from the CLI pages, and always
`--json`. The executable is `ai-stp` (package `ai-stp-cli`). There is no
`component inspect` and no `setup show`. The only kind-specific validate
is `ai-stp component skill validate`.

**This kind, specifically:** there is no `component instruction
validate`. Use passport validation.

```bash
ai-stp component passport validate --id <stable_id> --json
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

If discovery reported the path under more than one harness or kind:

```bash
ai-stp component adopt --path <source_path> --harness portable --kind instruction --json
```

**Find, select, install:**

```bash
ai-stp registry search --kind component --query <name> --json
ai-stp select eligibility --harness <id> --json
ai-stp install plan --json
```

An instruction can also be an embedded member of a compose manifest. See
[Setups](https://ai-stp.aiguild.space/en/docs/components).

## How an instruction moves through `ai_stp`

=== "Author"
    The author publishes the instruction from a public GitHub source, or
    imports it locally. The version pins an exact commit and subpath.

=== "Catalog"
    The catalog shows what it is for, the supported harnesses, the
    constraints, the author's trusted status and the component's own
    independent status.

=== "Compiler"
    The compiler checks that the instruction can be built into the chosen
    setup and that its file structure suits the provider's projection.

=== "Provider"
    The provider places the instruction on the harness's native surface
    and updates the related indexes only after a plan, a digest and a
    confirmation.

## Red flags

- Treating `AGENTS.md` as kind `agent`, or a role file as standing rules.
- Shipping `CODEX.md` and expecting discovery to accept it as Codex
  instructions.
- Nesting the Markdown under `payload/` or another wrapper directory.
- Live tokens, private keys, or `.env` bodies in the package.
- Rules that instruct the agent to ignore previous instructions or to
  exfiltrate secrets.
- `experimental` trust line without `consent allow`.
- Harness not in the component's compatibility list.
- "Latest" or a branch name instead of an exact `X.Y` and commit.
- Treating `author_verified` as `component_verified`.
- Inventing a `memory` kind instead of putting memory in this text.
- Copying files into a target instead of going through the provider plan.

??? question "Can an instruction be used without publishing it"
    Yes. Your own, imported or exactly pinned instruction can be used
    after local checks. It does not thereby become platform-verified, and
    it must be shown as exactly what it is: a local or pinned object
    (`local_owner_or_pinned`).

## Author checklist

1. Scaffold with `--type instruction --language none` and keep the
   Markdown at the package root (under `source/` in the authoring tree).
2. Write standing rules only. Move a procedure to a [`skill`](https://ai-stp.aiguild.space/en/docs/components);
   move a named shortcut to a [`command`](https://ai-stp.aiguild.space/en/docs/components).
3. Declare what the text asks of the agent in the passport. No secrets.
4. Run `ai-stp component discover --root . --json` and read
   `layout_source` on the finding.
5. `component adopt --path <exact source_path>` — add `--kind
   instruction` if the path is claimed by more than one kind.
6. Pin an exact public GitHub commit and subpath.
7. `component passport validate` → `component version release` to mint
   immutable `X.Y`.
8. Publish through [the publication path](https://ai-stp.aiguild.space/en/docs/components).
9. In a setup, pin that `X.Y`. Updating later is a new setup version.

Related: [Authoring](https://ai-stp.aiguild.space/en/docs/components),
[Components](https://ai-stp.aiguild.space/en/docs/components), [`agent`](https://ai-stp.aiguild.space/en/docs/components), [`skill`](https://ai-stp.aiguild.space/en/docs/components).
