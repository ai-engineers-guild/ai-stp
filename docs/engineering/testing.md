---
description: "Test strategy for passports, builds, sync, providers, and platform."
last_verified: "2026-08-27"
---

# Testing

## Levels

| Level | Purpose |
|---|---|
| Unit | Pure rules and transformations without I/O, clocks, or network. |
| Property | Digest, merge, version, graph, and state-machine invariants. |
| Integration | SQLite/PostgreSQL, filesystem, object storage, OAuth adapters. |
| API | ASGI-level via httpx AsyncClient against app factory: envelope, errors, health. |
| Scenario | End-to-end flows between platform slices in a single process. |
| Contract | CLI JSON, API, schemas, provider protocol, OpenAPI parity against `#71` fixtures. |
| E2E | Main user paths. |
| Security | Paths, authz, tenant isolation, archive and subprocess boundaries. |
| Fault | Crash, timeout, stale plan, partial apply, retry. |
| Phase | Selection of evidence by roadmap phase through the phase marker. |
| Golden | Passports, plans, bundles, conversion reports. |

## Mandatory Scenarios

- The passport retains the origin when moving to confirmed;
- Changing the passport does not change the public profile;
- duplicate `X.Y` with a new digest is rejected;
- The link to the setup version does not contain a variant, and the list of component types does not contain `marketplace`;
- An unverified object enters the output only with explicit consent and does not enter the automatic setup;
- Two devices store different environments without changing or conflicting with the developer's passport;
- Canceling a recommendation session does not create a version, and confirmation atomically creates exactly one;
- Consent areas `publisher` and `object_major` differ, and extension of privileges requires a new decision;
- the right to the `X` line does not open `X+1`, a fork does not change the original, a revocation preserves local data;
- the complaint contains no secrets or paths and does not change the version state without moderator action;
- expiration of mandatory proof blocks new installations without disabling the installed target;
- every type of component and MCP transport class is covered by the verification policy;
- arbitrary graph detects all conflict classes;
- the invitation does not grant access until the address is confirmed by login;
- the index sees a mixed tree of extensions and excludes secrets, cache, and generated results;
- autonomous path works after network disconnection;
- stale plan is not applied;
- backup/restore preserves unmanaged state;
- revoked device does not synchronize;
- three-way merge does not lose changes;
- partial operation is not reported as success;
- old/new schema/API compatibility;
- Linux x86_64 E2E for all five release lines;
- portable Windows fixtures for `.exe`, `.cmd`, npm/Scoop metadata, and Codex Desktop `WindowsApps`, with mandatory `version_source` and diagnostics;
- manual macOS portability evidence until future expansion of the support matrix.

## Platform and CLI Separation

Server platform tests are separated from CLI tests by subdirectories `tests/<level>/platform/` and `tests/<level>/cli/` and markers `platform` and `cli`. A conftest from one area is not imported into another, so platform and CLI fixtures do not mix. The conftest hierarchy is as follows: the root registers markers and deterministic helpers, the platform provides the application factory, asynchronous client, and database and queue fixtures, and the level boundaries do not cross.
Database isolation remains for the test, but its cost does not: the Alembic chain is applied once per process in the migrated template (`pg_migrated_template`), and each test receives its own database as a clone of `CREATE DATABASE ... TEMPLATE`. A test that checks the migrations themselves works with an empty database via `isolated_database_url` and applies them itself — it is the only one that pays the full cost again. Coverage tracing goes through `sysmon` and is incompatible with `concurrency=greenlet`. The solution and cost measurements — `docs/adr/ADR-0117-the-test-run-does-not-repeat-expensive-work.md`. The public gate runs the server set only on Linux, split into shards, while CLI and web tests run on three OSes (`docs/adr/ADR-0116-the-gate-spends-runners-on-os-and-shards.md`).

The need for PostgreSQL is not supported by a manual list: the root conftest sets the marker `pg` via the fixture closure of the test, so `-m "not pg"` selects the set for which the database is not needed, exactly as much as it is actually needed.

## Test Rules

