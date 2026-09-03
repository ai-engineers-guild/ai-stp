---
title: "Install"
description: "Plan, approve, apply, cancel, recover, and resume an installation."
---

# Install

Install computes an immutable plan, records an approval against that plan's
digest, and asks the harness's public provider to apply it. The CLI does not
write native harness state itself.

A plan has no effect of its own. Approval is the user decision. Apply is
the provider's write, journaled here. Recover and resume inspect or finish
a result check; they do not apply the plan again.

## Command table

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp install plan` | `plan` | `none` | compute an immutable installation plan |
| `ai-stp install approve` | `apply` | `plan_digest` | approve one plan by its exact digest |
| `ai-stp install apply` | `apply` | `plan_digest` | carry out one approved plan through its provider |
| `ai-stp install cancel` | `apply` | `none` | abandon a plan before anything is applied |
| `ai-stp install status` | `read` | `none` | operations that stopped without a settled outcome |
| `ai-stp install recover` | `read` | `none` | what one stopped operation left; recovers nothing itself |
| `ai-stp install resume` | `apply` | `none` | finish the result check an interrupted apply never made |

`--json` is global. Always pass it.

Approve is confirmed by `--plan-digest` of the plan the user saw. Apply
does **not** take a digest flag: approval already bound that digest to the
operation. There is no `--confirm` on this group. There is no
`--expected-plan-digest` on `install plan`, `approve`, or `apply`.

## Plan

Exactly one of `--proposal` or `--setup` is required. `--setup` is
`<stable_id>@<X.Y>` and then `--project` is required. `--provider` is
always required.

```bash
ai-stp install plan \
  --proposal <proposal_id> \
  --provider <exe> \
  --provider-manifest <path> \
  --protocol-version 3 \
  --target <dir> \
  --json
```

From a prepared setup version:

```bash
ai-stp install plan \
  --setup setup_...@1.0 \
  --project . \
  --harness codex \
  --provider <exe> \
  --provider-manifest <path> \
  --protocol-version 3 \
  --target <dir> \
  --json
```

`--action` is `install`, `update`, `backup`, `remove`, or `rollback`. Omit
it for a normal install. `--backup-ref` is required by a protocol-v3
rollback. `--scope` is `global` (default), `project`, or `user_root`.
`--target` is required for protocol v2/v3 and when `--scope` is `project`
or `user_root`.

`--provider-manifest` is required by protocol v3 unless
`--unverified-provider` is given. `--provider-build-attestation` verifies
exact provider bytes through the repository, source commit, and signer
workflow pinned by local policy. `--provider-attestation-bundle` is an
optional local GitHub attestation bundle for offline verification.
`--provider-release-recovery` explicitly recovers an older exact provider
release already verified on this machine. `--permission-profile` is a
provider-declared execution posture, separate from setup identity.

A backup you take on purpose:

```bash
ai-stp install plan \
  --action backup \
  --project <project_id> \
  --harness codex \
  --provider <exe> \
  --provider-manifest <path> \
  --protocol-version 3 \
  --target <dir> \
  --json
```

A restore from a provider-owned copy uses `--action rollback` and
`--backup-ref`. That is not `target rollback`, which only **names** a
previous version. See [Target](target.md) and [Setups](../setups/index.md).

## Approve

```bash
ai-stp install approve \
  --operation <operation_id> \
  --plan-digest sha256:... \
  --json
```

`--operation` and `--plan-digest` are required. The digest is the
confirmation. A flag meaning "whatever is in front of me" is not accepted.
A changed plan is a new operation.

## Apply

```bash
ai-stp install apply \
  --operation <operation_id> \
  --provider <exe> \
  --json
