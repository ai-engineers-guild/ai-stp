---
title: "hook"
description: "Hook components: actions bound to harness lifecycle events."
---

# `hook`

A `hook` is an action bound to a harness lifecycle event: before a tool
runs, after a write, before a prompt is sent, or at another event the
harness actually documents.

A hook answers the question: **what must run automatically when this
event happens?**

It does not answer "which named shortcut do I type?" ([`command`](command.md)),
"how should the agent do this class of task?" ([`skill`](skill.md)), or
"which standing rule should the agent remember?"
([`instruction`](instruction.md)).

A hook is the most sensitive of the eight kinds: it can change state
while the user is looking at something else.

!!! warning "A harness hook is not a React hook, and not a webhook"

    Kind `hook` is a harness lifecycle handler, usually a `hooks.json`
    plus a command handler.

    An ordinary `src/hooks/useFoo.ts`, a product webhook, or an arbitrary
    `hooks/` folder is **not** this kind. `unsupported` in the discovery
    matrix does not become a filename heuristic.

    A plugin may *contain* a hooks directory. That member is still kind
    `hook`. The pack around it is kind [`plugin`](plugin.md). Discovery
    reads plugin hooks only inside a pack proven by the exact manifest.

    | Object | Kind | When discovery reports it |
    | --- | --- | --- |
    | `.codex/hooks.json` | `hook` | Codex project layout |
    | `hooks/hooks.json` inside a proven plugin | `hook` | Claude Code or Codex pack |
    | Grok `hooks/` directory | `hook` | declared Grok layout |
    | `src/hooks/useFoo.ts` | none | not a harness component |

## Neighbours

| Kind | The main difference |
| --- | --- |
| `command` | a command starts when a person or agent invokes it; a hook starts on an event |
| `skill` | a skill waits to be selected for a task; a hook does not wait |
| `instruction` | an instruction is text; a hook is an action |
| `plugin` | a plugin may *contain* a hooks directory; the hook is still kind `hook` |
| `mcp` | MCP is a tool interface; a hook is not a protocol server |
| `agent` | an agent is a role; a hook is not a subagent |
| `setting` | a setting holds parameters; a hook holds an event and a handler |

Choose `hook` when the check must be unavoidable on that event. Choose
`command` when a person should start the work. Choose `instruction` when
a reminder in prose is enough.

## Recommended package structure

A hook handler must be directly runnable after installation. `--language`
is `python`, `typescript`, `javascript`, or `dart-flutter`. Rust and Go
are refused: the provider does not perform a hidden source build.

The portable native layout is a `hooks.json` manifest plus a handler.
The authoring directory holds `source/hook-source.json` (event, order,
blocking failure, handler). A portable scaffold also writes those derived
bytes under `source/` so discover/adopt of `source/` sees a closed-set
manifest. A concrete harness receives generated `hooks.json` and a handler
under `projections/<harness>/`. `discover` / `adopt` transfer `source/`
when portable and `projections/<harness>/` when a harness was selected,
not the whole tree.

```text
pre-tool-check/                    # component-scaffold/6
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
├── source/
│   └── hook-source.json
└── projections/codex/
    ├── GENERATED.md
    ├── hooks.json
    └── hooks/
        └── handler.py
```

```bash
ai-stp component scaffold plan \
  --type hook \
  --language python \
  --harness codex \
  --name pre-tool-check \
  --output ./pre-tool-check \
  --json

ai-stp component scaffold apply \
  --type hook \
  --language python \
  --harness codex \
  --name pre-tool-check \
  --output ./pre-tool-check \
  --expected-plan-digest <digest> \
  --json
```

`--language rust` and `--language go` fail closed for this kind.

Adoption accepts a path discovery already named. A directory must carry
a closed-set manifest. `hooks.json` is in that set. A plugin
hook-directory is one component: it includes the manifest and adjacent
scripts in a deterministic artifact. Scripts are **not** run during
discovery.

There is no `ai-stp component hook validate`. Structural readiness is
`component passport validate`. Kind-specific specification checking
exists only for [`skill`](skill.md).

## Standards and frameworks

