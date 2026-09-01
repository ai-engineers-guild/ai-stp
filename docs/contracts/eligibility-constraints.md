---
description: "Mechanical constraints before agent selection: a closed list of rejection reasons, check order, and two independent eligibility axes."
last_verified: "2026-08-26"
---

# Mechanical constraints and rejection reasons

The requirements owner is `SPEC-006` REQ-601, REQ-603, and REQ-613; the
decisions are `ADR-0016` for trust lines and `ADR-0032` for reporting
installation eligibility. This document defines the machine boundary: the
constraint families, the closed set of rejection reasons, the check order, and
the distinction between eligibility and the right to be selected automatically.

Constraints are enforced **before** the agent sees candidates. Agent reasoning
cannot weaken or override them: an ineligible candidate is not included in the
selection input, so returning it as free text is impossible.

## Two independent axes

One flag is insufficient, and merging these axes into a single Boolean response
is an error:

- `admissible` — the candidate passed all mechanical constraints. This axis
  answers “may this be installed,” and the trust line does not relax it: under
  `validation-policy.md`, trust lines change the conditions for inclusion in
  results, not the set of mandatory installation checks.
- `auto_selectable` — the candidate is admissible **and** its trust line permits
  automatic selection. The `experimental` line never permits it, even with
  valid consent: consent enables display in a separate section, not automatic
  installation under `SPEC-006` REQ-603.

An `experimental` candidate with consent is admissible and is not automatically
selectable. This is a normal state, not a rejection, and does not participate in
the list of reasons below.

## Installed targets are not disabled

Constraints decide the fate of **new** installations and updates. An already
installed target continues to operate and receives a warning with the reason
under `ADR-0032`; no remote target kill switch exists, and none of the codes
below creates one.

## Families and reasons

The list is closed. A new reason requires changing this document, and adding one
is a machine-boundary change. Each reason has a stable code that does not change
with the message text: the message is for humans, while the code is for machines
and tests.

### `compatibility` — whether the candidate technically fits the target

| Code | When it occurs |
|---|---|
| `harness_mismatch` | the object declares another harness |

The declared harness is read from the stored passport in the same way as the
composition surface: first from the document field, otherwise from
`facts.harness_id`. A passport of an exact catalog version carries `harness_id`
at the top level and need not duplicate it as a fact.

A component that names no harness is portable — a repository-root `AGENTS.md`
is one convention several products read, not one surface per product — and is
compatible with every harness whose released provider declares a native
surface for its kind; where none does, the refusal is
`provider_surface_unavailable`, the same code a harness-bound object of that
kind receives. A setup always names exactly one harness.
| `harness_version_unsupported` | the detected harness version is outside the declared range |
| `harness_version_unknown` | a range is declared, but the harness version on the target could not be read |
| `os_unsupported` | the target system is not among the declared systems |
| `arch_unsupported` | the target architecture is not among the declared architectures |
| `capability_malformed` | a required capability fails normalization under `capability-vocabulary.md` |
| `capability_unknown` | a required capability is outside the vocabulary |
| `capability_missing` | a known required capability is absent from the target |

`capability_unknown` and `capability_missing` are intentionally distinct: the
former means an invalid passport and is fixed by the author; the latter means a
mismatch with this target and is fixed by the user. A shared code would tell the
user to install a tool that does not exist.

A version is the first word in `--version` output that is a number containing a
dot: `2.1.224 (Claude Code)` and `codex-cli 0.146.0` are read identically, while
`2024` is not considered a version. A prerelease suffix preserves ordering:
`1.2.3-beta` precedes `1.2.3`; otherwise, the prerelease would satisfy a lower
bound written precisely to exclude it. A string without such a word is an
unreadable version, not version `0`.

`harness_version_unknown` is separated from `harness_version_unsupported` for
the same reason. A declared range is a mandatory compatibility condition, and
the inability to evaluate it is not evidence of compatibility: under
`ADR-0032`, absence of evidence blocks a new installation. But this has its own
reason—a silent `--version`, not an unsuitable version—and a shared code would
tell the user to update something that does not need updating.

### `access` — whether the object is available at all

| Code | When it occurs |
|---|---|
| `object_not_registrable` | a draft or deleted object |
| `object_blocked` | manual moderator state `blocked` |
| `grant_missing` | another owner's private object without permission for this primary line |

### `trust` — whether the attestation is current

| Code | When it occurs |
|---|---|
| `evidence_stale` | required evidence is not a current `passed` |
| `unverified_without_consent` | the `experimental` line without consent covering the candidate |

`evidence_stale` is an installation constraint, not only a line constraint.
Under `ADR-0032`, losing current evidence simultaneously clears
`component_verified`, removes the version from `authoritative`, and blocks new
installations; the user's own object has no mandatory evidence and is not
rejected for this reason.

### `license` — whether the license permits the intended use

| Code | When it occurs |
|---|---|
| `license_undeclared` | the version does not name a license |
| `redistribution_forbidden` | the composition is intended for distribution, but the version forbids it |

### `entitlement` — whether the object expands permissions

| Code | When it occurs |
|---|---|
| `entitlement_not_granted` | a permission is required that the target has not allowed |

### `provider` — whether anything can install it

| Code | When it occurs |
|---|---|
| `provider_unavailable` | no released provider exists for the harness |
| `provider_platform_unsupported` | the released provider does not support the target system or architecture |
| `provider_surface_unavailable` | the harness has no native surface for the component type, so the provider cannot project it |

## What is not a rejection

The following states are returned in a separate notes list and do not prohibit
installation. Turning any of them into a rejection violates the named
requirement:

| Note code | Requirement |
|---|---|
| `required_env_missing` | `SPEC-001` REQ-111, `SPEC-008` REQ-816: installation is allowed, while launch readiness remains `needs_configuration` |
| `authorization_required` | `SPEC-008` REQ-820: installation completes; authorization is explained to the user |
| `credentials_required` | `component-setup-passports.md`: the flag is shown before installation alongside permissions |

A note names only the variable name or authorization type. The variable value,
credentials, and the address where they are issued are not included in the
note.

## Order

The family order is fixed and matches the order listed in `REQ-601`:

```text
compatibility → access → trust → license → entitlement → provider
```

All checks within a family are performed in the order shown in the table above,
not only until the first rejection: `REQ-604` requires an explainable trace, and
one reason out of six would hide the other five and force them to be fixed one
at a time. The fixed order makes the reason list identical for identical input,
as required by `REQ-607`.

## Rejection

A rejection contains the family, stable code, message, and details. Details
name the participating values: capability identifier, declared version range,
and required permission. Secrets, environment-variable values, and credential
contents are not included in a rejection.

A rejection is response data, not an execution error: an ineligible candidate
is a normal selection result, and `no_candidate` under `SPEC-006` remains an
honest state rather than a server error.
