---
title: "plugin"
description: "Plugin components: native harness extensions, distinct from a marketplace."
---

# `plugin`

A `plugin` is a native extension of a harness. It can add skills,
agents, commands, hooks, client MCP configuration, or other surfaces
**where that harness documents them**.

A plugin answers the question: **which package extends the harness
itself?**

It does not answer "which single MCP server is connected?"
([`mcp`](mcp.md)), "which workflow should the agent follow?"
([`skill`](skill.md)), or "which catalog of plugins is this shipped
through?" (that is **marketplace** packaging, not a component kind).

!!! warning "A plugin is not a marketplace"

    `marketplace` is native packaging: a collection or ledger a harness
    uses to distribute plugins. It is **not** one of the closed component
    kinds. Grok `plugins/marketplaces` is a service container, not a
    plugin, and discovery does not return it as a candidate.

    A directory under `plugins/` becomes a plugin only through an exact
    manifest from the closed set. JSON manifest **values** are not read
    — the file's existence proves that the directory is a plugin.

    | Object | What it is | Component kind? |
    | --- | --- | --- |
    | Pack with `.claude-plugin/plugin.json` | plugin | yes, `plugin` |
    | Pack with `.codex-plugin/plugin.json` | plugin | yes, `plugin` |
    | Pack with `.cursor-plugin/plugin.json` | plugin | yes, `plugin` |
    | Pack with `plugin.json` | plugin | yes, `plugin` |
    | Marketplace / `plugins/marketplaces` | packaging / service container | no |

    Inside a proven plugin, nested members keep their own kinds (`skill`,
    `agent`, `command`, `hook`, `instruction`, `mcp`). The pack is the
    plugin; the members are not relabelled as plugins.

## Neighbours

| Kind | The main difference |
| --- | --- |
| `skill` | a skill extends the agent's working behaviour; a plugin extends the harness |
| `mcp` | an MCP **server** is `mcp` with `harness_id=null`; plugin `.mcp.json` is client config, still kind `mcp` |
| `instruction` | Cursor plugin `rules/` files are instructions, not the plugin itself |
| `hook` | a plugin may carry `hooks/hooks.json`; that member is kind `hook` |
| `command` | a plugin may carry `commands/`; each file is kind `command` |
| `agent` | a plugin may carry `agents/`; each file is kind `agent` |
| `setting` | a setting holds parameters; a plugin is a package |

Choose `plugin` when you are shipping a harness package. Choose `mcp`
when you are shipping a server. Choose `skill` when you only need a
workflow.

## Recommended package structure

`--language` for a plugin is one of `python`, `typescript`,
`javascript`, `rust`, `go`, or `dart-flutter`. OpenCode and Pi plugins
are a **single JS/TS module**, not an invented manifest: `--language`
must be `javascript` or `typescript` for those two harnesses.

Manifest-directory plugins (Claude Code, Codex, Cursor, and portable
`plugin.json`):

```text
review-pack/
├── .claude-plugin/
│   └── plugin.json                # or .codex-plugin / .cursor-plugin / plugin.json
├── skills/                        # optional; each child with SKILL.md is a skill
├── agents/                        # Claude Code / Cursor, when present
├── commands/                      # Claude Code / Cursor, when present
├── hooks/
│   └── hooks.json                 # Claude Code / Codex, when present
└── .mcp.json                      # Claude Code client config; not a server
```

Cursor inside a proven pack: `skills`, `agents`, `commands`, and
`rules` (each file is an `instruction`). The official schema also names
`hooks` and `mcpServers`; the walker does not invent those types from an
adjacent directory.

When you start from `ai_stp`, scaffold first. The authoring directory is
wider than the published package: `discover` / `adopt` transfer `source/`
when portable and `projections/<harness>/` when a harness was selected,
not the whole tree.

```text
review-pack/                       # component-scaffold/6
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
└── source/
    ├── plugin.json
    └── skills/
        └── README.md
```

```bash
ai-stp component scaffold plan \
  --type plugin \
  --language python \
  --harness portable \
  --name review-pack \
  --output ./review-pack \
  --json

ai-stp component scaffold apply \
  --type plugin \
  --language python \
  --harness portable \
  --name review-pack \
  --output ./review-pack \
  --expected-plan-digest <digest> \
  --json
```

