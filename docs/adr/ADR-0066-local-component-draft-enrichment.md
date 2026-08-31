---
description: "Safe enrichment of a local component draft through confirmed content-addressed revisions."
last_verified: "2026-08-10"
---

# ADR-0066: Local enrichment of a component draft

Status: accepted.

## Context

Native discovery and adopt intentionally know only mechanical facts: layout,
path, exact bytes, and proven provenance. A complete ComponentVersionPassport
additionally requires a name, safe description, license, dependencies,
capabilities, permissions, and exact public source. Without a separate write
boundary, the agent either cannot bring the draft to completeness or is forced
to modify SQLite and guess fields outside the machine contract.

Component and setup are simultaneously used as the kind of a local entity and
as the kind of an immutable version passport. Therefore, prohibiting parent
revisions on the shared PassportEnvelope incorrectly prohibits draft history
specifically, even though immutability is required only for the formal version
snapshot.

## Decision

The CLI receives three commands from a single command registry: passport show,
update, and validate, with an explicit `--for-publication` profile. Update accepts
only a bounded regular JSON file, does not follow symbolic links, uses a closed
typed schema, rejects secret-bearing keys before reflecting values, and requires
both `--expected-revision` and `--confirm`.

The read-only `passport suggest` operates before update and only on saved exact
bytes. It copies suggestions from the closed `ai-stp.component` block in
`pyproject.toml` or `package.json` and from complete exact Git provenance, names
the source of each field, and leaves all values unconfirmed. Ordinary package
manifest fields are not interpreted as component semantics. An unknown,
invalid, or contradictory declaration fails closed; a field that cannot be
inferred remains explicitly unresolved and is not assigned a guess.

Accepted fields are recorded as declared/user-confirmed facts in a new
content-addressed child revision. A no-op returns the current revision; a stale
head fails with a conflict. The shared envelope permits a parent graph for a
component draft; concrete ComponentVersionPassport and SetupVersionPassport
separately require an empty parent list and remain immutable snapshots.

Publication validation does not write to the network or publish. It lists all
missing/invalid fields and attempts to construct a formal
ComponentVersionPassport from the exact revision. Cloud publication planning,
approval, application, recovery, and status are added only after a stable server
contract exists and are not imitated by a local command.

## Alternatives considered

1. Automatically infer all fields from an ordinary package manifest. Rejected:
   package dependencies do not prove the component's purpose, while the license,
   permissions, and conditional authorization require an explicit versioned
   block and a decision.
2. Edit YAML next to the installed component. Rejected as a hidden write to the
   target and a conflation of the source object with the local registry draft.
3. Allow an arbitrary JSON merge. Rejected: it creates a second unbounded schema
   owner and can carry secrets or unknown requirements.
4. Treat `ready` as publication authorization. Rejected: local structure does
   not prove authentication, permissions, current server policy, or the absence
   of a race.

## Consequences

The agent receives an executable path from adopt to formal completeness without
a model API and without manual SQLite changes. The revision graph is synchronized
by the existing mechanism; a released version does not move after a subsequent
update. The publication state machine remains an open dependency of platform/CLI
contracts rather than a hidden side effect.

## Reconsideration conditions

The decision is reconsidered when a versioned patch schema, a provable manifest
extraction proposal, or a server publication contract appears. New fields are
not added as free-form extras: they first receive a typed owner and compatibility
with generated schemas.
