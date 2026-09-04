---
description: "Machine contract for read-only discovery of native components in supported harnesses."
last_verified: "2026-09-04"
---

# Native component discovery

## Boundary

The requirements owner is `SPEC-005` REQ-517 and REQ-518; the decisions are
`ADR-0054`, `ADR-0055`, and `ADR-0056`.
`component discover` checks only declared global layouts of supported harnesses and
layouts within an explicitly supplied `--root`. The command does not traverse home,
read values from discovered files, create a passport, or open the registry for writing.
A separate adapter under `ADR-0055` reads only declared size-bounded metadata manifests
to prove package provenance; it does not read arbitrary settings or secret values.
The MCP source adapter additionally reads only a bounded package manifest and exact
declared entry source under `ADR-0065`; it does not run the package, launcher, or Git.
Under `ADR-0106`, the client MCP adapter opens only the file whose layout declared a
key and reads only server names under that key. A declared path still belongs to an untrusted
machine, so the "declared file" boundary does not rest on its name: a symlink or a file
with a second hard link is never read, the descriptor is checked against the `lstat`
that resolved it, and the server count and name length are bounded. Names enter
`evidence_refs`, and an unbounded name would put arbitrary text there. Length, not the
character set, is bounded: `say "hi"` is a name someone chose, and rejecting it would
claim that the file declares no servers when it does.
External metadata ports under `SPEC-005` REQ-529 read only `nori.json` at an explicitly
named root and `.agents/.skill-lock.json` version 3 in project or global scope. They
refine an already discovered path or add a declared Nori component, but do not make an
external manifest a source of confirmed passport facts.

The supported set is Claude Code, Codex, Pi, OpenCode, Grok Build, Cursor, and
Antigravity. Shared `.agents/skills` belong to none of them and are returned with
`harness_id=null`. One physical path is not duplicated under multiple harnesses merely
because their formats are compatible.

The executable owner of the set is the declarative table shown by
`toolchain harness-capabilities`. Detector and discovery rules are built from it; the
`undefined` row owns only portable conventions without a single harness. Each row names
the support level, global and project layouts, projection capabilities, sources, and
known gaps.

## Bounded layout matrix

| Harness | Global | Project | Manifest-backed plugin |
|---|---|---|---|
| Claude Code | instruction, skill, agent, command, setting, MCP, plugin | instruction, skill, agent, command, setting, MCP, plugin | installed ledger/cache adapter; plugin root, skill, agent, command, hooks-directory, and MCP client config |
| Codex | instruction, command/prompt, setting, shared skill | instruction, setting, agent, hook, shared skill | plugin root, skill, and hooks-directory |
| Pi | instruction, skill, plugin, command, setting | skill, plugin, command, setting | no separate project-plugin manifest declared |
| OpenCode | skill, agent, command, plugin, setting | skill, agent, command, plugin, setting | bounded native plugin directory |
| Grok Build | skill, plugin, hook, setting, shared command | skill, plugin, hook, setting | bounded native plugin directory |
| Cursor | instruction, setting, plugin | instruction, plugin | plugin root, skill, agent, command, and rules-as-instruction; hook/MCP only if carried by the tree |
| Antigravity | setting, plugin, skill, agent, hook, MCP | plugin, skill, agent, hook, MCP | bounded native plugin directory |

An MCP server package belongs to no single harness and is shown separately with
`harness_id=null`. Python requires a consistent `pyproject.toml` → MCP SDK dependency →
`project.scripts` → exact module import chain. TypeScript requires a `package.json` →
SDK dependency → `bin`/script source → exact SDK import chain.

`unsupported` in this matrix does not become a filename heuristic. A new layout appears
only with an official source and fixture. Therefore an ordinary `src/hooks/useFoo.ts`,
business webhook, or arbitrary `plugins/` directory does not become a harness component.

A Claude Code project plugin pack is recognized like a Codex pack and differs by
manifest name. A directory under `plugins/` becomes a plugin only through exact
`.claude-plugin/plugin.json`; within a proven plugin, discovery reads `skills` (a
directory containing `SKILL.md`), `agents`, `commands`, `hooks/hooks.json`, and
`.mcp.json`.

A Cursor project plugin pack differs only by manifest name:
`plugins/<name>/.cursor-plugin/plugin.json`. Within a proven plugin, discovery reads
`skills`, `agents`, `commands`, and `rules` (each file is an instruction). The official
schema also names `hooks` and `mcpServers`; they are absent from the measured OpenNetwork
sample, and the walker does not invent these types from an adjacent directory. JSON
manifest values are not read—the file's existence proves that the directory is a plugin.