For OpenCode or Pi, scaffold a single `{name}.js` or `{name}.ts` under
`source/` (and `projections/<harness>/`). Do not invent a `plugin.json`
those products do not use.

Adoption of a directory requires a closed-set manifest. The plugin names
in that set are `plugin.json`, `.claude-plugin/plugin.json`,
`.codex-plugin/plugin.json`, and `.cursor-plugin/plugin.json`. A
`plugins/` directory whose members carry no manifest from **any**
supported harness produces no components and reports
`unsupported_manifest` once per collection.

There is no `ai-stp component plugin validate`. Structural readiness is
`component passport validate`. Kind-specific specification checking
exists only for [`skill`](skill.md).

## Standards and frameworks

- Claude Code plugins (verified):
  [Create plugins](https://code.claude.com/docs/en/plugins). Discovery
  `layout_source` for that pack is `code.claude.com/docs/en/plugins`.
- Codex and Cursor packs: cite `layout_source` on the finding
  (`learn.chatgpt.com/docs/build-plugins`,
  `cursor.com/docs/reference/plugins`). Do not invent a docs URL.
- Nested skills still follow the
  [Agent Skills Specification](https://agentskills.io/specification).
- Nested MCP client config follows [MCP](https://modelcontextprotocol.io)
  as a protocol; the `.mcp.json` file is still not a server.

NVIDIA SkillSpector and Cisco Skill Scanner are skill scanners. They
do not validate a plugin package as a whole.

## Native layouts per harness

Discovery only reports layouts that are declared. Exact paths on a
machine come from `ai-stp component discover --json`. Each finding
carries `layout_source`. If classification is uncertain, show that
field; do not guess a neighbour's path.

From the discovery matrix:

| Harness | Global | Project | Notes that are in the discovery contract |
| --- | --- | --- | --- |
| Claude Code | yes | yes | proven only by exact `.claude-plugin/plugin.json`; inside: `skills`, `agents`, `commands`, `hooks/hooks.json`, `.mcp.json` |
| Codex | plugin root | plugin root | proven by `.codex-plugin/plugin.json`; inside: `skills`, `hooks/hooks.json` |
| Pi | yes | yes | bounded native plugin/extension directory; no separate project-plugin manifest declared |
| OpenCode | yes | yes | bounded native plugin directory; single JS/TS module |
| Grok Build | yes | yes | bounded native plugin directory; `plugins/marketplaces` is **not** a plugin |
| Cursor | yes | yes | proven by `.cursor-plugin/plugin.json`; inside: `skills`, `agents`, `commands`, `rules` |
| Antigravity | yes | yes | bounded native plugin directory |
| `undefined` | portable conventions | portable conventions | not a harness; automatic install is not considered safe |

A pack for one harness does not trigger a complaint from another: a
Codex pack remains a pack even without a Claude manifest.

Under `skills/`, a directory with `SKILL.md` is a skill; a directory
with `.claude-plugin/plugin.json` or `plugin.json` is a **plugin**.
Discovery tells them apart by the manifest, not by the parent folder
name.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

## Versions are `X.Y`, not SemVer

A published plugin version is immutable and has the form `X.Y`. There is
no patch number. Changing the manifest, a nested member, or the entry
module is a new version. Updating a plugin inside a setup is a new setup
version.

Vendor plugin manifests may contain their own version strings. Those
strings are not `ai_stp` versions. `ai_stp` still mints immutable `X.Y`.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` opens the next major line. A major line is a separate access
boundary.

## What `ai_stp` checks

The catalog percent and the required-versus-optional split are explained
on [Security checks](../security-checks.md). For a plugin, expect at
least:

- structure, digest, license, tags, source repository;
- bounded unpack and path denylist;
- secret scanning (`secrets_heuristic`, and Gitleaks when enabled);
- prompt-injection and hidden-content rules;
- language SAST and SCA when scripts and lockfiles are present;
- nested members of other kinds, when present, are covered by the
  families on [Security checks](../security-checks.md) for those kinds.

A passed scan reduces known risk. It is not a guarantee that the plugin
is harmless. Required checks that fail or cannot run block publication.

Before install, also look at:

| Check | Why it matters |
| --- | --- |
| Exact manifest | no manifest means it is not a plugin |
| Nested members | skills, hooks, and `.mcp.json` change behaviour after install |
| Provenance | `github/exact` is not platform verification or plugin safety |
| Who is the author | a verified author does not make the plugin automatically safe |
| Which `X.Y` is pinned | updating a plugin makes a new version of the setup |
| Trust line | `experimental` needs explicit consent |

`author_verified` and `component_verified` are independent. Neither is a
safety guarantee.

## Related CLI commands

Only commands that exist. Flags always from the CLI pages, and always
`--json`. The executable is `ai-stp` (package `ai-stp-cli`). There is no
`component inspect` and no `setup show`. The only kind-specific validate
is `ai-stp component skill validate`.

**This kind, specifically:** there is no `component plugin validate`.
Use passport validation. Nested skills may still be checked with:

```bash
ai-stp component skill validate --path <directory-with-SKILL.md> --json
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

If the path is also claimed as a skill directory:

```bash
ai-stp component adopt --path <source_path> --kind plugin --json
```

**Find, select, install:**

```bash
ai-stp registry search --kind component --query <name> --json
ai-stp select eligibility --harness <id> --json
ai-stp install plan --json
```

A plugin can also be an embedded member of a compose manifest. See
[Setups](../setups/index.md).

## How a plugin moves through `ai_stp`

=== "Author"
    The author publishes the plugin from a public GitHub source, or
    imports it locally. The version pins an exact commit and subpath.
    Discovery does not run the plugin.

=== "Catalog"
    The catalog shows what it is for, the supported harnesses, the
    constraints, the author's trusted status and the component's own
    independent status.

=== "Compiler"
    The compiler checks that the plugin can be built into the chosen
    setup and that its file structure suits the provider's projection.

=== "Provider"
    The provider installs the native package only after a plan, a digest
    and a confirmation. Rollback must return the target as far as that
    harness's provider allows.

## Red flags

- A `plugins/` directory with no supported manifest, treated as a
  plugin. Discovery reports `unsupported_manifest` once; an empty
  inventory without that diagnostic would be worse.
- Labelling a marketplace, or Grok `plugins/marketplaces`, as kind
  `plugin`.
- Putting `commands/`, `agents/`, `skills/`, or `hooks/` **inside**
  `.claude-plugin/` (only `plugin.json` belongs there).
- A directory under `skills/` that is actually a plugin, labelled as a
  skill.
- Opening `.mcp.json` to copy tokens into a passport.
- Live tokens, private keys, or `.env` bodies in the package.
- `experimental` trust line without `consent allow`.
- Harness not in the component's compatibility list.
- "Latest" or a branch name instead of an exact `X.Y` and commit.
- Treating `author_verified` as `component_verified`.
- Treating `github/exact` as proof the plugin is safe.

??? question "Can a plugin be used without publishing it"
    Yes. Your own, imported or exactly pinned plugin can be used after
    local checks. It does not thereby become platform-verified, and it
    must be shown as exactly what it is: a local or pinned object
    (`local_owner_or_pinned`). Supply-chain and post-install behaviour
    still need a plan.

## Author checklist

1. Scaffold with `--type plugin` and a real `--language`. For OpenCode
   or Pi use `javascript` or `typescript` and a single module.
2. Prove the pack with the exact manifest for that harness. Do not
   invent a marketplace kind.
3. Put nested members at the plugin root (`skills/`, `agents/`,
   `commands/`, `hooks/hooks.json`, `.mcp.json`, Cursor `rules/`) only
   when that harness's proven pack actually reads them.
4. Declare post-install behaviour in the passport. No secrets.
5. Run `ai-stp component discover --root . --json` and read
   `layout_source` on the plugin finding and on nested members.
6. `component adopt --path <exact source_path>` — add `--kind plugin`
   if the path is also a skill directory.
7. Pin an exact public GitHub commit and subpath.
8. `component passport validate` → `component version release` to mint
   immutable `X.Y`.
9. Publish through [the publication path](../publishing/index.md). In a
   setup, pin that `X.Y`.

Related: [Authoring](../publishing/authoring.md),
[Components](index.md), [`mcp`](mcp.md), [`skill`](skill.md).
