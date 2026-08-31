---
description: "SPEC-003: Developer passport and public projection."
last_verified: "2026-08-29"
---

# SPEC-003: Developer Passport and Public Projection

## Purpose

The system stores a private, versioned, and explainable profile of how the user works with agents, automatically collects safely observable facts, and asks only for missing mandatory decisions.

## Scope

The scope includes the role, typical tasks, preferences, preferred languages and harnesses, permissions, and decision history—the user's cross-device facts. Source conversations, secret values, full shell history, and automatic publication are out of scope. Observable facts about a device's environment belong to the device passport under `ADR-0025` and `SPEC-002`.

## Terms

- `DeveloperPassport` — the private canonical object.
- `Fact` — a value with provenance, confirmation, and source links.
- `PublicProfile` — a separate object that the user fills in themselves.

## Requirements

- `REQ-301`: The passport is private by default and accessible only to its owner and authorized administrative operations.
- `REQ-302`: The passport has a stable ID, a schema version, and immutable revisions with parents.
- `REQ-303`: A fact stores provenance as `declared`, `observed`, `derived`, or `imported` and confirmation as `none` or `user_confirmed` as two independent axes, as well as limited source links and observation and confirmation timestamps.
- `REQ-304`: The passport stores the role, typical tasks, priorities, preferred languages and harnesses as declared preferences, permissions, and the history of accepted and rejected decisions; it does not contain the observed OS/architecture, installed harnesses, or tool versions.
- `REQ-305`: The CLI deterministically discovers safe facts and findings, the agent interprets them and completes the passport, and the user confirms unknown mandatory values and risky preferences.
- `REQ-306`: The public profile is a separate object, is populated by an explicit action, and does not receive passport fields automatically; an empty profile means that no public profile exists.
- `REQ-307`: Source conversations, secret values, full shell history, and optional source content are not collected.
- `REQ-308`: The CLI, passports, local core, and mandatory server operations do not invoke model interfaces and do not require a model key; optional server presentation enrichment is limited to `SPEC-053`, and its absence does not degrade any passport function.
- `REQ-309`: A materially changed repeated observation resets confirmation to `none` and exposes the discrepancy instead of silently carrying confirmation forward.
- `REQ-310`: The public profile has a closed list of fields defined by `docs/contracts/public-profile.md`; arbitrary metadata and fields "for the future" are not allowed.
- `REQ-311`: A finding is an observation with provenance `observed` and confirmation `none` that has not yet been recorded in the passport; there is no separate finding entity.
- `REQ-312`: An observed environment fact is recorded in the current device's passport; rescanning on any device does not change the developer passport or create a revision conflict in it.

## States and errors

The passport has `draft`, `complete`, `conflict`, and `tombstoned` states. An unknown fact is not replaced with a guessed value. A conflict between concurrent revisions returns both heads and their common ancestor. An unsupported schema major version blocks writes while preserving access to the raw payload for recovery.

## Security and privacy

Automatic discovery is limited by a field allowlist. Values from the environment, token stores, and credential files are not read. By default, no public profile exists: its content appears only through an explicit user action, not through disclosure of passport sections.

## Compatibility and migration

Adding an optional field is forward-compatible. Renaming a field or changing its meaning requires a schema migration that preserves provenance. An old client must not delete unknown fields during a round-trip.

## Acceptance criteria

| Requirement | Executable oracle |
|---|---|
| `REQ-301` | Authorization tests reject passport reads by an unrelated account. |
| `REQ-302` | Round-trip/property tests verify the stable ID, revision parents, and canonical digest. |
| `REQ-303` | Schema tests accept only the allowed values for both axes and preserve source links. |
| `REQ-304` | The golden fixture contains only personal sections, and the schema rejects an observed OS, architecture, or installed harness version field. |
| `REQ-305` | A CLI test separates discovered facts and findings from agent questions and user confirmations. |
| `REQ-306` | Changing the passport does not change any public profile field, and an unpopulated profile is not served as a public page. |
| `REQ-307` | Negative fixtures containing `.env`, shell history, and transcripts do not appear in output. |
| `REQ-308` | A dependency-closure check for the CLI and passport/server-core configuration rejects a model client and a model-key requirement; a separate `SPEC-053` check prevents optional worker enrichment from becoming their dependency. |
| `REQ-309` | A rescan fixture resets confirmation to `none` and preserves provenance. |
| `REQ-310` | The profile schema rejects an unknown field, and a profile without substantive fields is not served as a public page. |
| `REQ-311` | A finding and a recorded fact differ only on the two axes and do not have separate schemas. |
| `REQ-312` | A fixture with two devices in different environments creates neither a change nor a conflict in the developer passport. |
