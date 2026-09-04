---
title: "mcp"
description: "MCP components: servers that expose tools, and client config that names them."
---

# `mcp`

An `mcp` is how an agent gets a structured tool surface: a server that
speaks the Model Context Protocol, or the client configuration that
points a harness at such a server.

An MCP component answers the question: **which external tool interface
is connected?**

It does not answer "how should the agent use that tool?" ([`skill`](skill.md)
or [`instruction`](instruction.md)), "which package extends the harness?"
([`plugin`](plugin.md)), or "which named shortcut do I type?"
([`command`](command.md)).

!!! warning "Two different MCP objects"

    This page covers both native roles discovery can report. They share
    kind `mcp` and they are not the same object.

    | Object | `native_role` | What discovery does |
    | --- | --- | --- |
    | MCP **server** package | `mcp_server` | `harness_id=null`; proves a package chain; never runs the server |
    | Plugin `.mcp.json` | `mcp_client_config` | proves itself by name; discovery **does not open it** |
    | Servers inside a settings file | `mcp_client_config` | file is also a `setting`; only server **names** are read |

    A plugin `.mcp.json` is client config, not a server. Tokens, access
    bearing URLs, command, args, headers, and env **never** enter
    discovery output, passports, logs, or fixtures.

    Files named `mcp.json` under Pi are user extensions, not harness
    layouts. The machine table reports `no_documented_mcp_client_config`.

## Neighbours

| Kind | The main difference |
| --- | --- |
| `plugin` | a plugin may *carry* `.mcp.json` client config; the server package is still `mcp` |
| `setting` | Codex, OpenCode, and Grok Build keep client servers inside a file also declared as `setting` |
| `skill` | a skill explains when and how to use a tool; MCP is the tool interface |
| `instruction` | standing rules about tools stay text; they do not start a server |
| `hook` | a hook fires on an event; MCP waits to be called as a tool |
| `command` | a command is a named shortcut; MCP is a protocol surface |
| `agent` | a role may be allowed to use MCP tools; the server is not the role |

Choose `mcp` when the agent must call an external tool through MCP.
Choose `plugin` when you are shipping a harness package that may include
client config. Choose `setting` when you are pinning parameters that are
not server entries.

## Recommended package structure

`--language` for an MCP **server** is one of `python`, `typescript`,
`javascript`, `rust`, `go`, or `dart-flutter`. The kind is executable.

An MCP **server** package belongs to no single harness
(`harness_id=null`). Discovery does not guess from an `mcp` substring.
It requires a consistent chain:

- **Python:** `pyproject.toml` → MCP SDK dependency → `project.scripts`
  → exact module import of the SDK.
- **TypeScript:** `package.json` → SDK dependency → `bin` / script
  source → exact SDK import.

```text
github-issues/                     # published server package
├── pyproject.toml                 # dependencies include mcp or fastmcp
└── src/
    └── github_issues/
        └── server.py              # project.scripts target; imports the SDK
```

```text
github-issues/                     # TypeScript server package
├── package.json                   # @modelcontextprotocol/sdk or fastmcp
└── src/
    └── index.ts                   # bin/script entry; imports the SDK
```

When you start from `ai_stp`, scaffold first. The authoring directory is
wider than the published package: `discover` / `adopt` transfer `source/`
when portable and `projections/<harness>/` when a harness was selected,
not the whole tree. The scaffold plants `source/mcp.json` plus a language
entry; a discoverable **server** still needs the manifest chain above.
Claude Code `mcp` is refused: there is no provider-owned MCP surface.

```text
github-issues/                     # component-scaffold/6
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
└── source/
    ├── mcp.json
    └── src/main.py                # python handler; add the package manifest
```

```bash
ai-stp component scaffold plan \
  --type mcp \
  --language python \
  --harness portable \
  --name github-issues \
  --output ./github-issues \
  --json

ai-stp component scaffold apply \
  --type mcp \
  --language python \
  --harness portable \
  --name github-issues \
  --output ./github-issues \
  --expected-plan-digest <digest> \
  --json
```

