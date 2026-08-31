---
description: "Required documentation updates alongside behavior, schemas, and operations."
last_verified: "2026-08-03"
---

# Documentation Maintenance

Documentation is part of a change, not a follow-up task. A PR that changes behavior, a contract, schema, configuration, dependency, command, provider, migration, deployment, or recovery must update every canonical owner of the affected information at the same time.

## Update Matrix

| Change | Required Owners |
|---|---|
| User-facing behavior or scope | `docs/product/`, active spec, and README when needed |
| Domain object or invariant | `docs/architecture/domain-model.md`, contract/schema, active spec |
| CLI/API/wire format | `docs/contracts/`, schema/OpenAPI, compatibility, and tests |
| Storage or migration | `SPEC-009`, migration plan, rollback, and runbook |
| Provider contract or pin | `docs/contracts/provider-protocol.md`, `docs/operations/provider-integration-state.md`, release evidence, and cross-repo issue |
| Security/privacy | `SECURITY.md`, `SPEC-013`, and negative tests |
| Development command or dependency | QUICKSTART, engineering docs, lock, and CI |
| Failure/recovery path | operation contract, observability, and runbook |

## Rules

- one normative fact has one canonical owner;
- other documents link to the owner rather than copying a large block;
- `index.md` is retained in every long-lived section and updated by the generator;
- `last_verified` changes only after the content has actually been verified;
- `last_verified` uses UTC rather than local time: east of the prime meridian, the local date leads UTC for several hours each day, so such a date can pass locally but be rejected by CI as a future date;
- an active specification is updated before implementation or replaced by a new version;
- an accepted architectural decision is not rewritten retroactively; a new ADR is created;
- an obsolete command is removed from every example in the same PR;
- generated output is not edited independently of its source;
- `just gen` and `just check` are run after the final documentation edit.

## Completion gate

A PR is not ready until the final diff confirms consistency across code, tests, schemas, documentation, runbooks, generated indexes, and release notes for the affected behavior. If a document does not need to change, the PR body briefly explains why.
