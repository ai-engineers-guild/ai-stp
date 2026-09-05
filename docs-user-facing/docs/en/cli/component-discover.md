---
title: "Discover and adopt"
description: "Find native components, scaffold them, and register a discovery."
---

# Discover and adopt

These commands look at files this machine already has, or create a new
authoring directory. They do not publish, install, or write harness state.

Discovery reports paths without opening secret-named files to learn their
contents. Adopting a path is an explicit act: it registers one discovered
component in the local registry. Forgetting it marks the record deleted and
keeps history.

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp component discover` | `read` | `none` | list native components in harness roots and one project |
| `ai-stp component find` | `read` | `none` | search the local registry by prefix, phrase, tag, or field |
| `ai-stp component scaffold plan` | `plan` | `none` | preview exact files and digests for one versioned scaffold |
| `ai-stp component scaffold apply` | `apply` | `plan_digest` | create exactly the confirmed scaffold; never overwrite a path |
| `ai-stp component template render` | `read` | `none` | render and validate a portable template for one harness |
| `ai-stp component adopt` | `apply` | `none` | register one discovered component in the local registry |
| `ai-stp component forget` | `apply` | `none` | mark a registered component deleted, keeping its history |

`--json` is global. Always pass it.

## Discover

`discover` scans harness roots and, if you name `--root`, one project. It
changes nothing. A secret-looking path is flagged from the **name**, not from
opening the file.

```bash
ai-stp component discover --json
ai-stp component discover --root . --json
```

Success fields include `components`, `diagnostics`, `project`, and
`schema_version`. Each component carries `candidate_id`, `component_type`,
`layout_source`, `native_role`, `path`, `harness_id`, `holds_secret`,
`byte_length`, `entry_points`, and `evidence_refs`.

An empty `components` list is typed emptiness, not a failure. It does not
silently run `device init` or adopt anything.

## Find

`find` searches objects already in the local registry. It uses no model and
no network. Unverified hits stay hidden unless you pass
`--include-unverified` for this call only. That flag is never stored.

```bash
ai-stp component find --prefix demo --json
ai-stp component find --phrase "playwright" --tag mcp --json
ai-stp component find --field kind --value skill --include-unverified --json
```

`--tag` is repeatable: every named tag must match. `--field` and `--value`
together match one declared field exactly.

Success fields include `hits` (each with `stable_id`, `lane`, and `fields`)
and `schema_version`.

## Scaffold plan, then apply

A scaffold is a new authoring directory. Plan first. Apply creates exactly
the files the plan named, and refuses to overwrite a path that already
exists.

`--type` is one of `instruction`, `skill`, `mcp`, `hook`, `command`,
`agent`, `plugin`, `setting`, `cli`. `--language` is `none` for declarative types,
or one of `python`, `typescript`, `javascript`, `rust`, `go`,
`dart-flutter`. `--harness` is `portable` or one concrete harness:
`claude-code`, `codex`, `pi`, `opencode`, `grok-build`, `cursor`,
`antigravity`. `--name` is a lowercase slug. `--output` is the new
directory.

```bash
ai-stp component scaffold plan \
  --type skill \
  --language python \
  --harness portable \
  --name demo-skill \
  --output ./components/demo-skill \
  --json
```

The plan answer carries `plan_id`, `plan_digest`, `output`,
`component_name`, `descriptor`, and `files`. Each file has `path`, `digest`,
and `byte_length`. `publication_ready` is `false`. The scaffold still needs
an exact source before publication.

Apply repeats the same options and adds `--expected-plan-digest` of the
unchanged plan. There is no `--confirm`. The digest says **which** scaffold.

```bash
ai-stp component scaffold apply \
  --type skill \
  --language python \
  --harness portable \
  --name demo-skill \
  --output ./components/demo-skill \
  --expected-plan-digest sha256:... \
  --json
```

The apply answer carries `plan_id`, `plan_digest`, `output`, and `created`.
If the directory already exists, the command refuses. If the digest no
longer matches the recomputed plan, the command refuses as stale.

## Template render

Render a portable UTF-8 template for one concrete harness. This is a read:
it validates the rendering. It does not write the native files.

```bash
ai-stp component template render \
  --template ./templates/skill.md \
  --harness codex \
  --name demo-skill \
  --component-root components/demo-skill \
  --json
```

`--harness` here is a closed-registry harness, not `portable`.
`--component-root` is a bounded relative POSIX path.

## Adopt

Adoption writes a passport and stores bytes. Naming `--path` with the exact
path discovery reported **is** the decision. There is no `--confirm`.

```bash
ai-stp component adopt --path <exact-path> --json
ai-stp component adopt --path <exact-path> --root . --json
```

If the same path answers to more than one harness, name `--harness`. Use
`portable` for the shared cross-product claim. If it answers to more than
one kind, name `--kind`.

The answer is a passport view: `stable_id`, `kind`, `revision_id`,
`parent_revision_ids`, `owner_id`, `created_at`, `facts`, `schema_version`.

## Forget

Forget marks the component deleted in the local registry and keeps history.
It does not delete managed bytes on a harness target.

```bash
ai-stp component forget --id <stable_id> --reason "replaced by catalog pin" --json
```

`--reason` is optional. The answer is the same passport view shape as adopt.

## Happy path

```text
component discover --root .
→ component adopt --path <exact>
→ component passport show --id <stable_id>
```

Or, for a new component:

```text
component scaffold plan → scaffold apply --expected-plan-digest
→ component adopt --path <output>
→ component passport validate --id <stable_id>
```

## Named success fields

| Command | Fields to read |
| --- | --- |
| `discover` | `components`, `diagnostics`, `project` |
| `find` | `hits`, each hit's `stable_id` and `lane` |
| `scaffold plan` | `plan_id`, `plan_digest`, `files` |
| `scaffold apply` | `plan_digest`, `output`, `created` |
| `template render` | the rendered template payload |
| `adopt` / `forget` | `stable_id`, `revision_id`, `kind`, `facts` |

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | a required option is missing or not in the closed vocabulary | read the descriptor; do not invent a type or harness |
| `AI_STP_NOT_FOUND` | discovery did not report that path, or the id is unknown | run `discover` or `find` again |
| `AI_STP_USER_DECISION_REQUIRED` | the path is claimed by more than one harness or kind | pass `--harness` and/or `--kind` |
| `AI_STP_PLAN_STALE` | scaffold bytes no longer match `--expected-plan-digest` | plan again, show the files, apply with the new digest |
| `AI_STP_CONFLICT` | apply would overwrite an existing path | choose a new `--output` |
| empty `components` | nothing native was found | that is success; do not adopt a guessed path |
| `--include-unverified` forgotten | unverified local objects stay hidden | pass the flag for this call only, or leave them hidden |

Do not pass `--confirm` to adopt, forget, or scaffold apply. Those flags are
not declared. Scaffold apply is confirmed by `--expected-plan-digest`.

## Related links

- [Component commands](component.md)
- [Component passport](component-passport.md)
- [Component source](component-source.md)
- [Publish a component](component-publish.md)
- [Components](../components/index.md)
- [Project](project.md)
- [Registry](registry.md)
- [Consent](consent.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups discovery commands so a person can find them. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and
the CLI disagree, follow the CLI.