`.mcp.json` within a plugin is client config, not a server: the finding receives
`component_type=mcp` and `native_role=mcp_client_config`. Such a file proves itself by
name, so discovery does not open it, and no token, access-bearing URL, or `.env` body
enters the output. The layout is declared by observation, not conjecture: working servers
reside there, while `~/.claude.json`, `~/.claude/settings.json`, and
`~/.claude/.mcp.json` do not carry an MCP key.

Codex, OpenCode, and Grok Build keep client servers inside a file also declared as a
`setting`: for the first and third it is `config.toml`; for the second, `opencode.json`
or `opencode.jsonc`. Here file existence proves nothing—it exists on any machine where
the harness has run at least once, and an empty declaration means no servers. Therefore
such a layout declares a key, and the file becomes an `mcp` finding only when at least
one server is declared under that key. The `setting` finding remains: one file produces
two findings of different types.

Only server names are read, and they enter `evidence_refs`—for example,
`mcp_servers.github`. Values next to a name—command, arguments, URL, headers, and
environment—are neither read nor returned, so a token stored in a server entry reaches
neither a passport, log, nor fixture. A file that cannot be parsed in its format, exceeds
the size limit, or lacks the key produces no findings: guessing its content would be
the very heuristic this contract prohibits.

Pi has no declared client layout. Files named `mcp.json` occur under its root, but they
are created by user extensions rather than the harness itself, and observed instances
disagree on the key. The Pi documentation table of contents contains no MCP page, so the
machine table reports the verified gap `no_documented_mcp_client_config` rather than an
invented layout.

This is a separate layout, not a renaming of the global cache adapter. The adapter still
reads the installed ledger, while the pack is a marketplace source tree in which the
`.claude/` directory may be entirely absent.

A `plugins/` directory whose members carry no manifest from **any** supported harness
produces no components and reports `unsupported_manifest` once per collection. Silence
would be worse than failure: the operator would receive an empty inventory without a
reason. A pack for one harness does not trigger a complaint from another: a Codex pack
remains a pack even without a Claude manifest.

Codex project hooks are recognized only as `.codex/hooks.json` or as `hooks/hooks.json`
inside a plugin proven by exact `.codex-plugin/plugin.json`. A plugin hook-directory is
one component and includes the manifest and adjacent scripts in a deterministic artifact;
scripts are not run during discovery. Custom agents come only from `.codex/agents`.
CODEX.md is not a documented instruction layout and is returned as a safe
`unsupported_manifest` diagnostic suggesting `AGENTS.md`, not as a false native finding.

## Finding fields

- `candidate_id` — `sha256:` of a domain hash in `ai-stp:native-discovery:v1`; it
  addresses the discovery result but does not replace the adopted Component's logical
  identifier;
- `component_type` — a value from the closed eight-type vocabulary;
- `native_role` — `mcp_client_config` or `mcp_server` for MCP, otherwise `null`;
- `harness_id` — owner of the native layout, or `null` for a shared convention;
- `scope` — `global` or `project`;
- `source_path` — path with home replaced by `~`;
- `layout_source` — official document declaring the verified layout;
- `provenance` — consistent provenance: `filesystem/local` contains only layout
  evidence; `package/observed` contains only observed package identity without a remote
  claim; `github/exact` requires a canonical repository and full commit SHA and may
  contain a subpath and package name/version; an askill-compatible lock may add the
  exact folder's `digest` to `package/observed`, but that digest is not a Git commit;
- `byte_length` — regular file size, or `null` for a directory or unmeasurable entry;
- `holds_secret` — result of checking the name, not the content;
- `entry_points`, `transport_capabilities`, `evidence_refs` — only allowlisted
  structural facts from a manifest-led adapter; transport may be empty if it cannot be
  proven as `stdio` or `http`;
- `reason` — safe basis for classification or immeasurability.

Candidate identity is computed from the type, harness, scope, redacted path,
`layout_source`, and allowlisted provenance. Repeating discovery on an unchanged
filesystem returns the same values in the same order. Changing the official layout
source or exact source intentionally changes identity and requires agent reevaluation.

## GitHub provenance

Global Claude plugins are read through the supported chain of a version 2 ledger,
marketplace registry, and marketplace manifest. The install path is accepted only within
the computed plugin cache; the marketplace's recorded manifest path is ignored. A
relative source within a GitHub marketplace and GitHub-backed `github`, `url`, or
`git-subdir` with an exact revision are permitted. A credentialed URL, a path containing
`..`, an incomplete SHA, an unknown ledger version, and escape from the cache root fail
closed.