```

`--operation` and `--provider` are required. The operation must already be
approved. Apply re-checks the target, lets the provider act, records
`applied_unverified` before looking, then verifies. An interrupted provider
call is `partial`, never a guessed failure: a timeout does not prove
nothing happened.

After an unconfirmed timeout, read `install status` and `install recover`.
Do not apply again until you know the operation is still `approved`.

## Cancel, status, recover, resume

```bash
ai-stp install cancel --operation <operation_id> --reason "changed composition" --json
ai-stp install status --json
ai-stp install recover --operation <operation_id> --json
ai-stp install resume --operation <operation_id> --provider <exe> --json
```

Cancel is refused once applying began. `--reason` is optional.

`status` lists operations that stopped without a settled outcome. `partial`
appears here even though it is terminal: someone still has to recover.

`recover` is a read. It reports `operation_id`, `state`, `backup_ref`,
`effects_recorded`, `next_actions`. It restores nothing.

`resume` finishes the result check an interrupted apply never made. It
applies nothing. `--operation` and `--provider` are required.

## Happy path

```text
select confirm --proposal <id>
→ install plan --proposal <id> --provider <exe> --provider-manifest <path> --protocol-version 3 --target <dir>
→ read operation_id and plan_digest
→ install approve --operation <id> --plan-digest sha256:...
→ install apply --operation <id> --provider <exe>
→ target status --project <id> --harness <id>
```

Deliberate restore from a backup you took:

```text
install plan --action backup … → approve --plan-digest → apply
→ target backups --project <id> --harness <id>
→ install plan --action rollback --backup-ref <exact> …
→ approve --plan-digest → apply
→ target status
```

## Named success fields

Every plan / approve / apply / cancel / resume answer is an installation
view. Read at least:

| Field | Meaning |
| --- | --- |
| `operation_id` | the journal id you pass onward |
| `plan_digest` | the exact digest `approve` must echo |
| `action` | `install`, `update`, `backup`, `remove`, `rollback` |
| `state` | `planned`, `approved`, `applying`, `applied_unverified`, `verified`, `partial`, `failed`, `stale`, `cancelled`, `rolled_back` |
| `backup_ref` | provider-owned copy, when the plan took one |
| `expected_target_digest` | what the target must become |
| `provider_plan_digest` | the provider's own plan bytes |
| `provider_release_trusted` | whether the pinned policy accepted the provider |
| `provider_release_trust` | `verified_publisher`, `signed`, `build_attested`, or `unverified` |
| `effects` | listed effects of the plan |
| `managed_paths` | paths the provider will own |
| `steps` | append-only journal of this operation |
| `expires_at` | when a still-planned operation goes stale |

`recover` adds `next_actions` and `effects_recorded` for one stopped
operation. `status` lists those as `stopped`.

## Refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` | both or neither of `--proposal` / `--setup`, or `--target` missing for v2/v3 | name exactly one source; add `--target` |
| `AI_STP_USER_DECISION_REQUIRED` | `--plan-digest` was omitted on approve | pass the digest the plan answer carried |
| `AI_STP_PLAN_STALE` | the plan bytes or preconditions changed | plan again; the old digest does not carry |
| `AI_STP_PRECONDITION_FAILED` | apply before approve, or the target drifted | `install status`; do not invent a digest |
| `AI_STP_CONFLICT` | another operation holds the pair | wait or recover the other operation |
| `AI_STP_TIMEOUT_UNCONFIRMED` | apply timed out without a confirmed effect | `install recover`; do not apply again yet |
| `AI_STP_PARTIAL_OPERATION` | the provider stopped mid-write | `recover`, then `resume` or a new plan as `next_actions` says |
| `AI_STP_UNSUPPORTED_APPLY` | that harness cannot be applied this way | stop; do not substitute another harness |
| cancel after apply began | cancel is refused | recover; do not delete backups by hand |
| `--expected-plan-digest` on approve | that flag is not declared here | use `--plan-digest` |

Do not delete the target or backups by hand before recovery has finished.
Do not restore a single component: restoring returns the target as a whole.

## Related links

- [Select](select.md)
- [Target](target.md)
- [Provider](provider.md)
- [Setup commands](setup.md)
- [Setups](../setups/index.md)
- [Telemetry](telemetry.md)
- [Troubleshooting](../troubleshooting/index.md)
- [Command map](commands.md)

## Machine help is the parser

```bash
ai-stp help --agent --json
```

This page groups install commands so a person can find them. The installed
CLI is the source of flags, schemas, and `next_actions`. If this page and
the CLI disagree, follow the CLI.
