---
title: "Eval"
description: "Bind a reference evaluation profile to a local setup and run it."
---

# Eval

Eval binds a versioned reference evaluation profile to one exact local
setup graph and runs local deterministic checks. It does not install, does
not publish, and does not call a model API.

The profile is the same for every caller. The plan pins the setup, the
harness, the provider, and the runner. The run is confirmed by the plan
digest. Status and show read immutable local evidence. Repeat `eval show`
of the same `run_id` returns the same bytes.

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp eval profile` | `read` | `none` | show the versioned reference profile for all or one component type |
| `ai-stp eval plan` | `plan` | `none` | bind that profile to one exact local setup graph |
| `ai-stp eval run` | `apply` | `plan_digest` | run local deterministic checks for one confirmed exact plan |
| `ai-stp eval status` | `read` | `none` | read the immutable status of one local evaluation run |
| `ai-stp eval show` | `read` | `none` | show full immutable local evidence for one evaluation run |

`--json` is global. Always pass it. `eval run` requires
`--expected-plan-digest`. There is no `--confirm`.

## Profile

```bash
ai-stp eval profile --json
ai-stp eval profile --type skill --json
```

`--type` is optional. When present it is one of `instruction`, `skill`,
`mcp`, `hook`, `command`, `agent`, `plugin`, `setting`.

Success fields: `profile_id`, `scope`, `component_types`, `preconditions`,
`checks`, `eval_permissions`, `profile_version`. Each check has `check_id`,
`method`, `runner`, `assertion`, `tolerance`, `budget`. Permissions list
`filesystem`, `network`, and `process` postures. Budget fields include
`timeout_seconds` and `max_output_bytes`.

## Plan

```bash
ai-stp eval plan \
  --setup-id <setup_id> \
  --setup-version 1.0 \
  --harness-version 0.140.1 \
  --provider-version 1.2.3 \
  --runner-version 1.0.0 \
  --json
```

Required: `--setup-id`, `--setup-version`, `--harness-version`,
`--provider-version`, `--runner-version`. `--component-id` is repeatable:
an optional exact subset of the setup graph.

The setup must already exist locally as that exact `X.Y`. Eval does not
compose it.

Success fields: `plan_id`, `plan_digest`, `profile`, `setup_id`,
`setup_version`, `setup_passport_digest`, `setup_artifact_digest`,
`harness_id`, `harness_version`, `provider_version`, `runner_version`,
`components`, `planned_at`. Each component coordinate has `stable_id`,
`version`, `passport_digest`, `artifact_digest`, `component_type`.

## Run

```bash
ai-stp eval run \
  --plan-id <plan_id> \
  --expected-plan-digest sha256:... \
  --json
```

`--plan-id` and `--expected-plan-digest` are required. The digest is the
one `eval plan` returned. A changed graph is a new plan.

The run executes the local-static checks in the profile. It does not apply
a setup and does not talk to a model.

Success fields: `run_id`, `result_digest`, `plan`, `status`, `executed_at`,
`checks`. Each check result has `check_id`, `method`, `runner`, `status`,
`message`. Also present: `immutable_published_bytes_changed`,
`provider_permissions_used`.

## Status and show

```bash
ai-stp eval status --run-id <run_id> --json
ai-stp eval show --run-id <run_id> --json
```

`--run-id` is required. Both answers use the same result schema. `status`
is the short immutable view; `show` is the full evidence. Neither reruns
the checks.

## Happy path

```text
select confirm --proposal <id>          # or setup compose apply
→ eval profile --type skill
→ eval plan --setup-id <id> --setup-version <X.Y> --harness-version … --provider-version … --runner-version …
→ eval run --plan-id <plan_id> --expected-plan-digest sha256:...
→ eval status --run-id <run_id>
→ eval show --run-id <run_id>
```

A green eval is local evidence. It is not `component_verified`, not a
publication, and not an install. Attach signed attestations with
`attestation sign` when a publication plan needs them.

## Named success fields

| Command | Fields to read |
| --- | --- |
| `profile` | `profile_id`, `checks`, `eval_permissions` |
| `plan` | `plan_id`, `plan_digest`, `setup_passport_digest`, `components` |
| `run` / `status` / `show` | `run_id`, `result_digest`, `status`, `checks`, `executed_at` |

On a run, also read `immutable_published_bytes_changed` and
`provider_permissions_used`. A change to published bytes during eval is a
signal to stop, not a detail to ignore.

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | a required version or id is missing, or `--type` is not in the closed set | read the descriptor |
| `AI_STP_NOT_FOUND` | that setup version or plan id is not local | compose or confirm the setup first |
| `AI_STP_PLAN_STALE` | `--expected-plan-digest` no longer matches | `eval plan` again |
| `AI_STP_PRECONDITION_FAILED` | a precondition of the profile is not met | read `preconditions`; fix the graph |
| `AI_STP_USER_DECISION_REQUIRED` | the digest was omitted | pass `--expected-plan-digest` |
| treating `status: failed` as `ok: false` | the envelope can still be a successful report of failed checks | read each check `status` and `message` |
| inventing `--confirm` | run is confirmed by the plan digest | do not add a boolean |
| asking eval to call a model | this product does not | stop; there is no model-key flag |

Eval permissions are the profile's declared posture. They are not a
provider install and not a network exemption for the harness.

## Related links

- [Select](select.md)
- [Setup commands](setup.md)
- [Publication](publication.md)
- [Security checks](../security-checks.md)
- [Trust and safety](../trust-and-safety/index.md)
- [Command map](commands.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups eval commands so a person can find them. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and
the CLI disagree, follow the CLI.