For `required_env`, record names and purposes in the passport, never
values. Secrets, tokens, and passwords do not go into a passport.

There is no `ai-stp component mcp validate`. Structural readiness is
`component passport validate`. Kind-specific specification checking
exists only for [`skill`](skill.md).

## Standards and frameworks

- [Model Context Protocol](https://modelcontextprotocol.io) — the
  independent standard.
- Build-server guide used as discovery `layout_source` for server
  packages: [Build an MCP server](https://modelcontextprotocol.io/docs/develop/build-server).
- SDK names discovery will accept in the dependency chain: Python `mcp`
  or `fastmcp`; TypeScript `@modelcontextprotocol/sdk` or `fastmcp`.
- NVIDIA SkillSpector and Cisco Skill Scanner are skill scanners. They
  do not validate MCP.

Client layouts are declared per harness. Cite `layout_source` on the
finding rather than guessing a vendor path.

## Native layouts per harness

Discovery only reports layouts that are declared. Exact paths on a
machine come from `ai-stp component discover --json`. Each finding
carries `layout_source`. If classification is uncertain, show that
field; do not guess a neighbour's path.

From the discovery matrix:

| Harness | Global | Project | Notes that are in the discovery contract |
| --- | --- | --- | --- |
| Claude Code | yes | yes | plugin-internal `.mcp.json` is `mcp_client_config`; discovery does not open it |
| Codex | names in `config.toml` | names in `config.toml` | file is also a `setting`; key `mcp_servers`; existence is not enough |
| Pi | no | no | gap `no_documented_mcp_client_config`; `mcp.json` files are user extensions |
| OpenCode | names in `opencode.json` / `opencode.jsonc` | same files | file is also a `setting`; key `mcp`; existence is not enough |
| Grok Build | names in `config.toml` | names in `config.toml` | file is also a `setting`; key `mcp_servers`; existence is not enough |
| Cursor | not invented from an adjacent directory | not invented from an adjacent directory | official plugin schema names `mcpServers`; walker does not invent the file |
| Antigravity | yes | yes | |
| `undefined` | portable conventions | portable conventions | not a harness; automatic install is not considered safe |
| (server package) | n/a | n/a | `harness_id=null`; Python or TypeScript chain as above |

Codex, OpenCode, and Grok Build keep client servers inside a file also
declared as `setting`. File existence is not enough: at least one server
must be declared under the key. One file can produce two findings
(`setting` + `mcp`). Only server **names** enter `evidence_refs` (for
example `mcp_servers.github`). Values next to a name — command,
arguments, URL, headers, environment — are neither read nor returned.

A plugin `.mcp.json` proves itself by name, so discovery does not open
it. Working servers for Claude Code packs reside there; guessing a
different home file is not a layout.

```bash
ai-stp component discover --root . --json
ai-stp toolchain harness-capabilities --json
```

If the same path is both a `setting` and an `mcp`, name `--kind` on
adopt. Do not adopt the file twice under guessed kinds.

## Versions are `X.Y`, not SemVer

A published MCP version is immutable and has the form `X.Y`. There is no
patch number. Changing the server, its entry point, or the client
declaration is a new version. Updating MCP inside a setup is a new setup
version.

```bash
ai-stp component version list --id <stable_id> --json
ai-stp component version release --id <stable_id> --json
```

`--major` opens the next major line. A major line is a separate access
boundary.

## What `ai_stp` checks

The catalog percent and the required-versus-optional split are explained
on [Security checks](../security-checks.md). For MCP, expect at least:

- structure, digest, license, tags, source repository;
- bounded unpack and path denylist;
- secret scanning (`secrets_heuristic`, and Gitleaks when enabled);
- prompt-injection and hidden-content rules;
- `mcp_config_static` (schema, transport policy, capability);
- language SAST and SCA when scripts and lockfiles are present.

A passed scan reduces known risk. It is not a guarantee that the server
is harmless. Required checks that fail or cannot run block publication.

Before install, also look at:

| Check | Why it matters |
| --- | --- |
| `native_role` | a client config is not a server; a server is not a plugin |
| Required permissions | MCP widens what the agent can reach |
| How secrets are supplied | names in the passport, values in the environment or OS store |
| Who is the author | a verified author does not make the server automatically safe |
| Which `X.Y` is pinned | updating MCP makes a new version of the setup |
| Trust line | `experimental` needs explicit consent |

`author_verified` and `component_verified` are independent. Neither is a
safety guarantee.

## Related CLI commands

Only commands that exist. Flags always from the CLI pages, and always
`--json`. The executable is `ai-stp` (package `ai-stp-cli`). There is no
`component inspect` and no `setup show`. The only kind-specific validate
is `ai-stp component skill validate`.

**This kind, specifically:** there is no `component mcp validate`. Use
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

When the finding is also a setting file:

```bash
ai-stp component adopt --path <source_path> --kind mcp --json
```

**Find, select, install:**

```bash
ai-stp registry search --kind component --query <name> --json
ai-stp select eligibility --harness <id> --json
ai-stp install plan --json
```

An MCP component can also be an embedded member of a compose manifest.
See [Setups](../setups/index.md).

## How an MCP component moves through `ai_stp`

=== "Author"
    The author publishes the server or client config from a public GitHub
    source, or imports it locally. The version pins an exact commit and
    subpath. Secret values stay out of the tree.

=== "Catalog"
    The catalog shows what it is for, the supported harnesses, the
    required permissions, the author's trusted status and the
    component's own independent status.

=== "Compiler"
    The compiler checks that the MCP object can be built into the chosen
    setup and that its file structure suits the provider's projection.

=== "Provider"
    The provider registers the native client entry or ships the server
    package only after a plan, a digest and a confirmation. It does not
    copy tokens from the passport — there are none.

## Red flags

- Treating plugin `.mcp.json` as if it were the server package.
- Opening `.mcp.json` or a settings MCP block to "check" for tokens —
  discovery already refuses to read those values.
- Pi `mcp.json` files treated as a harness layout
  (`no_documented_mcp_client_config`).
- A `config.toml` / `opencode.json` with no servers under the key,
  labelled as MCP because the file exists.
- Unpinned `npx` / `uvx` launchers, or command/args/URL/headers/env
  stored in the passport.
- Live tokens, private keys, or `.env` bodies in the package.
- `experimental` trust line without `consent allow`.
- Harness not in the component's compatibility list.
- "Latest" or a branch name instead of an exact `X.Y` and commit.
- Treating `author_verified` as `component_verified`.
- Skill scanners cited as if they validated this kind.

??? question "Can an MCP component be used without publishing it"
    Yes. Your own, imported or exactly pinned MCP object can be used
    after local checks. It does not thereby become platform-verified, and
    it must be shown as exactly what it is: a local or pinned object
    (`local_owner_or_pinned`).

## Author checklist

1. Scaffold with `--type mcp` and a real `--language` (not `none`).
2. For a **server**, complete the Python or TypeScript chain: manifest,
   SDK dependency, declared entry, exact SDK import. Do not run the
   server to "prove" it.
3. For **client config**, keep values that bear access out of the
   artifact. Record env *names* only.
4. Declare filesystem, network, and credential needs in the passport.
5. Run `ai-stp component discover --root . --json` and read
   `native_role`, `harness_id`, and `layout_source`.
6. `component adopt --path <exact source_path>` — add `--kind mcp` when
   the file is also a setting.
7. Pin an exact public GitHub commit and subpath. No secrets in the tree.
8. `component passport validate` → `component version release` to mint
   immutable `X.Y`.
9. Publish through [the publication path](../publishing/index.md). In a
   setup, pin that `X.Y`.

Related: [Authoring](../publishing/authoring.md),
[Components](index.md), [`plugin`](plugin.md), [`setting`](setting.md).
