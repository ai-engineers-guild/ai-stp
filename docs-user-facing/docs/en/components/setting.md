---
title: "setting"
description: "Setting components: parameters and modes, never secrets, sometimes sharing a file with MCP."
---

# `setting`

A `setting` is the configuration part of a setup: parameters, modes,
feature flags, preferences, thresholds, and other values the harness or
the provider knows how to apply.

A setting answers the question: **which non-secret parameters should be
pinned?**

It does not answer "what standing rule should the agent remember?"
([`instruction`](instruction.md)), "what must run on an event?"
([`hook`](hook.md)), or "which MCP servers are declared in this same
file?" (that finding is kind [`mcp`](mcp.md), `native_role`
`mcp_client_config`).

A setting must not hold secrets. If a value is a token, a password, a
private key, or a credential, it goes through a supported secret store,
not through a component's passport.

!!! warning "One file can be a setting and an MCP finding"

    Codex, OpenCode, and Grok Build keep client MCP servers inside a
    file also declared as `setting`:

    | Harness | File | MCP key |
    | --- | --- | --- |
    | Codex | `config.toml` | `mcp_servers` |
    | OpenCode | `opencode.json` / `opencode.jsonc` | `mcp` |
    | Grok Build | `config.toml` | `mcp_servers` |

    File existence proves the **setting**, never the servers. The file
    becomes an `mcp` finding only when at least one server is declared
    under that key. One file can produce two findings of different
    types. Adopt with `--kind` when the path is claimed by both.

    Only server **names** are read into `evidence_refs`. Values
    (command, args, URL, headers, env) are never read.

## Neighbours

| Kind | The main difference |
| --- | --- |
| `instruction` | an instruction is prose; a setting is a typed parameter |
| `mcp` | MCP servers may live *inside* the same file; they are still kind `mcp` |
| `hook` | a hook is an action; a setting does not fire |
| `command` | a command is invoked; a setting is applied |
| `plugin` | a plugin is a package; a setting is configuration |
| `skill` | a skill is a workflow; a setting is not |
| `agent` | an agent is a role; a setting is not |

Choose `setting` when the provider or the CLI reads a value. Choose
`instruction` when the agent should be told in prose. Choose `hook` or
`command` if the value starts an action.

## Recommended package structure

`setting` is declarative. `--language` is `none`. Portable native output
is `settings.json` (an empty JSON object in the scaffold). A concrete
harness may project `config.toml`, `opencode.json` / `opencode.jsonc`,
or another declared settings file instead.

```text
strict-mode/                       # component-scaffold/2
├── .ai-stp-template.json
├── authoring-template.md
├── component-passport.json
├── eval-profile.json
├── README.md
├── SAFETY.md
├── PUBLICATION.md
└── native/
    └── settings.json
```

```bash
ai-stp component scaffold plan \
  --type setting \
  --language none \
  --harness portable \
  --name strict-mode \
  --output ./strict-mode \
  --json

ai-stp component scaffold apply \
  --type setting \
  --language none \
  --harness portable \
  --name strict-mode \
  --output ./strict-mode \
  --expected-plan-digest <digest> \
  --json
```

`--language` for a setting is `none`. The kind is declarative.

Put in the artifact only values that may be stored:

| May be | May not be |
| --- | --- |
| an execution mode | an API token |
| the interface language | a password |
| a policy flag | a private key |
| a limit or a threshold | the contents of `.env` |
| a path inside the target, if it is not secret | an OAuth refresh token |

For `required_env`, record names and purposes in the passport, never
values.

There is no `ai-stp component setting validate`. Structural readiness is
`component passport validate`. Kind-specific specification checking
exists only for [`skill`](skill.md).

## Standards and frameworks

