---
description: "SPEC-063: Materialize one target-harness adaptation from a pinned component."
last_verified: "2026-09-06"
---

# SPEC-063: Component materialize

## Purpose

Give the agent a plan/apply command that materializes one explicit target-harness
adaptation from a pinned component version, using the same native transform as
setup recast.

## Scope

Included: `component materialize plan` / `apply`; owner next-minor versions;
private local overlays (`component portability plan` / `apply`). Excluded:
catalog presentation, server persistence, mutating a published version in place.

## Terms

- Materialize — record an exact target-harness adaptation from a pinned version.
- Overlay — a private fork used for claimed-portable install.
- Reuse — the pinned version already has the target adaptation.
- Derive — freeze a new version with an added derived adaptation.
- Blocked — the surface cannot be rewritten without silent loss.

## Requirements

- `REQ-6301`: Plan names the pinned component, optional source harness, and
  one or more target harnesses from the closed set. `--all-missing` targets
  every closed harness that does not yet have an adaptation. Same-harness
  materialize is refused. `--all-missing` with an explicit `--to-harness` is
  refused. Apply of `--all-missing` is complete only when every requested
  target is `reuse` or `derive`; a blocked member fails the whole set.
- `REQ-6302`: The plan digest binds source passport digest, transform identity
  and version, provider profile digest, target harness, produced projection
  identity, declared losses, and whether the result is a local overlay.
- `REQ-6303`: Owner apply records the next minor of the same `stable_id` when
  bytes change. Source and unrelated adaptations are preserved. Retry of the
  same plan is idempotent.
- `REQ-6304`: A local overlay forks a new private `stable_id` and never mutates
  the source version. Public publication still requires an exact published
  adaptation of the public object. A public setup composition and setup
  publication refuse an overlay or other private member. A private local setup
  may include the overlay.
- `REQ-6305`: Unsupported or unmapped surfaces are `blocked`. Apply refuses an
  incomplete or stale plan.

## States and errors

`AI_STP_VALIDATION_ERROR` — missing identity, unknown harness, or same-harness
target. `AI_STP_NOT_FOUND` — the pinned version is absent. `AI_STP_PLAN_STALE`
— apply digest mismatch. `AI_STP_CONFLICT` — incomplete plan or a version
already stands for different content.

## Security and privacy

Materialize copies already-recorded local bytes. It does not read secrets, call
a model, or write a harness target. A local overlay is `private`.

## Compatibility and migration

Owner apply uses the next minor of the same `stable_id`. Historical versions
stay immutable. This is not a new HTTP, provider, scaffold, or standard-family
generation. The native transform is the recast table at revision `1.3`.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-6301` | Claude instruction onto Codex is `derive`; same harness is refused. `--all-missing` on that instruction is incomplete because Cursor and Antigravity stay `blocked`; the four derivable targets in one apply produce `1.1`. |
| `REQ-6302` | Identical inputs share a plan digest; a stale digest is `AI_STP_PLAN_STALE`. |
| `REQ-6303` | Apply creates `1.1`; a second apply of the same digest returns `created=false`. |
| `REQ-6304` | Portability apply leaves source 1.0 without the target adaptation; the overlay is `private` and recorded in `overlay_origin`. |
| `REQ-6305` | A setting cannot materialize across harnesses. |
