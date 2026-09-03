---
description: "SPEC-041: Versioned scaffold plans for a component's complete authoring catalog."
last_verified: "2026-09-03"
---

# SPEC-041: Component scaffold framework

## Purpose

An author or agent receives a deterministic component or setup scaffold that
can be validated, registered locally, and then enriched with precise
provenance for publication. Creation is separated from preview by an exact
plan/confirm boundary and never overwrites an existing path.

## Scope

The framework creates a local authoring catalog and a private passport patch.
It does not register the object, invent a public source, license, or
authorization, invoke a package manager, execute generated code, compose a
setup into SQLite, export a harness tree, or write a provider target.
`ADR-0142` records the architecture boundary between authoring git, native
projections, compose, and install.

## Terms

- **Descriptor** — a private selection of the template/generator version, type,
  language, and harness variant.
- **Scaffold plan** — a content-addressed preview of all files to be created.
- **Scaffold apply** — confirmed creation of a new catalog from the exact plan.
- **Source tree** — `source/`, the canonical authoring files the owner edits.
- **Projection tree** — `projections/<harness>/`, the native layout for one
  concrete harness. Absent when the variant is `portable`.
- **Setup scaffold** — a physical authoring directory for one harness-bound
  setup, distinct from `setup compose` and from provider install.

## Requirements

- `REQ-4101`: The descriptor pins the template and generator versions, one of
  the eight component types, the language, a portable or specific harness
  variant, and the executability flag.
- `REQ-4102`: The matrix permits `none` for the declarative `instruction`,
  `skill`, `command`, `agent`, and `setting` types; `mcp` and `plugin` use one of
  the executable languages, while `hook` uses only a language whose source can
  be run after installation without an implicit build. A combination without
  native semantics in the selected harness is rejected before any files are
  written. That refusal includes portable `setting` (a setting is a harness
  file), Claude Code `mcp` (no provider-owned MCP surface in the target),
  Grok `command`, Pi `agent` and `hook`, OpenCode `hook`, Codex `plugin`, and
  Cursor `agent` at global scope. A Codex `agent` is a TOML file and is
  accepted. OpenCode and Pi `plugin` require JavaScript or TypeScript.
- `REQ-4103`: The plan lists every relative path, exact byte length, mode, and
  domain-separated digest and binds them to an absolute new target. The plan
  does not list `.git` or any git object.
- `REQ-4104`: The component scaffold contains the descriptor, private component
  passport patch, `SetupEvalProfile`, consumer README, `.gitignore`, and a
  type-specific `source/` tree. A concrete harness variant also contains
  `projections/<harness>/` with that harness's native layout. The scaffold
  does not contain native/, authoring-template.md, SAFETY.md, or
  PUBLICATION.md. The mustache authoring template remains available through
  `component template render` (SPEC-005 REQ-528) and is not the canonical
  native layout.
- `REQ-4105`: The passport patch uses the slug as `name`, omits invented
  descriptions and closed-vocabulary tags, declares empty minimal permissions
  and capabilities, and faithfully retains `NOASSERTION` / the prohibition on
  distribution until the author decides. A `skill` description is the same
  string as the `SKILL.md` YAML `description`. A portable descriptor is not
  misrepresented as a passport for a specific harness. Draft body text uses
  the marker `TODO(ai-stp-scaffold):`. Safety declarations belong in the
  passport, not a sibling markdown file.
- `REQ-4106`: Apply rebuilds the plan from the same explicit inputs, requires its
  exact digest and `--confirm`, creates owner-only files, rolls back its own
  incomplete result, and fails closed for an existing target, a symlink, or a
  missing parent.
- `REQ-4107`: The eval skeleton contains a local deterministic check, while
  unavailable model/human checks receive `not_run` when executed under
  `SPEC-040`; the scaffold itself does not execute code.
- `REQ-4108`: `source/` holds the canonical type-specific files.
  `projections/<harness>/` holds the exact native layout for the selected
  harness from the projection registry. `instruction` canon is `AGENTS.md`;
  Claude Code receives `CLAUDE.md`, Cursor receives `rules/<name>.mdc`, and
  Antigravity receives `config/rules`. `command` is Markdown with a
  `description`; Codex and Pi project to `prompts/`. `agent` is Markdown with
  `name` and `description`, or Codex TOML with `name`, `description`, and
  `developer_instructions`. `setting` is the harness-native settings file; an
  entire settings file is one component. A Codex `agent` is not converted into
  another type.
- `REQ-4109`: `source/hook.json` strictly pins the event, order, blocking
  failure policy, and handler command. The native manifest and adjacent
  handler are derived deterministically into `source/` and, when a harness is
  selected, `projections/<harness>/`. Claude Code projects the `hooks` key
  inside `settings.json`. The scaffold does not create a `handle_event` stub.
