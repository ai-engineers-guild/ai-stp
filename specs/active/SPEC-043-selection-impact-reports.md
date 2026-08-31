---
description: "SPEC-043: Local reports for context budget, capability delta, and blast radius."
last_verified: "2026-08-15"
---

# SPEC-043: Selection impact reports

## Purpose

Before selecting or updating an exact `SetupVersion`, the agent can mechanically show changes in context and access, and, for an exact `ComponentVersion`, the local objects affected by an update or lifecycle event. The report selects nothing, does not change eligibility, and does not perform installation, update, or removal.

## Scope

The first implementation covers the local machine CLI and the shared contract. The personal baseline/delta and blast radius remain local: Web does not project account blast radius or display an installed baseline derived by the server (`SPEC-049`). The deterministic estimator is a single shared implementation for CLI and server; Web receives only the absolute budget of the visible exact setup. The local response does not represent itself as complete for the account. The report is not an eligibility check, does not select a setup, and does not write the target.

## Terms

- **Estimator profile** — version of the unit and deterministic counting method.
- **Price profile** — an explicitly provided price snapshot with a source and validity period.
- **Blast radius** — exact reverse references within the named authorization boundary.
- **Freshness** — the origin and timestamp of the snapshot, not a promise of global completeness.

## Requirements

- `REQ-4301`: The versioned estimator operates only on verified local artifact bytes. The `ai-stp:utf8-bytes/1` profile counts UTF-8 bytes exactly as its native units; `ai-stp:unicode-chars-div4/1` deterministically estimates tokens as the number of Unicode codepoints divided by four and rounded up.
- `REQ-4302`: The budget includes textual `instruction`, `skill`, `agent`, and `command` components. `instruction` is counted as always-loaded; the other three kinds are conditionally-loaded. Invalid UTF-8 is marked `unavailable`, not counted as zero.
- `REQ-4303`: The selection report contains the candidate's absolute budget and capability snapshot; when an exact baseline is available, it also contains its absolute values and the signed difference. The capability surface lists tools, MCP servers, hooks, external endpoints, credential requirements, and three permission categories without an aggregate risk score. The baseline is specified explicitly or derived for the project, first from the most recent verified installation and then from the current selection; the source remains visible in the response.
- `REQ-4304`: A price appears only from an explicitly supplied strict price profile containing model, source, `fetched_at`, and `expires_at`. An expired profile is marked `stale` and does not provide an amount; the absence of a price does not affect eligibility.
- `REQ-4305`: A blast radius request searches for exact reverse references only within the local registry: setup versions, selected projects, verified installed targets, and the local device. The authorization boundary and freshness are returned explicitly.
- `REQ-4306`: The `update`, `deprecation`, `blocked`, `expired_evidence`, and `advisory` scenarios have identical read-only behavior. `action=none` prohibits interpreting the report as an automatic update or removal.
- `REQ-4307`: A missing component, invalid passport digest, corrupted bytes, or an incomplete exact setup graph closes the entire report with a typed failure.
- `REQ-4308`: The machine CLI and other consumers use the same strict shared `SelectionImpactReport` and `BlastRadiusReport` schemas; private bytes are never sent to an external tokenizer or API. Server/Web do not publish `BlastRadiusReport` or an account blast-radius resource.

## States and errors

A measurement has the state `exact`, `estimated`, or `unavailable`; a price has the state `available`, `stale`, or `unavailable`. An unsupported profile and an incomplete baseline pair produce a validation error. An exact digest mismatch, a missing reference, or a corrupted artifact produces a conflict before the response is formed.

## Security and privacy

The estimator has no network transport. A price profile contains only a public rate and a source link, but no API key. Blast radius does not read another registry, does not disclose content bytes, and reports only local identifiers already accessible to the owner of the registry file.

## Compatibility and migration

Adding an estimator, currency, state, or report field requires a new contract version and an updated shared schema. The SQLite tables do not change: reverse references are computed from existing immutable versions, selections, and the operation log.

## Acceptance criteria

| Requirement | Executable evidence |
|---|---|
| `REQ-4301` | Unit tests pin both estimator profiles and a reproducible result. |
| `REQ-4302` | A textual artifact and an invalid artifact are distinguished as measured and unavailable. |
| `REQ-4303` | Shared-component fixtures verify absolute values and signed delta. |
| `REQ-4304` | Missing and stale price profiles do not return an amount. |
| `REQ-4305` | The reverse-reference test returns multiple setups and does not go beyond the local registry. |
| `REQ-4306` | Machine help declares read-only commands, and the schema fixes `action=none`. |
| `REQ-4307` | A changed exact digest fails without a partial report. |
| `REQ-4308` | Schema generation and the command registry reference the same contract models. |