A problem in one source adapter does not remove independent findings. It appears in
`diagnostics` with a closed code and safe reason, without manifest content, credentials,
or system error text. The presence of `github/exact` does not mean platform verification
or plugin safety.

An installed plugin with npm, archive, local, or incomplete Git evidence does not
disappear: it is returned as `package/observed`. The agent may use this for inventory but
does not call its repository or revision exact.

Global Pi Git packages are discovered only in documented
`git/<host>/<owner>/<repository>` within the config root. For `github.com`, the adapter
reads bounded `HEAD`, loose ref, or `packed-refs`; it neither reads nor runs
`settings.json`, Git config, hooks, working files, or the network. Such a checkout
receives `github/exact`, but enabled state and working-tree cleanliness are not inferred.
A non-GitHub host remains without a GitHub claim.

Grok `plugins/marketplaces` is a service container, not a plugin, and is therefore not
returned as a candidate. The public Grok contract does not yet expose enough installation
registry structure for exact provenance of each marketplace plugin; the CLI shows only
provable local-layout elements and does not guess the source.

## External metadata ports

The Nori port accepts bounded UTF-8 JSON with unique keys and required `name` and
`version`. It maps only declared `skills`, `subagents`, and `slashcommands` to an
existing real path within the named root. Values in `repository`, dependencies, and
scripts neither create exact provenance nor execute.

The skill-lock port accepts only version 3 and an existing
`.agents/skills/<sanitized-name>`. `skillFolderHash` is retained as `sha1:` or `sha256:`
in observed provenance; `source`, `sourceType`, and `sourceUrl` do not prove a repository
or commit. The adopted draft retains a reference to the lock, folder digest, and a
separate content digest of the bytes actually read. Passport validation therefore keeps
reporting missing exact public source until explicit owner enrichment.

Both manifests are limited to 1 MiB and 500 entries, are not read through a symlink,
reject duplicate JSON keys, and run no external commands, scripts, Git, or package
manager. A failure in one port returns a safe diagnostic and does not remove independent
findings.

## Roots

The config root comes from the same detector table as `harness survey`. A documented
relocation variable completely replaces the original root. A shared home layout is
permitted only by a rule without `harness_id`; an unknown root or a rule without a source
makes the `component_layouts` doctor check unsuccessful.

## Agent action

The agent groups findings by scope and harness, shows `layout_source` when classification
is uncertain, shows diagnostics separately, and retains `candidate_id` while discussing
selection. The agent calls GitHub origin exact only when `provenance.kind=github` and
`state=exact`; a cache-directory name is not evidence.
Discovery is not consent. Before `component adopt`, the agent must obtain the user's
decision and pass the exact `source_path` together with the correct project root for a
project finding.

`component adopt` accepts only what discovery already named: a path absent from the
finding is rejected. A directory must additionally carry a manifest from the closed set—
`SKILL.md`, `AGENTS.md`, `plugin.json`, `.claude-plugin/plugin.json`,
`.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `hooks.json`, `package.json`,
or `pyproject.toml`. A directory without such a file is rejected: adoption cannot
distinguish a component from an arbitrary tree, and guessing from content would mean
adopting someone else's content.

A single file in a directory-shaped layout needs no manifest—it is the component. This
is how claude-code agents and commands are authored, and adoption accepts them.

The `component-scaffold/6` scaffold stores authoring metadata next to editable
`source/` and, for a concrete harness, the generated layout under
`projections/<harness>/`. `discover`/`adopt` transfers that concrete projection;
a portable scaffold transfers `source/`. Historical `/2` trees still use `native/`,
and `/3`, `/4`, and `/5` remain immutable historical wrapper identities.
Single-file OpenCode/Pi JS/TS plugins are adopted as files;
manifest-directory plugins only through a manifest from the closed set above.

## External source identity

`component source parse` accepts a published slug, GitHub shorthand or HTTPS URL, local
path, and collection URL and returns only structured intent. This result is not
provenance evidence and always contains `provenance_proven=false`. The command accesses
neither the network, Git, manifest, nor registry.

`component source resolve` is a separate mechanical boundary: only GitHub intent with a
full lowercase commit SHA becomes `github/exact`. A branch, tag, short SHA, credentialed
URL, control characters, and an absolute subpath or one escaping through `..` fail
closed. Even exact identity does not yet prove content digest and size; those facts come
from the subsequent bounded import/adopt path.
