---
title: Publishing and authoring
description: "Prepare repository-backed components and setups for publication."
---

# Authoring a component or a setup

Authoring is local, digest-bound work: scaffold a tree, fill only confirmed
facts, pin an exact public GitHub commit, validate the passport, release an
`X.Y`, then follow [Publishing](index.md). Secrets, private paths, caches,
and generated output must never enter a passport.

A published version is immutable `X.Y`, not SemVer. Changing bytes means a
new version.

## Scaffold

Preview every file and digest, then apply the same inputs with the exact
plan digest. The destination must not already exist.

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

`--type` is one of the eight kinds. Declarative kinds (`instruction`,
`skill`, `command`, `agent`, `setting`) take `--language none`. Executable
`mcp` and `plugin` take `python`, `typescript`, `javascript`, `rust`, `go`,
or `dart-flutter`. `hook` does not accept Rust or Go: the provider does not
perform a hidden source build.

`--harness` is `portable` or one concrete harness. If that harness has no
independent native form for the type, the plan fails closed before any write.
`setting` requires a concrete harness. Apply initializes git when the
destination is not already inside a worktree; git is not part of the plan
digest.

The `component-scaffold/3` directory contains:

```text
playwright-checks/
├── .ai-stp-template.json
├── .gitignore
├── README.md
├── component-passport.json
├── eval-profile.json
├── source/                  # canon; portable adopt transfers this
└── projections/<harness>/   # only when --harness is concrete
```

A hook also gets `source/hook.json` (event, order, blocking failure, handler)
and a projected native manifest. Manifest-directory plugins get a product
manifest and a `skills/` note, not an `activate_plugin` stub. OpenCode and Pi
plugins are a single JS/TS module, not an invented manifest. A setting
requires a concrete harness.

`discover` / `adopt` transfer `source/` when portable and
`projections/<harness>/` when a harness was selected, not the whole
authoring directory.

`setup scaffold plan` / `apply` create a physical setup directory for one
concrete harness: draft `setup.json`, draft `setup-passport.json`, optional
nested `components/<member>/` sharing one git root, and empty
`projections/<harness>/` until a later export. `setup compose` still records
SQLite. Compose is not install.

## Passport

The scaffold passport is a local patch: no invented source, no secrets, no
permission to redistribute (`NOASSERTION` until you review a license).

```bash
ai-stp component discover --root . --json
ai-stp component adopt --path <source_path> --json
ai-stp component passport show --id <stable_id> --json
ai-stp component passport suggest --id <stable_id> --json
ai-stp component passport update --id <stable_id> --expected-revision <rev> --from <patch.json> --json
ai-stp component passport validate --id <stable_id> --json
ai-stp component passport quality --id <stable_id> --json
```

`validate` lists every structural blocker to publishing. `quality` is optional
authoring hints; it does not change trust or readiness.

For `required_env`, record names and purposes, never values.

## Exact GitHub commit

`component source parse` is untrusted intent. Only a full lowercase commit
SHA becomes `github/exact`.

```bash
ai-stp component source parse --source https://github.com/example/repo --json
ai-stp component source resolve --source https://github.com/example/repo --commit <40-char-sha> --json
```

A branch, tag, short SHA, credentialed URL, control characters, an absolute
subpath, or a `..` escape fail closed. Exact identity still does not prove
content digest; that comes from the later import/adopt path.

Refresh archived GitHub evidence only after the version exists locally:

```bash
ai-stp component source evidence show --id <stable_id> --version 1.0 --json
ai-stp component source evidence refresh --id <stable_id> --version 1.0 --json
```

## No secrets

Do not put tokens, passwords, private keys, OAuth refresh tokens, or `.env`
bodies in:

- the passport;
- `source/` or `projections/<harness>/` files that will be published;
- logs, fixtures, or README examples with live values.

If the harness needs a credential, the passport may say that a named
variable is required. The value lives in the operating system's secret store
or the environment the operator already uses — never in the artifact.

`setting` is not a hiding place for secrets. See
[`setting`](../components/setting.md).

## Skill-specific check

Of the eight kinds, only `skill` has an independent specification. Validate
the **package** (the directory with `SKILL.md` at its root), not the whole
authoring tree:

```bash
ai-stp component skill validate --path ./playwright-checks/native --json
```

That command is not [`ai-stp skill install`](../cli/skill.md). The latter
installs the CLI's own Agent Skill.

## From a native tree you already have

If the component already lives in a harness layout:

```bash
ai-stp component discover --root . --json
ai-stp component adopt --path <exact source_path from the finding> --json
```

Adoption accepts only a path discovery already named. A directory must carry
a closed-set manifest (`SKILL.md`, `AGENTS.md`, `plugin.json`,
`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`,
`.cursor-plugin/plugin.json`, `hooks.json`, `package.json`, or
`pyproject.toml`). A directory without one is refused.

## Setups

Compose a setup from catalog pins and embedded sources, then release and
publish the graph as a set. The JSON manifest and update path are on
[Setups](../setups/index.md). The confirm path is on
[Publishing](index.md).

## Product articles are not a user CMS

Help-center product articles, changelog notes, and release notes live in
the repository under `docs-user-facing/content/` as Git-native Markdown, one
file per locale, with matching `type` and `slug`. They are not a CMS an
account can edit from the website, and they are not how a component or a
setup is published. Component and setup publication is the CLI path above.
