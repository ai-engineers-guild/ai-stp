---
description: "SPEC-040: Local functional evaluation profiles for an exact setup."
last_verified: "2026-08-13"
---

# SPEC-040: Setup Evaluation Profiles

## Purpose

An author and an agent can create a reproducible evaluation plan for a component, a subset, or a complete `SetupVersion`, run the available local mechanical checks, and obtain immutable evidence without changing published bytes or using provider permissions.

## Scope

This specification covers a versioned profile, exact coordinates, budgets, isolation requirements, a local deterministic runner, and truthful states for unavailable model/human runners. Credentialed checks at publication time and displaying evidence on the web are implemented as separate consumers of the shared contract.

## Terms

- **Profile** — portable evaluation intent without coordinates of a specific version.
- **Plan** — a profile bound to an exact `SetupVersion` and runner environment.
- **Result** — immutable local evidence for one confirmed plan.

## Requirements

- `REQ-4001`: `SetupEvalProfile` version `setup-eval/1` defines the scope, component kinds, preconditions, checks, assertions, explicit tolerances, budgets, isolation requirements, and separate eval permissions.
- `REQ-4002`: The reference profile contains a base check and type-specific tracks for all eight component kinds and separates the `deterministic`, `model_assisted`, and `human_review` methods, each with a compatible runner.
- `REQ-4003`: An evaluation plan binds the profile to exact setup/component versions, passport and artifact digests, harness/provider/runner versions, and the planning time; a subset may contain only components from the specified setup graph.
- `REQ-4004`: `eval run` requires the exact plan digest and explicit confirmation; rerunning does not create a second evidence record, and a changed digest results in a fail-closed refusal.
- `REQ-4005`: Core runs only local deterministic checks; an unavailable model, human, or isolated runner receives `not_run`, never `passed`, and an aggregate containing `not_run` receives `degraded`.
- `REQ-4006`: The result is bound to the complete plan, exact runner coordinates, result digest, and timestamp, and explicitly states that published bytes were not changed and provider permissions were not used.

## States and errors

A check accepts `passed`, `failed`, `not_run`, or `degraded`. The result is `failed` if at least one check fails; otherwise, it is `degraded` if anything was not run or was degraded; only a fully executed set receives `passed`.

A missing version, a changed passport/artifact digest, a component outside the setup graph, an incompatible method/runner combination, and a stale plan digest result in a typed refusal.

## Security and privacy

Eval permissions are not inherited from provider permissions. The core runner does not invoke a model, access the network, or execute a component artifact. The profile contains the names of required credentials, but not their values. Evidence does not change immutable published bytes and does not by itself increase trust or publication readiness.

## Compatibility and migration

The profile version is independent of the JSON Schema version. An unknown major profile version results in a fail-closed refusal. An existing result is not rewritten when the runner or profile is updated; a new run is created against a new exact plan.

## Acceptance criteria

| Requirement | Executable Verification Method |
|---|---|
| `REQ-4001` | The schema corpus rejects unknown fields, invalid budgets, and an incomplete profile. |
| `REQ-4002` | A parameterized test requires a reference profile for all eight component kinds and three separate methods. |
| `REQ-4003` | A process fixture builds a plan from an exact first-party setup and rejects a component ID outside the graph. |
| `REQ-4004` | A run without confirmation or with a stale digest is refused; a rerun returns the same run and a single evidence row. |
| `REQ-4005` | Local-static checks pass, model/human checks receive `not_run`, and the overall status is `degraded`. |
| `REQ-4006` | The machine-readable result passes schema validation and contains exact coordinates, a result digest, and two explicit negative indicators for mutation and permission use. |
