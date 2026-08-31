---
description: "Immutable architectural rules of ai_stp."
last_verified: "2026-08-03"
---

# Architectural Principles

## One Product, Modular Boundaries

CLI, API, worker, and web are parts of one product. They share a domain model, while entrypoints and dependencies remain separate.

## Ownership by Function

Each module owns its behavior, schemas, and ports. A shared `domain` or `common` package that knows about everything is forbidden.

## Local Mode Is Complete

Basic passports, the index, registry, selection, compilation, and installation do not require an account. The cloud extends rather than replaces the local product.

## Immutable Versions

Published versions and applied bundles are addressed by digest. Mutable lifecycle state is stored separately.

## One Target Writer

Only the provider for a specific harness changes its target. `ai_stp`, the Agent, external resolvers, and the server do not write to the target concurrently.

## Plan Before Writing

Every mutating operation goes through inspection, plan construction, user decision, locking, revalidation, application, result verification, and journal completion.

## The Agent Is Not a Policy Mechanism

The Agent asks questions and proposes a composition. Hard constraints, access, digest, schema, conflicts, and provider preconditions are checked deterministically.

## Honest Unknown States

`unknown`, `not_run`, `degraded`, `not_verified`, and `partial` are first-class states. They must not be converted into a successful result.

## Four Independent State Axes

States are not mixed across axes, and the same word means different things on different axes:

| Axis | Values | Owner |
|---|---|---|
| Local environment readiness | `ready`, `needs_input`, `degraded`, `unsupported`, `failed` | `SPEC-001` |
| Individual check result | `passed`, `warning`, `failed`, `degraded`, `not_run` | `SPEC-007` |
| Mutating operation | `planned`, `approved`, `applying`, `applied_unverified`, `verified`, `partial`, `failed`, `stale`, `cancelled`, `rolled_back` | `contracts/operation.md` |
| Release-line evidence | `verified`, `not_verified` | `engineering/release-evidence.md` |

`degraded` describes the environment on the first axis and a specific check on the second. A `failed` check does not make an operation `failed`. An operation's `verified` state is not release evidence: a line that was not run receives `not_verified`, regardless of how many operations completed successfully.

## Least Privilege

Core is installed in user-owned directories. `sudo` is not a normal mechanism. A password is never passed to the Agent.

## Compatibility by Contract

Schemas, the provider protocol, API, and sync are versioned. Simultaneous updates of all clients and repositories are not assumed.
