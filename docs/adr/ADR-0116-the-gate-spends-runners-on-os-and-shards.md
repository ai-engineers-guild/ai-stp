---
description: "Decision to run CLI and web tests concurrently on three operating systems, and the server suite only on Linux, split into shards without conserving runners."
last_verified: "2026-09-04"
---

# ADR-0116: The gate spends runners on operating systems and shards

Status: accepted. Clarifies `ADR-0113` and, regarding job shape, two decisions
that belong to private infrastructure and are not published here, specifying
which jobs run on which operating systems and how many run concurrently. The
90% fail-under consequence is superseded by `ADR-0147`. Combining Linux shards
into one coverage report remains.

## Context

The public gate already ran in parallel, but not in a form that reduced wall
time. Web tests ran only on Linux. The server suite had three large shards on
four processes. The CLI on macOS was bottlenecked by `tests/contract`, dominated
by its process-heavy tail. The four vCPUs of one job would be idle while
adjacent work could run on another machine.

`ADR-0113` proved the CLI surface on three operating systems. Browser and web
unit tests observe the filesystem, fonts, Chrome, and paths just as the CLI
observes encoding and the keyring: a Linux run cannot see these differences.

## Decision

**CLI tests and web tests run concurrently on Linux, macOS, and Windows.** The
legs do not wait for one another. Web static checks (lint, types, production
build, audit, Storybook) remain Linux-only: they are not an OS-dependent
surface.

**The server lane is Linux-only.** PostgreSQL, ASGI, and platform unit tests do
not prove a Windows or Darwin server runtime. They are split into separate jobs
by the test tree: `api`, `integration`, `unit-platform`, `unit-api`, `unit`,
`contract-process`, `contract-lifecycle`, `contract`, `property`. Each job uses
eight xdist processes on a standard four-core runner: the tests wait on the
database and processes, cores are not the bottleneck, and conserving runner
minutes here is explicitly prohibited.

`tests/contract` is split into three because the tree is heterogeneous: with
eight processes, `test_cli_process.py` takes 107 s,
`test_offline_closure.py` together with `test_installation_restart.py` takes
65 s, and everything else takes 23 s. As a whole, the shard took as long as the
sum and was the gate's second-longest job. Splitting by file timing rather than
directory names follows the same rule: the bottleneck is measured, not guessed.

The shard set is configuration, not a contract. The contract is that the shards
cover the `tests/` tree exactly once and that `coverage` lists them all; both
are checked mechanically.

**The CLI process contract is a separate matrix leg.**
`tests/contract/test_cli_process.py` does not share a machine with the rest of
`tests/contract`. This is the only multiplicative gain for macOS that does not
require more cores within one job.

Coverage remains a property of combining the Linux shards: `coverage`
gathers the artifacts and then prints one total. A percentage does not
fail the job (`ADR-0147`). The web and CLI matrices do not write coverage.

The provider support matrix does not change (`ADR-0062`, `ADR-0113`): three
operating systems in the gate prove the client surface, not installation
through a signed provider release.

## Consequences

Wall time is the longest leg plus queue time when concurrent jobs exceed the
host limit. This is an accepted cost. Removing an OS leg from web tests or
merging the server shards back into three is a regression of this decision.

The limit is measured, not assumed: peak concurrency in the public repository
is 20 jobs, and 5 for macOS. The 34-job gate reaches both. This yields a
counterintuitive consequence: **splitting a leg into more shards does not reduce
wall time while the run is at the concurrency limit**—it merely moves the same
work to other slots and lengthens the queue. Verified: splitting `web-e2e` into
four shards instead of two produced 269 s versus 262 s on the longest leg and
increased the run from 5.6 to 6.08 minutes. Splitting is useful only for a
heterogeneous leg whose sum is substantially greater than the maximum of its
parts.

What actually shortens a run under this limit is reducing total job-seconds,
not the number of jobs. Therefore the fixed setup of each leg is counted on the
same basis as its tests.

Required status checks use the actually rendered job names, including the OS in
parentheses and the shard in the `tests-*` name.

## Reconsideration conditions

Reconsider if the standard GitHub-hosted runner changes its core count, if the
process contract ceases to dominate `tests/contract`, or if paid larger runners
become more economical for one large job than a set of shards.
