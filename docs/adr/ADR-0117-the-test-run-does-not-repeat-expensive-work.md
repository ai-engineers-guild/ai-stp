---
description: "Decision not to repeat expensive work in a run: migrations are applied once per process, and coverage tracing uses sys.monitoring."
last_verified: "2026-08-29"
---

# ADR-0117: The run does not repeat expensive work

Status: accepted. Clarifies, with respect to run cost, a decision that belongs
to private infrastructure and is not published here. The decisions to
distribute tests across processes and keep the coverage threshold unchanged
remain unchanged.

## Context

After removing the chain between jobs, the run cost was determined by two
repetitions of the same work, both visible in the code before any measurement.

Every test that needed PostgreSQL reapplied the entire Alembic chain:
`migrated_database_url` created an empty database and ran `command.upgrade` for
every test. Under xdist, this cost was multiplied by the number of workers
against a single PostgreSQL instance.

Coverage tracing used the `ctrace` backend, the historical default of
coverage.py. An earlier measurement had already shown that collecting coverage
cost about a third of the gate time (787.89 s versus 547.92 s without it), but
the backend itself had not been selected.

## Decision

Two changes; each was measured before adoption. Unless stated otherwise, the
figures below are from a local run on pinned versions (pytest 9.1.1,
pytest-cov 7.1.0, coverage 7.15.3, Python 3.12).

**Migrations are applied once per process.** The session-scoped fixture
`pg_migrated_template` in both platform conftests applies the Alembic chain to
one database per xdist worker; `migrated_database_url` creates the test database
as a `CREATE DATABASE ... TEMPLATE` clone—file copying instead of repeating
migrations. Measurement on the DB slice (`tests/api/platform` +
`tests/integration`, PostgreSQL 16, `-n 4`, without coverage): **346.15 s with
repetition for every test versus 99.50 s with the template—3.48 times faster**;
the test set was green in both cases. Isolation is not weakened: each test
still has its own database, which is destroyed afterward; the test that checks
the migrations themselves uses an empty database via `isolated_database_url`
and deliberately pays the full cost.

**Coverage tracing uses sys.monitoring.** `COVERAGE_CORE=sysmon` (the default is
set in `justfile` and in `[tool.coverage.run] core`, and can be overridden by
`AI_STP_TEST_COVERAGE_CORE`). Measurement of the full set without a database,
`-n 4`: 547.94 s on `ctrace` versus **521.97 s on `sysmon`**, with coverage
matching to the hundredth (87.09% in both). The gain is below the threshold
that would usually justify changing a mechanism, and the decision was not made
for these four percent: the data is identical, the risk is zero, and tracing
accounts for a larger share of time on the slower runner, where the effect is
expected to exceed the local result. The CI figure will be an observation from
the first run; if it is worse, reverting is a one-word change in `justfile`.

`concurrency = ["greenlet"]` in `[tool.coverage.run]` makes sysmon impossible:
coverage 7.15 refuses sysmon with that concurrency and falls back to `ctrace`.
Consequently, the run—locally on 3.12 through the `justfile` export and in CI
on 3.14, where sysmon is already the coverage.py default—paid for the slower
core plus a warning on every xdist worker. `greenlet` was removed from
concurrency; `thread` remains. Intersections across `await` in SQLAlchemy
asyncio are no longer reached by this plugin: that is the cost of the selected
core.

Also recorded and rejected: scaling from 4 to 8 workers yielded only 410.85 s
versus 521.97 s (1.27x instead of 2x)—the set is constrained by a tail of CLI
subprocess tests, not by the number of cores. The local worker count is not
increased further; the next multiplicative gain can come only from sharding
between jobs, and the `back-durations` recipe already writes durations for
duration-based splitting.

## Rejected alternative

Deduplicating the `back-python-3.12` matrix leg was considered and implemented
on the old private gate: static checks, wheel builds, and install regression do
not depend on the interpreter version and lived in `package`, so the leg should
have run only tests. While the work was in progress, the gate moved to the
public tree (`ADR-0110`) and the leg disappeared with the entire matrix—the
public gate runs every recipe exactly once by construction (`ADR-0113`). The
change lost its target and was withdrawn; the conclusion remains a rule:
repeating version-independent work in a run is a shape error fixed by removing
the repetition, not by speeding up every instance.

## Consequences

The DB portion of the run becomes roughly three times faster. The coverage
threshold, test-set composition, and isolation semantics do not change; the
threshold is checked in the same way.

The full set with PostgreSQL on Windows, Python 3.12, `-n 4`: **636 s** while
`concurrency=greenlet` disabled sysmon, versus **522 s** after its removal,
with 93.44% coverage.

The root conftest automatically applies the `pg` marker through fixture
closure, so selecting the "set without a database" cannot diverge from the
tests' actual requirements.

The cost of the decision is one session-scoped database per worker, which
lives until the process ends and is removed during teardown. Concurrent clones
from one template are safe: no process is connected to the source while it is
being copied.