There is no independent hook specification comparable to the
[Agent Skills Specification](https://agentskills.io/specification) or
to [MCP](https://modelcontextprotocol.io). Each harness documents its
own events.

Cite `layout_source` from `ai-stp component discover --json` when
classification is uncertain. Do not guess a neighbour's path, and do
not treat an ordinary `src/hooks/useFoo.ts` or a business webhook as a
harness hook — `unsupported` in the matrix does not become a filename
heuristic.

NVIDIA SkillSpector and Cisco Skill Scanner are skill scanners. They
do not validate hooks.

## Native layouts per harness

Discovery only reports layouts that are declared. Exact paths on a
machine come from `ai-stp component discover --json`. Each finding
carries `layout_source`. If classification is uncertain, show that
field; do not guess a neighbour's path.

From the discovery matrix:

| Harness | Global | Project | Notes that are in the discovery contract |
| --- | --- | --- | --- |
| Claude Code | not a top-level cell | not a top-level cell | manifest-backed: `hooks/hooks.json` **inside** a plugin proven by `.claude-plugin/plugin.json` |
| Codex | no | yes | only `.codex/hooks.json`, or `hooks/hooks.json` inside a plugin proven by `.codex-plugin/plugin.json` |
| Pi | no | no | not a declared hook layout |
| OpenCode | no | no | not a declared hook layout |
| Grok Build | yes | yes | bounded native hook directory |
| Cursor | not invented from an adjacent directory | not invented from an adjacent directory | official plugin schema names `hooks`; walker does not invent them from an adjacent directory |
| Antigravity | yes | yes | |
| `undefined` | portable conventions | portable conventions | not a harness; automatic install is not considered safe |

A Claude Code project plugin pack is proven only by exact
`.claude-plugin/plugin.json`. Inside that pack, discovery reads
`hooks/hooks.json` as one hook component.

A Cursor pack is proven by `.cursor-plugin/plugin.json`. The walker
does not create a hook finding from a neighbouring `hooks/` directory
that the tree does not carry.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

## Versions are `X.Y`, not SemVer

A published hook version is immutable and has the form `X.Y`. There is
no patch number. Changing the event, the matcher, or the handler is a
new version. Updating a hook inside a setup is a new setup version.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` opens the next major line. A major line is a separate access
boundary.

## What `ai_stp` checks

The catalog percent and the required-versus-optional split are explained
on [Security checks](../security-checks.md). For a hook, expect at
least:

- structure, digest, license, tags, source repository;
- bounded unpack and path denylist;
- secret scanning (`secrets_heuristic`, and Gitleaks when enabled);
- prompt-injection and hidden-content rules;
- `hook_schema_static` and `hook_command_argv` (schema, argv);
- language SAST and SCA when scripts and lockfiles are present.

A passed scan reduces known risk. It is not a guarantee that the handler
is harmless. Required checks that fail or cannot run block publication.

Before install, also look at:

| Check | Why it matters |
| --- | --- |
| The event | a person must be able to name when it fires |
| The action | one sentence; if you cannot say it, do not enable it |
| Disable / rollback | a hook that cannot be turned off is not MVP-safe |
| Who is the author | a verified author does not make the handler automatically safe |
| Which `X.Y` is pinned | updating a hook makes a new version of the setup |
| Trust line | `experimental` needs explicit consent |

`author_verified` and `component_verified` are independent. Neither is a
safety guarantee.

## Related CLI commands

Only commands that exist. Flags always from the CLI pages, and always
`--json`. The executable is `ai-stp` (package `ai-stp-cli`). There is no
`component inspect` and no `setup show`. The only kind-specific validate
is `ai-stp component skill validate`.

**This kind, specifically:** there is no `component hook validate`. Use
passport validation.

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

**Find, select, install:**

```bash
ai-stp registry search --kind component --query <name> --json
ai-stp select eligibility --harness <id> --json
ai-stp install plan --json
```

A hook can also be an embedded member of a compose manifest. See
[Setups](../setups/index.md).

## How a hook moves through `ai_stp`

=== "Author"
    The author publishes the hook from a public GitHub source, or imports
    it locally. The version pins an exact commit and subpath. Discovery
    never executes the handler.

=== "Catalog"
    The catalog shows the event, the supported harnesses, the
    constraints, the author's trusted status and the component's own
    independent status.

=== "Compiler"
    The compiler checks that the harness supports that lifecycle event
    and that the handler can be projected for the provider.

=== "Provider"
    The provider writes the native hook configuration only after a plan,
    a digest and a confirmation. Status must then show the hook, its
    source, and how to disable it.

## Red flags

- An ordinary `src/hooks/` React directory classified as a harness hook.
- A `hooks/` directory next to a Cursor plugin treated as a hook even
  though the walker does not invent that layout.
- Codex hooks anywhere except `.codex/hooks.json` or
  `hooks/hooks.json` inside a proven `.codex-plugin/plugin.json` pack.
- Scaffolding with `--language rust` or `--language go`.
- Handlers that download and pipe into a shell.
- Live tokens, private keys, or `.env` bodies in the package.
- No documented way to disable or roll the hook back.
- `experimental` trust line without `consent allow`.
- Harness not in the component's compatibility list.
- "Latest" or a branch name instead of an exact `X.Y` and commit.
- Treating `author_verified` as `component_verified`.
- Copying `hooks.json` into a target instead of going through the
  provider plan.

??? question "Can a hook be used without publishing it"
    Yes. Your own, imported or exactly pinned hook can be used after
    local checks. It does not thereby become platform-verified, and it
    must be shown as exactly what it is: a local or pinned object
    (`local_owner_or_pinned`). Preview, backup, and a way to switch it
    off still apply.

## Author checklist

1. Scaffold with `--type hook` and a directly runnable `--language`
   (`python`, `typescript`, `javascript`, or `dart-flutter`).
2. Fill `source/hook-source.json` with the event, order, blocking
   failure, and handler command. A portable scaffold keeps the derived
   `hooks.json` and handler under `source/`. For a concrete harness they
   live under `projections/<harness>/`.
3. Declare what the handler does, what it reads, and how to disable it
   in the passport. No secrets.
4. Run `ai-stp component discover --root . --json` and read
   `layout_source` on the finding.
5. `component adopt --path <exact source_path>`.
6. Pin an exact public GitHub commit and subpath.
7. `component passport validate` → `component version release` to mint
   immutable `X.Y`.
8. Publish through [the publication path](../publishing/index.md).
9. In a setup, pin that `X.Y`. Updating later is a new setup version.

Related: [Authoring](../publishing/authoring.md),
[Components](index.md), [`command`](command.md), [`plugin`](plugin.md).
