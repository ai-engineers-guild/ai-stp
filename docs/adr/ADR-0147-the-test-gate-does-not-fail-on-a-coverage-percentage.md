---
description: "Decision that Python coverage is reported by the gate and does not fail a run on a percentage."
last_verified: "2026-09-04"
---

# ADR-0147: The test gate does not fail on a coverage percentage

Status: accepted. Supersedes the 90% fail-under consequence of `ADR-0116`.
It does not supersede combining Linux shards into one report, `sysmon`
tracing (`ADR-0117`), or the Vitest catalog threshold.

## Context

`just back-test` and the public `coverage` job failed the tree when combined
Python coverage rounded below 90%. That number was a project-owner setting,
not a product invariant. New work that is correct but not yet densely tested
could not land. The owner will raise coverage later as a separate effort.

## Decision

**A Python coverage percentage does not fail `just back-test` or public
`check`.** Coverage is still collected on `packages/` and `apps/`, combined
from the Linux shards, and printed at `precision = 2`. Missing shard artifacts
still fail the combine step. Skipped PostgreSQL tests still skip; they no
longer fail the run by lowering a percentage gate.

`--cov-fail-under` is absent from pytest `addopts`. `coverage report` does
not pass `--fail-under`. Shards do not restore a percentage gate.

Web Vitest thresholds are unchanged.

## Consequences

- A green `back-test` means the tests that ran passed, not that a coverage
  floor was met.
- Re-introducing a percentage fail-under is a new owner decision and a new
  ADR. If restored, compare at `precision = 2`; `precision = 0` reprints
  failure and can still exit 0.

## Reconsideration conditions

Reconsider if a measured coverage drop starts hiding missing tests the
product actually needs, or if a later owner sets an explicit floor.
