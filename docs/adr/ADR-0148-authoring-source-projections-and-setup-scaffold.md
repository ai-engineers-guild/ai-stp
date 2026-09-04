---
description: "Decision to scaffold components as source/ plus projections/<harness>/, initialize git as an apply side-effect, and add a physical setup authoring tree distinct from compose and install."
last_verified: "2026-09-03"
---

# ADR-0148: Authoring trees are source and projections, and a setup is its own git project

Status: accepted.

## Context

`component scaffold` currently emits the same seven wrapper files for every
kind, plus an ambiguous `native/` tree. Issue #79 asked for type-specific
trees that match community layouts, `source/` versus `projections/<harness>/`
instead of `native/`, `AGENTS.md` as the instruction canon with `CLAUDE.md` as
a Claude projection, rejection of placeholders, and failure at plan when a
type has no native surface. Setup authoring today is only a compose manifest
into SQLite: there is no physical setup directory, which the same issue named.

NDDev-OpenNetwork setup systems show a second gap. A harness-native tree,
a compose graph, and a provider install are three different objects. Collapsing
them into `native/` plus `setup compose` taught authors that a scaffold was
already a target, and that recording a setup was installing one.

Git was also missing. An authoring directory that is not a repository cannot
pin the exact commit publication requires, and nesting a component `.git`
inside a setup repository would create a second root the later export path
cannot own.

## Options

**Keep `native/` and add files around it.** Cheapest. Leaves the ambiguous
directory the issue rejected, still emits SAFETY.md / PUBLICATION.md /
authoring-template.md as if they were the product, and still has no setup
tree.

**Generate OpenNetwork `setup.json` (`id` + `sources[]`) as the setup
scaffold.** Wrong product: that file is a provider posture document. This
repository's compose manifest is `name`, `harness_id`, and `components[]`.
Two JSON files that share a name and not a schema would recreate the
`native/` confusion one level up.

**Put git in the plan digest.** The `.git` directory is not deterministic
across machines (hooks, default branch, identity). Hashing it would make
every plan unique per host and break the plan/apply digest boundary.

**Scaffold `source/` + `projections/<harness>/`, keep the mustache renderer
as a separate command, add `setup scaffold` as a physical tree, and run
`git init` only as an apply side-effect.** Costs a template version bump
and a new command pair. Matches the eight-kind layouts, keeps compose as
SQLite, and keeps install as a public provider write.

## Decision

1. **Component wrapper.** `component-scaffold/4` writes `README.md`,
   `component-passport.json`, `eval-profile.json`, `.ai-stp-template.json`,
   `.gitignore`, `source/`, and, when the variant is a concrete harness,
   `projections/<harness>/`. It does not write `native/`,
   authoring-template.md, SAFETY.md, or PUBLICATION.md. Executable MCP and
   hook scaffolds contain runnable stdlib-based examples for Python,
   TypeScript, JavaScript, Go, and Rust; `fastmcp` is an optional Python MCP
   framework selected explicitly in the descriptor.
   `component template render` and `scaffold()` remain for SPEC-005 REQ-528.

2. **Canon versus projection.** `source/` is what the author edits.
   `projections/<harness>/` is the native layout for one harness. Portable
   variants have no `projections/` directory. Discover and adopt transfer
   `source/` when portable and `projections/<harness>/` when a harness was
   selected, not the whole authoring tree.

3. **Kind-specific native forms** follow the projection registry in
   `composition.py`, including ADR-0129 contributions into an owned file.
   Unsupported type/harness pairs fail at plan, including portable `setting`
   (a setting is a harness file) and Claude Code `mcp` (no provider-owned
   MCP surface). A Codex `agent` is a TOML file under `agents/` and is
   accepted. Plugin scaffolds emit `plugin.json` and a `skills/` note, not
   an `activate_plugin` stub; OpenCode and Pi still receive a single JS/TS
   module. Marketplace registration remains a `setting`, not a `plugin`.

4. **README and passport.** README is the consumer document: what the draft
   is, what is canon, what to replace, and the publication checklist. Safety
   lives in the passport. The draft passport uses the slug as `name`, omits
   invented descriptions and tags, keeps `NOASSERTION` with
   `redistribution_allowed: false`, and for `skill` copies the `SKILL.md`
   YAML `description`. Draft text uses the marker `TODO(ai-stp-scaffold):`.

5. **Git is a setup-apply side-effect.** After the planned setup files exist,
   setup apply runs `git init` when the destination is not already inside a worktree,
   writes `.gitignore` (OS junk, bytecode, `.env`; never the passport,
   `source/`, README, or `setup.json`), then `git add -A` and one commit
   `Initial ai-stp scaffold` using the user's git identity. It does not pass
   `--author`. Missing identity leaves the files and the init, skips the
   commit, and reports `missing_identity`. An existing worktree skips init
   and reports `existing_worktree`. Git is absent from the plan digest.
   Remote and push are not scaffold's job. The destination must still not
   exist (REQ-4106).

6. **Setup scaffold.** `setup scaffold plan` / `apply` create a physical
   authoring directory: README, `setup.json` (this repository's compose
   manifest shape, allowed to be an incomplete draft), `setup-passport.json`
   (a draft graph, not a frozen SetupVersion), eval profile, descriptor,
   `.gitignore`, optional `components/<member>/` using the component wrapper
   without a nested `.git`, and `projections/<harness>/` left empty until a
   later export command. A setup requires a concrete harness. Optional
   `--components type:name` (and `type:name:language[:framework]` for executable kinds)
   nests members the harness can route. `setup compose` remains SQLite.
   Compose is not install. Export is not scaffold.

7. **One git root per project.** A component inside a setup is not its own
   repository. Independent `component scaffold apply` outside any worktree
   still initializes git.

## Consequences

- Template version `component-scaffold/4` and generator `ai-stp/4` are
  current for components. `setup-scaffold/1` is the first setup template.
  Versions `1` and `2` remain validatable against their schemas.
- `SetupScaffoldResult` reports the git initialization outcome; component
  scaffolds remain ordinary trees and do not create a nested repository.
- User documentation, evidence slices, and discover/adopt copy paths that
  named `native/` move to `source/` or `projections/<harness>/`.
- Tests must ignore `.git` when asserting owner-only file modes.
- Rollback of a failed apply still removes only files and directories the
  current apply created; a later git failure does not delete a successful
  tree.

## Revisit conditions

- A public provider grows a Claude Code user-scope MCP surface that it owns
  inside the target, which would retire the Claude `mcp` refusal.
- `setup export` ships, at which point empty `projections/<harness>/` in a
  setup scaffold must start receiving bytes from that command, not from
  scaffold.
- Git identity or default-branch policy becomes a machine contract rather
  than a side-effect report.
