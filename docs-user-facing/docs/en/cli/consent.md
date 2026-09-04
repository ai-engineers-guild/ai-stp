---
title: "Consent"
description: "Record, list, and withdraw explicit consent for unverified publishers and object major lines."
---

# Consent

An unverified object takes no part in automatic installation without
the user's explicit consent. This group records that consent, lists
what is still in force, and withdraws it. It does not install anything.

Consent is scoped. The only scopes this contract defines are
`publisher` and `object_major`. No wider form exists: there is no
“everything on this machine” switch.

This is not [Install telemetry](telemetry.md) consent. Telemetry is an
anonymous install ping with its own command. Mixing the two would make
a catalog-risk decision look like a traffic preference.

## Commands

| Command | Mutability | Confirmation | When |
| --- | --- | --- | --- |
| `ai-stp consent allow` | `apply` | `none` | Record consent to unverified objects of one publisher or major line. |
| `ai-stp consent revoke` | `apply` | `none` | Withdraw a consent. Takes effect immediately for later requests. |
| `ai-stp consent list` | `read` | `none` | Every consent still in force, and what each covered when given. |

`confirmation` is `none`. The decision is the command itself, aimed at
one publisher or one major line. That is narrower than a `--confirm`
that could cover anything.

## Typical path

See what is already recorded, then allow one publisher, then check
again:

```bash
ai-stp consent list --json
ai-stp consent allow --scope publisher --target <publisher> --json
ai-stp consent list --json
```

To allow one object major line instead:

```bash
ai-stp consent allow --scope object_major --target <stable_id> --json
```

To withdraw either form:

```bash
ai-stp consent revoke --scope publisher --target <publisher> --json
ai-stp consent list --json
```

`--scope` and `--target` are the declared options. The handler refuses
the call if either is missing. `--scope` is `publisher` or
`object_major`. `--target` is the publisher or the object major line
the consent covers.

A recorded consent is not permission to skip eligibility, a plan, or
`--expected-plan-digest`. It only answers the unverified-object gate
that would otherwise stop a later request.

`publisher` covers unverified objects of one publisher. `object_major`
covers one object major line. There is no `*` target, no account-wide
allow, and no “this session only” flag. If you need two publishers,
you record two consents.

The fingerprint is stored rather than recomputed. A later request that
needs more than the stored fingerprint is refused with
`AI_STP_PRECONDITION_FAILED`. That is the mechanism working. Allow
again only after you have read what grew.

## `consent allow`

Record consent to unverified objects of one publisher or major line.

```bash
ai-stp consent allow --scope publisher --target <publisher> --json
```

What is stored is the consent *and* a fingerprint of what the candidate
required when the user agreed. The whole mechanism is “does this now
need more than it did then”, which cannot be answered without the
older answer. If the candidate later grows new risk, the old consent
does not cover it.

`scope` must be one this contract defines. An unknown word is refused
before anything is asked about the target, so a typo is not reported
as a missing publisher.

Allowing a consent that is already in force is not a second, wider
grant. Read the returned record.

## `consent revoke`

Withdraw a consent. Takes effect immediately for later requests.

```bash
ai-stp consent revoke --scope publisher --target <publisher> --json
```

Later selection and installation requests see the withdrawal. Already
installed native state is not rolled back by this command. Rolling
back a target is [Target](target.md), through the provider.

Revoking a consent that was never given is refused with
`AI_STP_NOT_FOUND`.

## `consent list`

Every consent still in force, and what each covered when given.

```bash
ai-stp consent list --json
```

This is a read. An empty `records` array is a successful answer, not an
error. It means nothing is in force.

## What a successful envelope contains

`consent allow` and `consent revoke` return one record in `data`:

| Field | What it is |
| --- | --- |
| `consent_id` | this consent's identifier |
| `scope` | `publisher` or `object_major` |
| `target` | the publisher or major line it covers |
| `fingerprint` | what the candidate required when the user agreed |
| `observed` | what was observed at that moment |
| `origin` | where the decision was recorded |
| `decided_by` | who recorded it |
| `created_at` | when it was given |
| `revoked_at` | when it was withdrawn, or `null` |
| `schema_version` | the schema major of this record |

`consent list` returns:

| Field | What it is |
| --- | --- |
| `records` | every consent still in force, each in the shape above |
| `schema_version` | the schema major of this summary |

The envelope also carries `ok`, `warnings`, `next_actions`,
`request_id`, `operation_id`, and `schema_version`.

## Consent is not a trust line

[Trust and safety](../trust-and-safety/index.md) still applies.

| Line | What consent does |
| --- | --- |
| `authoritative` | not this page; ordinary plan and confirmation |
| `experimental` | may be considered only after explicit consent |
| `local_owner_or_pinned` | selected as a locally pinned object, not because the platform verified it |

`author_verified` and `component_verified` remain independent. Consent
does not flip either flag. It does not move an object onto the
`authoritative` line.

## What these commands never do

- install, update, or remove a component or a setup;
- widen a publisher consent into “all publishers”;
- replace telemetry consent;
- put secrets into the stored fingerprint;
- skip `select` eligibility or `install` plan confirmation;
- write a harness target.

## Typical refusals

| What you see | What it means | What to do |
| --- | --- | --- |
| `AI_STP_VALIDATION_ERROR` missing scope or target | both are required | pass `--scope` and `--target` |
| `AI_STP_VALIDATION_ERROR` unknown scope | the word is not `publisher` or `object_major` | use one of those two |
| `AI_STP_NOT_FOUND` on `revoke` | that consent was never given, or is already gone | `consent list --json` |
| `AI_STP_PRECONDITION_FAILED` | the candidate now needs more than the stored fingerprint covers | read `details`; allow again only after reviewing the new risk |
| an install still refuses | consent is not a plan digest and not eligibility | [Select](select.md) then [Install](install.md) |
| mixing this with `telemetry consent` | different decision, different command | [Install telemetry](telemetry.md) |

## Related pages

| Page | Why |
| --- | --- |
| [Trust and safety](../trust-and-safety/index.md) | trust lines and the two verification axes |
| [Catalog](../catalog/index.md) | how to read a card before consenting |
| [Registry](registry.md) | finding the publisher or object |
| [Select](select.md) | eligibility still applies |
| [Install](install.md) | plan, approve, apply still apply |
| [Install telemetry](telemetry.md) | the other consent screen |
| [Reports](report.md) | reporting an object after the fact |

!!! note "Flags from `ai-stp help --agent --json`"
    If `help --agent` disagrees with a flag on this page, the CLI wins.
    Optional flags are not listed here. Read them from the descriptor.
