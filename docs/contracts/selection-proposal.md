---
description: "Ephemeral composition proposal, its confirmation, and atomic persistence of a SetupVersion."
last_verified: "2026-08-25"
---

# Composition proposal and confirmation

The requirements owner is `SPEC-006`; machine-help actions belong to `SPEC-011`,
and the decision is `ADR-0027`. This document defines the machine boundary: what
a proposal contains, what it is not, and exactly what happens at confirmation.

## Recommendation session

Direct search remains an ordinary registry operation and does not create
proposals. A recommendation session is a separate flow over `SelectionRun`:

```text
context snapshot: passport revisions, selected harness
→ eligible candidates after mechanical constraints and trust lines
→ the agent authors one or more proposals
→ the user confirms exactly one proposal
→ atomic persistence of a private SetupVersion
```

The user's agent decides how many proposals to show; the result-size limit
remains a policy limit. `ai_stp` does not call model interfaces: the agent
authors proposals through machine commands.

## Proposal

A proposal is a derived, ephemeral object within a session. It contains:

- a proposal identifier valid only within the session;
- an exact composition graph: component version references according to
  `canonical-data.md` and explicit overlays;
- an input snapshot: context passport revisions, candidate hashes, and the
  policy version;
- trust lines, consent sources, and reasons for each candidate;
- aggregate permissions, required environment, and external connection points
  of the composition.

The exact graph may be empty: this is an explicit complete setup without
components. It differs from an absent proposal, goes through the same
confirmation, and is installed through the same provider lifecycle.

Displaying proposals does not create a version, target, `entity`, revision, or
synchronized registry object. The exact snapshot lives in the local session row
so that the next CLI process can confirm exactly the displayed composition and
check it for staleness. Cancellation preserves only the idempotent terminal
outcome of the row and does not change domain or target state.

## Confirmation

Explicit confirmation of one proposal is atomic and does exactly three things:

1. freezes the proposal's exact graph as a new private `SetupVersion` of the
   selected harness;
2. records a `RecommendationTrace` with trust lines, consent sources, and
   reasons;
3. pins the new version as selected for the project and harness pair and moves
   the pair to the pending installation state `pending_install`.

Selected and installed versions are separate facts. A version becomes installed
only after provider `verified` under a separate installation plan; until then,
the pair remains in `pending_install`, which is a normal state rather than
drift. The stable ID + version pair is compared: another Setup with the same
`X.Y` number also awaits installation. `local_drift` means that the target was
changed outside the provider lifecycle, not that installation of the selected
version is pending.

`catalog_drift` exists only when the available canonical version `X.Y` is
numerically greater than the selected version; mere string inequality is
insufficient. Thus `1.10` is newer than `1.9`, while a lagging catalog at `1.9`
with `2.0` selected is not a call to roll back.

Confirmation returns an exact reference to the created version. There is no
other way to create a `SetupVersion` from a proposal; applying the composition
without a version, package, and provider plan is prohibited by `SPEC-011`.

## Staleness and retry

A proposal is bound to its input snapshot. A change to any candidate hash,
context passport revisions, or the policy version makes the proposal stale;
confirmation of a stale proposal is rejected with a typed error and requires a
new session.

Exact versions, participant eligibility, and the sole heads of developer,
device, and project passports are checked before opening the transaction and
again under `BEGIN IMMEDIATE`. Their removal or change between the first check
and the write lock rejects confirmation and leaves no partial SetupVersion.

Repeated confirmation of the same proposal is idempotent: it returns the
already created version and does not create a second object.

## Errors

The following are distinguished: stale proposal, unknown proposal, ineligible
candidate within the proposal, active-version pin conflict, and persistence
failure. Partial persistence is impossible: either the version, trace, and pin
are created together, or nothing is created.