- Immutable non-naive tests without hardcoding: expected values are derived from constants and `ai_stp_foundation` registries and from builders, not copied as literals; error codes are taken from the registry, not written as a string.
- Determinism and absence of flakiness: no `sleep`, only waiting for conditions and events; frozen clocks; seeded randomness; no real network; test database isolation via transaction with rollback; no shared mutable global state.
- If a large suite fails or hangs, apply the described one-time fallback — one collection, 20 stable ordered shards, identical environment, no coverage only for localization, log outcome/duration, then narrow reproduction and root-cause fix; sleep, blind retry, and constant sharding without proof are prohibited.
- Actual behavior and minimal mocks: only the external service is mocked, but never the unit under test.
- Names and grouping: use `test_<subject>_<condition>_<expectation>` and group by behavior, not by method.
- Meaningful checks of observed behavior and invariants, not random structure.
- Each acceptance line `REQ-*` has at least one executable test, and contract tests are tied to fixtures `#71`.

The test should name the failure that will make it red.

## Can the check fail

The above rules indicate that the test checks. These — whether it can turn red at all.
Each is written based on a measured case; none is derived from principle.

- **Justification for skipping is a statement, and no one verifies it.**
  `pytest.skip("a rejection carries no body")` triggered by `body is None`:
  condition and explanation are separate statements, and the acceptance case has no body
would be skipped under a phrase that is false about it. The skip must assert what it says.
- **A number from a fixture, recorded as an invariant, cannot fall.**
  `minimum_sequence(...) == 1` was correct precisely because the only manifest that the check encountered was a fixture with `sequence` 1. Against the released version — 7. One should assert the connection (`== manifest.sequence`), not the observed value.
- **A check that has never encountered reality is a habit, not proof.** Twelve inter-repository life cycle tests were skipped in every CI run throughout the repository's history because `AI_STP_*_PROVIDER_V3` is not set anywhere. When run against signed releases, they immediately found two defects.
- **A new watchdog is falsified by returning a defect, and the mutation must assert that it was applied — and that it hit where it was intended.** One
`str.replace` did not match because the call was split over multiple lines by the formatter; the guard "passed" without being checked even once. The second time the pattern matched, but it appeared in three lists, and the edit went into the first: the test passed again, and again it was not checked. You also need to check that the mutation ended up inside the correct block.
- **Measure what is being delivered, otherwise you measured something else.** The adjacent system was taking the fixed artifacts `urllib`, while they were always checked manually `curl`; the vendor's CDN responds `403` to `Python-urllib/3.x` and delivers the same URL `curl`. The delivered path was checked only against one source that distributed everything indiscriminately, and the other six — never. The tool was not the one under inspection.
- **The counter is not a verdict, and `|` swallows the return code.** The chain of checks,
ending with `clippy … | grep -c`, prints `2` and exits with zero: the number was on the screen, and the commit was already gone. The tool is working correctly here — the verdict lost the pipeline. You need to check the status of the last command, not the one to the left of the pipe.
- **A gate is a recipe, not a list in a document.** `just check` unfolds into `back-check` of five recipes; for three days in a row, two of them were run and called "all gates." The document lists checks that a person needs to know about; `justfile` owns the composition.
- **Suspect the tool first.** When an item looks broken, the first hypothesis is measurement. Over two days: `strings` does not find the serde key because the keys are not in continuous literals; `-rs` collapses identical reasons and puts a counter in parentheses, so the lines are not tests; `provider
conformance` without `--protocol-version 3` checks the v3 provider with a set of v1 fields and declares a working release broken; `PATH` does not hide anything without `/usr/bin` as long as `/bin` refers to it.
- **Agreement of two tables is proof that neither has shifted, and not proof of anything about the vendor.** Reconciliation of `PROVIDER_RULES` with the catalog was done on a couple of rows, both equally incorrect. A watchdog reconciling with a table that the repository does not own is stronger — but it also catches discrepancies, not the general error.
- **An exception list that no one shortens becomes a place where things are hidden.** Every exception set has a paired check: a record whose basis has disappeared must turn red. The artifact of proof does not forgive its known failure — otherwise green means "we agreed not to look."
