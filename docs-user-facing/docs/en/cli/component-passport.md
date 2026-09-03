---
title: "Component passport"
description: "Show, suggest, update, validate, and quality-check a local component passport."
---

# Component passport

A component passport is the local, versioned description of one adopted
object. These commands show the current draft, suggest facts you can
confirm, write a new revision, and report whether the head is structurally
ready to publish.

They do not publish. They do not change `author_verified` or
`component_verified`. Quality hints are optional and mechanical. The
developer and device passports are a different group: [Passports](passport.md).

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp component passport show` | `read` | `none` | show the current local passport draft |
| `ai-stp component passport suggest` | `read` | `none` | suggest exact manifest facts without changing the draft |
| `ai-stp component passport update` | `apply` | `plan_digest` | add confirmed facts as a new content-addressed revision |
| `ai-stp component passport validate` | `read` | `none` | report every structural blocker to publishing this revision |
| `ai-stp component passport quality` | `read` | `none` | optional authoring hints; no trust or readiness change |

`--json` is global. Always pass it.

## Show

```bash
ai-stp component passport show --id <stable_id> --json
```

`--id` is the stable identifier of an adopted component.

The answer is a passport view: `stable_id`, `kind`, `revision_id`,
`parent_revision_ids`, `owner_id`, `created_at`, `facts`, `schema_version`.
`kind` is `component`. `revision_id` is the head you must name if you patch.

## Suggest

Suggest reads the adopted bytes and proposes closed-schema facts. It writes
nothing. Unresolved fields stay unresolved until you confirm them through
`update`.

```bash
ai-stp component passport suggest --id <stable_id> --json
```

Success fields: `stable_id`, `revision_id`, `suggestions`,
`unresolved_fields`, `schema_version`. Each suggestion has `field`, `value`,
and `source_refs`. Copy only facts you have reviewed into the patch file.

## Update

Update applies a bounded closed-schema JSON patch as a child of the current
head. The confirmation token is `--expected-revision`, the exact
`revision_id` `show` returned. There is no `--confirm` and no
`--expected-plan-digest`.

```bash
ai-stp component passport update \
  --id <stable_id> \
  --expected-revision <revision_id> \
  --from ./passport-patch.json \
  --json
```

`--from` is a path to the patch. Secrets, `.env` bodies, tokens, and
absolute personal paths do not belong in that file.

The answer is a new passport view. `revision_id` changed. The previous head
is in `parent_revision_ids`. A second call with the old `--expected-revision`
is refused: the head moved.

## Validate

Validate reports every structural blocker to publishing the current
revision. It is a local verdict, not permission to write to the cloud.
Publication still needs its own authenticated plan.

```bash
ai-stp component passport validate --id <stable_id> --json
ai-stp component passport validate --id <stable_id> --for-publication --json
```

`--for-publication` selects the public-publication readiness profile. That
profile is the one this command already applies. The flag is accepted so an
older caller's spelling still parses.

Success fields: `stable_id`, `revision_id`, `ready`, `missing_fields`,
`invalid_fields`, `for_publication`, `schema_version`. `ready: false` is a
successful report of blockers, not a crashed command. Fix the draft with
`update`, then validate again.

## Quality

Quality shows optional mechanical authoring hints. It does not change the
draft, trust, or publication readiness. `affects_component_verified` is
`false`.

```bash
ai-stp component passport quality --id <stable_id> --json
```

Treat the dimensions as hints. Do not skip `validate` because quality looked
green. Do not treat quality as a platform safety scan; that happens at
publication.

## Happy path

```text
component adopt --path <exact>
→ component passport show --id <stable_id>
→ component passport suggest --id <stable_id>
→ review suggestions; write a patch
→ component passport update --id <stable_id> --expected-revision <rev> --from <patch>
→ component passport validate --id <stable_id>
→ component version release --id <stable_id>
```

Show the envelope after every write. The next `update` must name the new
`revision_id`.

## Named success fields

| Command | Fields to read |
| --- | --- |
| `show` / `update` | `stable_id`, `revision_id`, `kind`, `facts`, `parent_revision_ids` |
| `suggest` | `revision_id`, `suggestions`, `unresolved_fields` |
| `validate` | `ready`, `missing_fields`, `invalid_fields`, `revision_id` |
| `quality` | dimension statuses and checks; `affects_component_verified` |

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | `--id`, `--expected-revision`, or `--from` is missing or the patch is not closed-schema | correct the request; do not send a free-form JSON object |
| `AI_STP_NOT_FOUND` | that id is not an adopted component | `component find` or `component discover` |
| `AI_STP_CONFLICT` / `AI_STP_PRECONDITION_FAILED` | `--expected-revision` is no longer the head | `passport show`, rebuild the patch, update again |
| `AI_STP_PLAN_STALE` | the patch was prepared against bytes that moved | same as conflict: show, then a new patch |
| `ready: false` | structural blockers remain | read `missing_fields` and `invalid_fields`; `update`; validate again |
| secrets in the patch | passports must not hold credentials | remove them; store secrets outside the passport |
| `--confirm` rejected | that flag is not declared on these commands | confirm update with `--expected-revision` only |

`validate` returning `ready: false` is not `ok: false`. The envelope is still
a success. The blockers are data.

## Related links

- [Component commands](component.md)
- [Discover and adopt](component-discover.md)
- [Component source](component-source.md)
- [Publish a component](component-publish.md)
- [Passports](passport.md)
- [Publishing](../publishing/index.md)
- [Trust and safety](../trust-and-safety/index.md)
- [Security checks](../security-checks.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups passport commands so a person can find them. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and
the CLI disagree, follow the CLI.