There is no independent setting specification comparable to the
[Agent Skills Specification](https://agentskills.io/specification) or
to [MCP](https://modelcontextprotocol.io). Each harness documents its
own configuration file.

Cite `layout_source` from `ai-stp component discover --json` when
classification is uncertain. Do not guess a neighbour's path, and do
not treat a settings file as MCP merely because it exists.

NVIDIA SkillSpector and Cisco Skill Scanner are skill scanners. They
do not validate settings.

## Native layouts per harness

Discovery only reports layouts that are declared. Exact paths on a
machine come from `ai-stp component discover --json`. Each finding
carries `layout_source`. If classification is uncertain, show that
field; do not guess a neighbour's path.

From the discovery matrix:

| Harness | Global | Project | Notes that are in the discovery contract |
| --- | --- | --- | --- |
| Claude Code | yes | yes | |
| Codex | yes | yes | `config.toml` may also yield an `mcp` finding when `mcp_servers` is populated |
| Pi | yes | yes | |
| OpenCode | yes | yes | `opencode.json` / `opencode.jsonc` may also yield an `mcp` finding when `mcp` is populated |
| Grok Build | yes | yes | `config.toml` may also yield an `mcp` finding when `mcp_servers` is populated |
| Cursor | yes | no | global setting in the bounded matrix; project setting is not a declared cell |
| Antigravity | yes | no | global setting in the bounded matrix |
| `undefined` | portable conventions | portable conventions | not a harness; automatic install is not considered safe |

A declared path still belongs to an untrusted machine. Discovery does
not read secret values out of a settings file to "check" them.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

If the same path answers to more than one kind, name `--kind` on adopt.

```bash
ai-stp component adopt --path <source_path> --kind setting --json
```

## Versions are `X.Y`, not SemVer

A published setting version is immutable and has the form `X.Y`. There
is no patch number. Changing a flag, a mode, or a threshold is a new
version. Updating a setting inside a setup is a new setup version.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` opens the next major line. A major line is a separate access
boundary.

## What `ai_stp` checks

The catalog percent and the required-versus-optional split are explained
on [Security checks](../security-checks.md). For a setting, expect at
least:

- structure, digest, license, tags, source repository;
- bounded unpack and path denylist;
- secret scanning (`secrets_heuristic`, and Gitleaks when enabled);
- prompt-injection and hidden-content rules.

A passed scan reduces known risk. It is not a guarantee that the
configuration is harmless. Required checks that fail or cannot run block
publication.

Before install, also look at:

| Check | Why it matters |
| --- | --- |
| Secret-looking keys | a setting is not a hiding place for tokens |
| Diff of values | configuration drift is how behaviour changes without a new skill |
| Dual findings | the same file may also be MCP client config |
| Who is the author | a verified author does not make the values automatically safe |
| Which `X.Y` is pinned | updating a setting makes a new version of the setup |
| Trust line | `experimental` needs explicit consent |

`author_verified` and `component_verified` are independent. Neither is a
safety guarantee.

## Related CLI commands

Only commands that exist. Flags always from the CLI pages, and always
`--json`. The executable is `ai-stp` (package `ai-stp-cli`). There is no
`component inspect` and no `setup show`. The only kind-specific validate
is `ai-stp component skill validate`.

**This kind, specifically:** there is no `component setting validate`.
Use passport validation.

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

A setting can also be an embedded member of a compose manifest. See
[Setups](../setups/index.md).

## How a setting moves through `ai_stp`

=== "Author"
    The author publishes the setting from a public GitHub source, or
    imports it locally. The version pins an exact commit and subpath.
    Secret values stay out of the tree.

=== "Catalog"
    The catalog shows the parameters, the supported harnesses, the
    constraints, the author's trusted status and the component's own
    independent status.

=== "Compiler"
    The compiler checks for conflicts with other components of the setup
    and that the file structure suits the provider's projection.

=== "Provider"
    The provider shows the configuration diff and writes the native
    surface only after a plan, a digest and a confirmation.

## Red flags

- Tokens, passwords, private keys, OAuth refresh tokens, or `.env`
  bodies in the setting, the passport, or README examples.
- Using a setting as a convenient place for a workflow, a hook, or a
  command.
- Labelling `config.toml` / `opencode.json` as MCP because the file
  exists, when the MCP key is empty.
- Opening the MCP block of a settings file to copy command, args, URL,
  headers, or env into a passport.
- `experimental` trust line without `consent allow`.
- Harness not in the component's compatibility list.
- "Latest" or a branch name instead of an exact `X.Y` and commit.
- Treating `author_verified` as `component_verified`.
- Copying a settings file into a target instead of going through the
  provider plan.

??? question "Can a setting be used without publishing it"
    Yes. Your own, imported or exactly pinned setting can be used after
    local checks. It does not thereby become platform-verified, and it
    must be shown as exactly what it is: a local or pinned object
    (`local_owner_or_pinned`). Secrets still do not belong in it.

## Author checklist

1. Scaffold with `--type setting --language none` and keep the native
   file under `native/`.
2. Store only non-secret parameters. Record env *names* in the passport
   if the harness will need a credential later.
3. If the file also declares MCP servers, treat that as a separate
   [`mcp`](mcp.md) finding. Do not put server values in this artifact.
4. Declare what the values change in `SAFETY.md`.
5. Run `ai-stp component discover --root . --json` and read
   `layout_source`, and `native_role` if a second finding appears.
6. `component adopt --path <exact source_path>` — add `--kind setting`
   when the path is also MCP.
7. Pin an exact public GitHub commit and subpath. No secrets in the tree.
8. `component passport validate` → `component version release` to mint
   immutable `X.Y`.
9. Publish through [the publication path](../publishing/index.md). In a
   setup, pin that `X.Y`.

Related: [Authoring](../publishing/authoring.md),
[Components](index.md), [`mcp`](mcp.md), [`instruction`](instruction.md).