- `REQ-4110`: A manifest-directory plugin carries the selected product's native
  manifest and a `skills/` note, not an invented program entry. An OpenCode
  plugin is a single `plugins/<name>.js|ts` file, while a Pi extension is a
  single JS/TS package entry. Marketplace registration is not part of the
  plugin package and is modeled as a separate `setting`.
- `REQ-4111`: After the planned files exist, apply initializes a git repository
  in the destination when that destination is not already inside a worktree,
  then stages every planned path and creates one commit `Initial ai-stp
  scaffold` using the user's configured `user.name` and `user.email` without
  passing `--author`. Missing identity leaves the tree and the init, skips the
  commit, and reports `missing_identity`. An existing worktree skips init and
  reports `existing_worktree`. Unavailable git skips init and reports
  `git_unavailable`. The result names `git_initialized`, `git_commit`, and
  `git_reason`. Git failure after a successful write does not delete the tree.
  Remote creation and push are out of scope.
- `REQ-4112`: `setup scaffold plan` and `setup scaffold apply` create a new
  directory for one concrete harness: consumer README, draft `setup.json` in
  this repository's compose-manifest shape, draft `setup-passport.json` that
  is not a frozen SetupVersion, eval profile, descriptor, `.gitignore`,
  optional `components/<member>/` using the component wrapper, and
  `projections/<harness>/` left empty pending a later export command. Portable
  setup is rejected. A member the harness cannot route is rejected at plan.
  Optional `--components` accepts `type:name` for declarative kinds and
  `type:name:language` for executable kinds. `setup compose` remains the
  SQLite freeze; compose is not install; scaffold is not export.
- `REQ-4113`: A project has one git root. Nested component directories created
  by setup scaffold do not receive a nested `.git`. Independent component
  apply still initializes git when the destination is not inside a worktree.

## States and errors

A plan is not a persisted mutable object: identical inputs and an available
target produce identical bytes and digest. An invalid matrix combination, stale
plan, modified bytes, or an occupied or unsafe target results in a typed failure
before any user-owned files are modified. Git identity and worktree state are
reported on the apply result and do not change the plan digest.

## Security and privacy

The scaffold does not read environment values, credentials, or user files other
than git identity configuration already present for commits. It does not access
the network or execute created code. The patch contains only an empty
`required_env` list; subsequent enrichment accepts variable names but not their
values. Cleanup of a failed write removes only files and catalogs created by
the current apply.

## Compatibility and migration

`component-scaffold/3` and `ai-stp/3` are the current independent versions of
the component template and generator; versions `1` and `2` remain validatable.
`setup-scaffold/1` and generator `ai-stp/1` are the first setup-scaffold
versions. A change to the exact generated bytes requires a new template
version; a change to the mechanics without changing the descriptor contract
requires a new generator version. Older descriptors remain validatable against
their own schema.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-4101` | The strict schema rejects unknown fields and values outside the closed vocabularies. |
| `REQ-4102` | A parameterized test covers the entire type × language × variant matrix and negative combinations, including portable setting and Claude Code mcp. |
| `REQ-4103` | A repeated preview matches, every digest is recomputed from the actual bytes, and no planned path is under `.git`. |
| `REQ-4104` | For every matrix row, the passport and eval profile pass their respective schemas, `source/` is present, `native/` is absent, and `projections/<harness>/` is present exactly when the variant is a concrete harness. |
| `REQ-4105` | Fixtures contain no secret values, public source claims, invented tags, or permission to distribute; skill passport description matches SKILL.md YAML. |
| `REQ-4106` | Without confirm, with a stale digest, an existing target, a symlink, or a missing parent, the operation is rejected without modifying files. |
| `REQ-4107` | The eval profile contains deterministic and model-assisted checks; the shared runner confirms an accurate `not_run`. |
| `REQ-4108` | Fixtures for native instruction/command/agent/setting components match the registry; a Codex agent is TOML; an unsupported pair is rejected without writing files. |
| `REQ-4109` | Hook fixtures preserve the event, order, failure policy, and command in `source/hook.json`; malformed source is rejected by the strict schema. |
| `REQ-4110` | Fixtures distinguish manifest packages from single OpenCode/Pi modules; the plugin does not write marketplace settings or an `activate_plugin` stub. |
| `REQ-4111` | Apply outside a worktree initializes git; apply inside a worktree does not; missing identity skips the commit and names the reason; the plan digest is unchanged by git. |
| `REQ-4112` | Setup scaffold without a harness is rejected; a member the harness cannot route is rejected; apply writes the wrapper and nested component trees without composing or installing. |
| `REQ-4113` | Nested members have no `.git`; an independent component apply in an empty parent does. |
