---
title: "Publication"
description: "Sign attestations and plan, inspect, and confirm a component publication."
---

# Publication

Publication creates an immutable server plan for one exact released
component version, and confirms that plan by its hash. Attestation signing
binds credential-dependent test evidence to the active device key.

The plan does not make the version public. Confirm does. A failed check
must not leave a partially published version behind. `author_verified` still
does not mean the content is safe.

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp attestation sign` | `apply` | `explicit_flag` | sign exact credential-dependent test evidence with the active device key |
| `ai-stp publication plan` | `plan` | `none` | create an immutable server plan for one exact released component version |
| `ai-stp publication status` | `read` | `none` | read the current server state of one publication plan |
| `ai-stp publication confirm` | `apply` | `explicit_flag` | confirm one exact unexpired publication plan hash |

`--json` is global. Always pass it.

`attestation sign` requires `--confirm`. `publication confirm` requires
`--plan-hash` and `--confirm`. For a whole setup graph, use
`setup publish plan` / `setup publish confirm` instead of confirming each
member by hand.

## Attestation sign

Sign observed test evidence locally. The output file is owner-only JSON.
The command does not upload it.

```bash
ai-stp attestation sign \
  --id <stable_id> \
  --version 1.0 \
  --check-id <check_id> \
  --policy-version <policy> \
  --harness-id codex \
  --harness-version 0.140.1 \
  --provider-version 1.2.3 \
  --test-case-id <case_id> \
  --result passed \
  --output ./attestation.json \
  --confirm \
  --json
```

Required: `--id`, `--version`, `--check-id`, `--policy-version`,
`--harness-id`, `--harness-version`, `--provider-version`, `--test-case-id`
(repeatable), `--result` (`passed` or `failed`), `--output`, `--confirm`.
`--tool-version` is repeatable `name=version`.

Success fields: `object_digest`, `subject`, `check_id`, `policy_version`,
`harness_id`, `harness_version`, `provider_version`, `test_case_ids`,
`result`, `account_id`, `device_id`, `attested_at`, `signature`,
`output_path`, `attestation_digest`.

Pass `--output` into `publication plan --attestation-file` later. Do not
put secrets in the attestation file.

## Publication plan

```bash
ai-stp publication plan --id <stable_id> --version 1.0 --json
ai-stp publication plan \
  --id <stable_id> \
  --version 1.0 \
  --attestation-file ./attestation.json \
  --json
```

`--id` is the stable identifier of the released component. `--version` is
the exact local `X.Y`. `--attestation-file` is repeatable.

The version must already be released (`component version release`). The
active session's device must match the signer of any attached attestation.

Success fields: `plan_id`, `plan_hash`, `state`, `object_kind`, `stable_id`,
`version`, `content_digest`, `component_verified`, `policy_version`,
`actor_id`, `device_id`, `effects`, `evidence`, `expires_at`. Read
`effects` before confirming. `component_verified` here is the plan's
recorded bit, not a reason to skip the hash check.

## Status

```bash
ai-stp publication status --plan-id <plan_id> --json
```

`--plan-id` is required. The answer is the same publication-plan view.
Confirm only an unexpired plan whose `plan_hash` still matches.

## Confirm

```bash
ai-stp publication confirm \
  --plan-id <plan_id> \
  --plan-hash sha256:... \
  --confirm \
  --json
```

`--plan-id` and `--plan-hash` are required. `--confirm` is the explicit
flag. The hash is the one `plan` returned. A changed plan is a new plan.

The answer is the plan view in its new `state`. Follow with
`publication status` if the envelope tells you to wait, or with
`owner version show` to see the public version.

## Happy path

Component:

```text
component passport validate --id <id>
→ component version release --id <id>
→ attestation sign … --output ./attestation.json --confirm   # when evidence is required
→ publication plan --id <id> --version <X.Y> --attestation-file ./attestation.json
→ publication status --plan-id <plan_id>
→ publication confirm --plan-id <plan_id> --plan-hash <hash> --confirm
→ owner version show --kind component --id <id> --version <X.Y>
```

Embedded member:

```text
component publish --from-setup <setup> --setup-version <X.Y> --component-id <id>
→ publication confirm --plan-id <plan_id> --plan-hash <hash> --confirm
```

Whole setup graph: [Setup commands](setup.md) `setup publish plan` then
`setup publish confirm --set-digest … --confirm`.

## Named success fields

| Command | Fields to read |
| --- | --- |
| `attestation sign` | `output_path`, `attestation_digest`, `signature`, `result` |
| `publication plan` / `status` / `confirm` | `plan_id`, `plan_hash`, `state`, `effects`, `evidence`, `expires_at` |

Also read `content_digest`, `component_verified`, and `policy_version` on
the plan. They must match the version you intended.

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_AUTH_REQUIRED` | no signed-in account | `auth login` |
| `AI_STP_USER_DECISION_REQUIRED` | `--confirm` was omitted | pass `--confirm` after reading `effects` |
| `AI_STP_VALIDATION_ERROR` | `--id`, `--version`, `--plan-id`, or `--plan-hash` missing | read the descriptor |
| `AI_STP_PRECONDITION_FAILED` | attestation not bound to this version, device, and account | sign again on this device after login |
| `AI_STP_PLAN_STALE` / expired `expires_at` | the plan is no longer current | `publication plan` again |
| `AI_STP_PERMISSION_DENIED` | this account cannot publish that id | `owner object show` |
| `AI_STP_CONFLICT` | a concurrent publication of the same version | `publication status`; do not confirm a second hash |
| `AI_STP_NOT_FOUND` | the version was never released locally, or the plan id is unknown | `component version list` |
| treating `component_verified` as safety | provenance and checks, not a guarantee | read [Trust and safety](../trust-and-safety/index.md) |

A public version must come from a public GitHub repository at an exact
commit and subpath. Local-only provenance is refused at plan time.

## Related links

- [Publish a component](component-publish.md)
- [Setup commands](setup.md)
- [Owner objects](owner.md)
- [Eval](eval.md)
- [Publishing](../publishing/index.md)
- [Authoring](../publishing/authoring.md)
- [Security checks](../security-checks.md)
- [Trust and safety](../trust-and-safety/index.md)
- [Command map](commands.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups publication commands so a person can find them. The
installed CLI is the source of flags, schemas, and `next_actions`. If this
page and the CLI disagree, follow the CLI.
