---
description: "Decision to make bundle v2 carry exact component adaptation and provider profile bindings."
last_verified: "2026-09-03"
---

# ADR-0144: Bundle v2 Binds Adaptations to the Provider Profile

Status: accepted.

## Context

`ADR-0143` makes an adaptation part of the immutable component version, but
`ai-stp-bundle/1` carries only final files and their component owner IDs. A
provider can verify paths and bytes against its current profile, yet cannot
prove that the compiler selected the same `adaptation_id`, scope, projection
artifact or profile digest that the component passport declared. An owner ID is
not that proof.

Changing the closed `/1` manifest in place would give one format name two
meanings and make released strict providers reject bytes whose name claims the
old contract. The first supported alpha is not released yet, so migration can
be staged without making `/1` a supported legacy line.

## Decision

`ai-stp-bundle/2` adds two required immutable bindings.

One `projection_profile` names the exact provider profile ID, content digest and
resolved target scope. One sorted `component_adaptations` entry per component
names its version-passport digest, `adaptation_id`, projection artifact digest
and size, provider-native kind, projection kind and exact member paths.

The compiler refuses `/2` before serialization unless:

- the profile scope equals the bundle scope;
- every file owner has exactly one component binding;
- every emitted file path belongs to that owner's declared members;
- the selected scope atom requires this exact profile and `/2` format;
- every component reference and adaptation comes from the exact immutable
  graph revision.

The provider independently compares the manifest profile digest with the
profile selected during planning and validates every adaptation binding before
creating an operation plan. Plan, apply, status and recovery continue to echo
the one resolved `projection_profile_digest`.

Rollout is ordered: consumer emits deterministic `/2` vectors without selecting
them; providers add `/2` validation and advertise new content-derived profile
digests; the first-party corpus is rebuilt against those digests; consumer
selects `/2`; released-binary lifecycle evidence passes for all providers; `/1`
is then removed before `0.0.16`. No supported release accepts both formats as a
compatibility promise.

## Consequences

- A provider route can no longer silently reinterpret final files as another
  component adaptation.
- Provider profile changes require new profile digests and new component
  versions; immutable prior bytes do not move.
- Multi-scope transactions bind one profile per scope-specific bundle. Atomic
  coordination across bundles belongs to the transaction contract, not this
  archive format.
- `/1` remains byte-identical only during rollout and is not part of the first
  supported release.

## Reconsideration Conditions

Reconsider if providers adopt a signed universal package whose identity already
binds all adaptation and scope facts, or if one provider operation begins to
accept multiple target scopes in one archive.
