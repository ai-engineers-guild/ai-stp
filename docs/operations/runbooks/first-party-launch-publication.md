---
description: "Runbook: publishing the first-party launch corpus through the standard pipeline."
last_verified: "2026-08-25"
---

# Publishing the first-party launch corpus

The operator batch reads an immutable snapshot of `ai_stp_contracts.first_party` and
passes each object through the existing authenticated routes:
`publication plan` → exact-byte binding → exact-hash confirmation →
server-side validation → publication. It does not write directly to the catalog, call
`catalog_seed`, or change the validation policy, `component_verified`, or trust
lane. The experimental seed from `SPEC-021` remains a separate fixture/demo path.

Actual external publication is a separate operator decision. The tool itself
only resumes the standard sequence and compiles a report.

## Preconditions

1. Sign in as the owner of the platform namespace and with an active device:
   `auth login --provider github --json`.
2. Ensure that the evidence required by the verification policy has already
   been prepared through the same path as for any publication. First-party
   origin grants no exceptions.
3. Keep the state file outside the checkout.

## Review

Review preserves the exact corpus digest, object coordinates, `plan_id`,
`plan_hash`, idempotency keys, and blockers. Plans are created for all
objects; components precede dependent setups.

```text
python apps/cli/tools/first_party_launch_publication.py review \
  --state /secure/ai-stp/first-party-launch.json
```

Repeating with the same digest resumes the saved keys and does not create a second plan.

## Apply

Apply requires an explicit `--confirm` and the same `corpus_digest` returned by
review. It reads the public catalog: a matching digest for the same `X.Y` causes
the object to be skipped as already published; a different digest blocks under
`REQ-2606` and does not call confirm. Unpublished objects bind the exact bytes,
confirm the saved plan, and read status until the state becomes `published` or
a rejection state. A setup is confirmed only after all its exact component pins
are `published`. Any blocker stops dependent objects.

`--max-polls` sets the upper bound for waiting on one plan (180 seconds by
default). Validate with a safety scan in production takes tens of seconds; too short
a wait marks a live plan as a blocker and leaves the job in the queue.

```text
python apps/cli/tools/first_party_launch_publication.py apply \
  --state /secure/ai-stp/first-party-launch.json \
  --corpus-digest sha256:<reviewed-digest> \
  --confirm
```

Repeat an interrupted run with the same command: status is read before confirm
is repeated, and the idempotency keys do not change.

## Status

```text
python apps/cli/tools/first_party_launch_publication.py status \
  --state /secure/ai-stp/first-party-launch.json
```

A read-only update of the saved `plan_id` values. If the confirm response is lost, read
status first instead of creating a new plan.

## Rejection

- A different corpus digest, owner, or device — stop.
- Missing required evidence — blocker; the dependent setup is not
  confirmed.
- The server rejects different bytes under the same `X.Y` under `REQ-2606`.
- Seed, direct catalog writes, and bypassing the validation policy are prohibited.
