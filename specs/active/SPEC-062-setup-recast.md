---
description: "SPEC-062: Recast a complete setup onto another harness with provenance."
last_verified: "2026-09-06"
---

# SPEC-062: Setup recast

## Purpose

Give the agent a machine command that takes one complete single-harness setup
and records another complete setup for a different harness. Provenance is
`ported_from` and `related_setup_ids` (`ADR-0014`). The source setup is
untouched. A partial recast is not a setup.

## Scope

Included: `setup recast plan` and `setup recast apply`; reuse of an existing
target-harness adaptation; deterministic derivation of instruction, skill,
command, agent, hook, and plugin native paths; MCP file-to-file projection and
MCP host-file contributions (`declared_key` as a setting contribution);
refusal of settings, of non-MCP host-file contributions, and of MCP plugin
packages; selecting one adaptation by the setup's harness when a component
version names several.
Excluded: reconciling two related setups; changing `harness_id` on an
existing setup; inventing Antigravity home variables; catalog/web display
of provenance (`#139`).

## Terms

- Recast — create a new setup for a target harness from an exact source setup.
- Reuse — the pinned component version already has the target adaptation.
- Derive — freeze a new component version of the same `stable_id` with an
  added derived adaptation.
- Blocked — that member cannot be reused or derived; the plan is not complete.

## Requirements

- `REQ-6201`: `setup recast plan` names the source setup, optional exact
  version, and target harness. Same-harness recast is refused. The plan lists
  every source member as `reuse`, `derive`, or `blocked` with a machine reason.
- `REQ-6202`: Apply records a new setup whose `harness_id` is the target,
  `ported_from` is the exact source setup version, and `related_setup_ids`
  contains the source `stable_id`. The source setup is unchanged.
- `REQ-6203`: Apply refuses a plan that is not complete, a stale plan digest,
  or a member that became blocked after planning. Completeness requires every
  member to be `reuse` or `derive`.
- `REQ-6204`: A component version that already has a unique adaptation for the
  target harness is reused. A missing adaptation is derived when the target
  provider rule is a whole-path file or directory without `declared_key`, or
  when the kind is `mcp` and the target rule is a host-file contribution.
  Settings never derive. Non-MCP host-file contributions never derive. An MCP
  plugin package (`projection_kind=package`) never derives.
- `REQ-6205`: Derived adaptations are `implementation_mode=derived`, keep the
  logical component type, and land on the target rule's path and scope. The
  new component version is the next minor of the same `stable_id`.
- `REQ-6206`: Composition, conversion, and install select the adaptation that
  matches the setup's `harness_id`. A component version with two adaptations
  is not a conflict.

## States and errors

`AI_STP_VALIDATION_ERROR` — same harness, missing source identity, or missing
target harness. `AI_STP_NOT_FOUND` — source setup or member is absent.
`AI_STP_PLAN_STALE` — apply digest mismatch. `AI_STP_CONFLICT` — incomplete
plan or the new setup version already exists. `adaptation_unavailable` remains
the install-time code when a pinned version has no target adaptation.

## Security and privacy

Recast copies already-recorded local bytes. It does not read secrets, call a
model, or write a harness target.

## Compatibility and migration

`ported_from` and `related_setup_ids` stay the existing passport fields.
Historical setups with null provenance remain valid. No generation port.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-6201` | Plan of a Claude instruction setup onto Codex lists `derive`; same-harness plan is refused. |
| `REQ-6202` | Apply writes `ported_from` and `related_setup_ids`; source version digest is unchanged. |
| `REQ-6203` | A setup whose only member is a setting is incomplete; apply with that digest is refused. |
| `REQ-6204` | A component that already has a Codex adaptation is `reuse`; a setting is `blocked`; a Cursor MCP file recast onto Codex is `derive` as `config.toml#mcp_servers`; a Pi MCP recast is `blocked`. |
| `REQ-6205` | Derived Codex instruction lands on `AGENTS.md` and is a new minor of the same id. |
| `REQ-6206` | A two-adaptation component produces a composition surface for the requested harness. |
