---
description: "SPEC-061: Estate-release complete requires the seven-harness launch matrix."
last_verified: "2026-09-08"
---

# SPEC-061: Estate-release qualification

## Purpose

Make the estate release record refuse `complete` unless every required
harness×OS×arch launch cell is present and passed. A scoped capability may
be absent; a required harness/OS workflow may not pass by skipping or
omitting the unavailable part.

## Scope

Included: `ai-stp-estate-release/2` verdict recomputation and the historical /1 reader, evidence row
`provider`, required `software` and `launch` slices, and the closed set of
seven attested OpenNetwork repositories. Excluded: tagging 0.1.0 or
0.0.65, executing Cursor or Antigravity binaries, inventing
`ANTIGRAVITY_*` environment variables, and platform/worker persistence.

## Terms

- Launch cell — one evidence row of slice `launch` keyed by attested
  `provider` repository, OS, and architecture.
- Known limitation — a string that explains a cell. It is not a cell.

## Requirements

- `REQ-6101`: `complete` requires `software` and `launch` in
  `required_slices`, the consumer distribution `{ai-stp-cli}`, exactly the
  seven attested OpenNetwork repositories, three primary `software` legs, and
  twenty-one passed `launch` cells (seven repositories × Linux x86_64,
  Windows x86_64 and macOS arm64) for schema /2 (ADR-0172). Legacy /1 records
  retain six legs. The other three platform pairs are not_verified.
- `REQ-6102`: A required launch cell that is missing, `skipped`, or
  `inconclusive`, or a launch row with an empty `provider`, cannot yield
  `complete`.
- `REQ-6103`: A required-platform evidence row with `result=failed` yields
  `failed` for /2. Historical /1 retains failure for any failed evidence row.
  `known_limitations` do not fill a missing cell and do not upgrade
  `failed` or `incomplete` to `complete`.
- `REQ-6104`: `EstateEvidenceRow.provider` is the attested repository
  identity. A launch row's `provider_tag` must match that provider's
  recorded tag. Historical records without `provider` remain parseable and
  cannot become `complete` without the matrix.

## States and errors

Verdicts remain `complete`, `incomplete`, and `failed`. The stored field is
a claim; `computed_verdict` is the decision. A validator that trusted the
written verdict is a defect.

## Security and privacy

The record contains repository names, commits, tags, and digests. It does
not contain secrets, tokens, or local paths.

## Compatibility and migration

New records use `ai-stp-estate-release/2` and explicitly name the three
not_verified platform pairs. Historical /1 records retain six required pairs.
`provider` defaults to empty; old incomplete records still validate. A stored `complete` that
lacks the launch matrix is rejected as a lying verdict. Historical Git
tags are not rewritten.

## Acceptance criteria

| Requirement | Executable verification method |
|---|---|
| `REQ-6101` | Unit test: software-only record is `incomplete`; seven providers plus all required passed launch cells plus software legs is `complete`; `REQUIRED_PROVIDERS` equals `provider-policy.toml` attestations. |
| `REQ-6102` | Unit test: omitting Antigravity, skipping Antigravity, or writing launch rows with an empty `provider` is `incomplete`. |
| `REQ-6103` | Unit test: failed Antigravity launch with a known-limitation string is `failed`; the same limitation with omitted cells is `incomplete`. |
| `REQ-6104` | Schema and model accept `provider`; a launch tag that does not match the named provider does not fill the cell. |
