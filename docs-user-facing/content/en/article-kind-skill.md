---
type: article
slug: kind-skill
locale: en
title: "A skill is a workflow package, not a prompt in a folder"
description: "An expanded guide to skill: triggers, procedures, progressive disclosure, and the supply-chain surface."
published_at: 2026-09-04
tags: [component, skill]
draft: false
---

# `skill`

![Component type: skill](/content/illustrations/kind-skill.jpg)

A `skill` is a portable agent workflow. It usually holds a `SKILL.md`,
instructions, references, assets and sometimes scripts that help an agent
carry out a specialised task without guessing at the process.

A skill answers the question: **how should the agent do this class of
task?**

It does not answer "which named shortcut do I type?" (`command`), "which
external tool is connected?" (`mcp`), or "which package extends the
harness?" (`plugin`).

!!! warning "Two different objects named skill"

    This page is the **component kind** `skill` that goes into a setup.

    The CLI also ships one canonical Agent Skill that teaches an agent how to
    drive `ai-stp` itself. That object is installed with
    [`ai-stp skill install`](https://ai-stp.aiguild.space/en/docs/components), inspected with
    `ai-stp skill status`, and removed with `ai-stp skill remove`. It is
    **not** a catalog component, it is **not** selected into a setup, and
    `ai-stp component skill validate` is **not** that installer.

    | Object | Command family | Lives in a setup? |
    | --- | --- | --- |
    | Kind `skill` (this page) | `component …`, `select`, `install` | yes |
    | CLI Agent Skill | `ai-stp skill install` / `status` / `remove` | no |

## Neighbours

| Kind | The main difference |
| --- | --- |
| `instruction` | gives general rules and context, and need not describe a workflow |
| `command` | runs as a named shortcut, while a skill activates on the meaning of the task |
| `plugin` | extends the harness itself, while a skill extends the agent's working behaviour |
| `mcp` | gives a tool interface, while a skill explains when and how to use it |
| `hook` | fires on a lifecycle event, while a skill waits to be selected for a task |
| `agent` | names a role that can use several skills; a skill is the procedure, not the role |
| `setting` | holds parameters, not a workflow |

Choose `skill` when the agent must follow a repeatable procedure with
supporting files. Choose `instruction` when you only need standing rules.
Choose `command` when a person or an agent should invoke the work by name.

## Recommended package structure

Of the eight kinds, `skill` alone has a specification that exists
independently of this repository: the Agent Skills Specification. `SKILL.md`
must sit at the **package root**. A `payload/SKILL.md` wrapper is
nonconforming for any reader that implements the standard rather than a
local layout.

```text
playwright-checks/
├── SKILL.md              required: YAML frontmatter and instructions
├── scripts/              optional, by convention
├── references/           optional, by convention
├── assets/               optional, by convention
├── evals/                permitted extra; listed separately in the report
└── tests/                permitted extra; not a rejection
```

The directory name must match the `name` field in frontmatter.

When you start from `ai_stp`, scaffold first. The authoring directory is
wider than the published package: `discover` / `adopt` transfer `source/`
when portable and `projections/<harness>/` when a harness was selected,
not the whole tree.

```text
playwright-checks/                 # component-scaffold/3
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
└── source/
    └── SKILL.md
```

```bash
ai-stp component scaffold plan \
  --type skill \
  --language none \
  --harness portable \
  --name playwright-checks \
  --output ./playwright-checks \
  --json

ai-stp component scaffold apply \
  --type skill \
  --language none \
  --harness portable \
  --name playwright-checks \
  --output ./playwright-checks \
  --expected-plan-digest <digest> \
  --json
```

`--language` for a skill is `none`. The kind is declarative.

### Frontmatter the validator will accept

| Field | Required | Constraint |
| --- | --- | --- |
| `name` | yes | 1–64 characters; lowercase letters, digits, and hyphens; neither starts nor ends with a hyphen; no double hyphens; matches the directory name |
| `description` | yes | 1–1024 characters, nonempty |
| `license` | no | the standard sets no extra limit |
| `compatibility` | no | 1–500 characters |
| `metadata` | no | mapping of strings to strings |
| `allowed-tools` | no | space-delimited string; experimental |

A top-level key not defined by the standard is reported as `SK033`.
Client-specific properties belong under `metadata`. The body after
frontmatter is not format-checked: the specification says there are no
format constraints.

Validate the installed package shape, not the authoring tree:

```bash
ai-stp component skill validate --path ./playwright-checks/native --json
```

The command is read-only. It names every deviation with a `SKxxx` code. It
does not adopt, publish, or write a target.

## Standards and frameworks

- [Agent Skills Specification](https://agentskills.io/specification) — the
  independent standard. `ai-stp component skill validate` implements that
  boundary, not a house style.
- Safety scanners used when available during publication:
  [NVIDIA SkillSpector](https://github.com/NVIDIA/SkillSpector) and
  [Cisco Skill Scanner](https://github.com/cisco-ai-defense/skill-scanner).
  An unavailable engine never becomes a pass. See
  [Security checks](https://ai-stp.aiguild.space/en/docs/components).

Do not invent extra frontmatter fields because a harness UI shows them.
Put harness-specific notes under `metadata`.

## Native layouts per harness

Discovery only reports layouts that are declared. Exact paths on a machine
come from `ai-stp component discover --json`. Each finding carries
`layout_source` — the official document that declared the layout. If
classification is uncertain, show that field; do not guess a neighbour's
path.

From the discovery matrix:

| Harness | Global | Project | Notes that are in the discovery contract |
| --- | --- | --- | --- |
| Claude Code | yes | yes | under `skills/`, a directory with `SKILL.md` is a skill; a directory with `.claude-plugin/plugin.json` or `plugin.json` is a **plugin** |
| Codex | shared skill | shared skill | shared `.agents/skills` belong to no harness (`harness_id=null`) |
| Pi | yes | yes | |
| OpenCode | yes | yes | |
| Grok Build | yes | yes | |
| Cursor | via plugin pack | via plugin pack | skills are read inside a proven `.cursor-plugin/plugin.json` pack |
| Antigravity | yes | yes | |
| `undefined` | portable conventions | portable conventions | not a harness; automatic install is not considered safe |

Shared `.agents/skills` are returned once, not duplicated under every
compatible harness.

A Nori `nori.json` or an `.agents/.skill-lock.json` (version 3) may refine
an already discovered path. They do not invent a skill from a missing
directory, and they do not make an external manifest a source of confirmed
passport facts.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

## Versions are `X.Y`, not SemVer

A published skill version is immutable and has the form `X.Y`. There is no
patch number. Changing `SKILL.md`, a script, or an asset is a new version.
Updating a skill inside a setup is a new setup version.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` opens the next major line. A major line is a separate access
boundary.

## What `ai_stp` checks

The catalog percent and the required-versus-optional split are explained on
[Security checks](https://ai-stp.aiguild.space/en/docs/components). For a skill, expect at least:

- structure, digest, license, tags, source repository;
- bounded unpack and path denylist;
- secret scanning (`secrets_heuristic`, and Gitleaks when enabled);
- prompt-injection and hidden-content rules;
- `skill_static_gate` (owned rules plus SkillSpector and Skill Scanner when
  available);
- language SAST and SCA when scripts and lockfiles are present.

A passed scan reduces known risk. It is not a guarantee that the workflow
is harmless. Required checks that fail or cannot run block publication.

Before install, also look at:

| Check | Why it matters |
| --- | --- |
| Are there scripts | scripts can act outside the Markdown |
| Are there references or assets | the agent needs the whole set, not only `SKILL.md` |
| Is the harness compatible | the same skill name does not guarantee the same format |
| Who is the author | a verified author does not make content automatically safe |
| Which `X.Y` is pinned | updating a skill makes a new version of the setup |
| Trust line | `experimental` needs explicit consent |

## Related CLI commands

Only commands that exist. Flags always from `ai-stp help --agent --json`.

**This kind, specifically:**

```bash
ai-stp component skill validate --path <directory> --json
```

**Not this kind** — CLI Agent Skill (see [Agent Skill CLI](https://ai-stp.aiguild.space/en/docs/components)):

```bash
ai-stp skill status --json
ai-stp skill install --target <dir> --json
ai-stp skill remove --target <dir> --json
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
ai-stp select eligibility --json
ai-stp install plan --json
```

A skill can also be an embedded member of a compose manifest. See
[Setups](https://ai-stp.aiguild.space/en/docs/components).

## How a skill moves through `ai_stp`

=== "Author"
    The author publishes the skill from a public GitHub source, or imports it
    locally. The version pins an exact commit and subpath.

=== "Catalog"
    The catalog shows what it is for, the supported harnesses, the constraints,
    the author's trusted status and the component's own independent status.

=== "Compiler"
    The compiler checks that the skill can be built into the chosen setup and
    that its file structure suits the provider's projection.

=== "Provider"
    The provider places the skill in the harness's native directory and updates
    the related indexes only after a plan, a digest and a confirmation.

## Red flags

- `SKILL.md` is nested under `payload/` or another wrapper directory.
- `name` in frontmatter does not match the directory name (`SK013`).
- A top-level field the specification does not define (`SK033`), instead of
  `metadata`.
- Scripts that download and pipe into a shell, or that instruct the agent to
  ignore previous instructions.
- Live tokens, private keys, or `.env` bodies in the package.
- A directory under `skills/` that is actually a plugin (it has
  `.claude-plugin/plugin.json` / `.codex-plugin/plugin.json` /
  `.cursor-plugin/plugin.json` / `plugin.json`) labelled as a skill.
- `experimental` trust line without `consent allow`.
- Harness not in the component's compatibility list.
- "Latest" or a branch name instead of an exact `X.Y` and commit.
- Treating `ai-stp skill install` as if it published this component.
- Treating `author_verified` as `component_verified`.

??? question "Can a skill be used without publishing it"
    Yes. Your own, imported or exactly pinned skill can be used after local
    checks. It does not thereby become platform-verified, and it must be shown
    as exactly what it is: a local or pinned object
    (`local_owner_or_pinned`).

## Author checklist

1. Scaffold with `--type skill --language none` and keep `SKILL.md` at the
   package root (under `source/` in the authoring tree).
2. Fill `name` and `description`. Put harness-specific keys under
   `metadata`.
3. Add `scripts/`, `references/`, and `assets/` only when the workflow
   needs them. Declare what they do in the passport.
4. Run `ai-stp component skill validate --path <package> --json` and fix
   every `SKxxx` code.
5. Pin an exact public GitHub commit and subpath. No secrets in the tree.
6. `component discover` → `component adopt` → `component passport validate`.
7. `component version release` to mint immutable `X.Y`.
8. Publish through [the publication path](https://ai-stp.aiguild.space/en/docs/components).
9. In a setup, pin that `X.Y`. Updating later is a new setup version.

Related: [Authoring](https://ai-stp.aiguild.space/en/docs/components),
[Components](https://ai-stp.aiguild.space/en/docs/components), [CLI Agent Skill](https://ai-stp.aiguild.space/en/docs/components).
