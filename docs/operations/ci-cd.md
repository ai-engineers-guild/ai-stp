---
description: "Checks and release order for compatible changes."
last_verified: "2026-08-25"
---

# CI and releases

## Before code exists

The following are required:

- documentation integrity;
- absence of placeholders;
- Markdown/YAML;
- Mermaid;
- correct indexes.

## After code bootstrap

The following are added:

- format/lint/type;
- unit/property;
- SQLite/PostgreSQL integration;
- schema/golden;
- API contract;
- provider contract;
- security;
- package/install;
- Linux x86_64 matrix;
- the manual CLI/package workflow on a standard GitHub macOS runner through `macos-evidence.yml` remains
  future portability evidence and does not block the current release under `ADR-0062`;
- real provider E2E remains separate release evidence.

The release candidate is built by a separate manual run, and both of its jobs—
build and attestation through OIDC—run on `nddev-linux-standard` using different
one-shot runners under `ADR-0101`. The separation of duties from `ADR-0048`
is preserved: the build receives no OIDC, while attestation performs no checkout and sees
only the bytes from the previous job.
The `release-candidate` workflow builds and attests the candidate. Publication to PyPI is
a separate manual `publish-pypi.yml`; the contract, environments, and upload order
belong to the `pypi-release.md` runbook.

## Required `runs-on` targets

The separation of trust domains under `ADR-0046` is preserved, but it is not
implemented by one physical role per target. Combining roles on one persistent host
remains prohibited; a job on a fleet class receives a one-shot runner
that is destroyed with it, so two jobs in the same class share neither
host, user, nor filesystem (`ADR-0080`, `ADR-0101`).

The fleet is named NDDev Drakkars. Classes are policy surfaces, not
hardware partitions: a name compiles into capability and trust predicates, while capacity
is shared (`ADR-0102`). The runner type is therefore listed separately from the class—it
determines whether the class has Docker.

| `runs-on` target | Type | What it runs |
|---|---|---|
| `nddev-linux-integration` | Drakkars class, one-shot Docker-capable container per job | `check`, `back-python-3.12`, `fleet-egress-probe` |
| `nddev-linux-standard` | Drakkars class, one-shot container per job, without Docker | `deploy/verify-public`, `release-candidate/build`, `release-candidate/attest`, `fleet-class-probe` |
| `nddev-linux-fast` | Drakkars class, one-shot container per job, without Docker or job credentials | `fleet-class-probe` |
| `macos-15` | standard GitHub-hosted fallback until a fleet macOS class exists | `macos-evidence` |
| `ubuntu-latest` | standard GitHub-hosted | `codeql`, only on the public mirror |

No required job targets `nddev-linux-fast`. The class accepts
assignment and does not create a worker (`NDDev-it-com/github-actions#318`), which has already
cost one run whose two substantive jobs were green. It
remains only in the probe because the probe is the only way to detect its
return.

The two notation forms are not interchangeable. A scale set is addressed by name and written as a
single string; a persistent role is addressed by a set of labels and written as a list
`[self-hosted, …]`. A list pointing to a scale set name finds nothing.

The production host is not an Actions runner. After a green `check`, the release job
advances the monotonic `deploy/prod`, and a host-side timer fetches it with a read-only
key and deploys the exact SHA (`ADR-0103`). `verify-public` then waits for the origin
to answer with the promoted commit or a descendant of it. The wait is bounded by
measurement, not by the timer's tick: one roll of the host — pull, image build,
migrate, bring-up — measured 29 minutes on 2026-09-01, and because the host deploys
serially and always takes the newest ref, a promotion that lands mid-roll waits for
that roll and then for its own, never more. The bound is two rolls; a second push
inside that window is verified through the descendant that overtook it.

Checks were moved to an ephemeral scale set under `ADR-0080`, and the migration is effective:
the scale set serves jobs for this repository, `back-python-3.12` passes on it
in full, and `check` reaches a terminal verdict.

`check` runs inside the Playwright image pinned to the exact version from
`apps/web/bun.lock`. The reason is `#349`: the ephemeral machine image lacks Playwright
system packages, so Chromium was downloaded but could not start. The `justfile`
installs the browser bytes and intentionally does not install system packages—the repository
check may not call `sudo`, and that boundary is preserved. The packages come from
the image, so the fix remains inside the repository and does not wait for a fleet image.
Browsers come from `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright` rather than being downloaded
again by every run. A test verifies that the image tag matches the lockfile:
a mismatch would pair one browser build with a different set of libraries.

A container job reaches a service by name and its own port
(`postgres:5432`), not by the port published on the host: inside the container, loopback
would point to the job itself. A job without a container retains the previous form. The dated
fleet observation is `docs/engineering/runner-separation-readiness.md`. The
`ai-engineers-guild` tenant owns its own GitHub App and credential in the fleet and, since
2026-08-16, serves the entire account rather than one repository: in the fleet this is
`ServesWholeAccount`, which supersedes the earlier `ADR-0080` statement about
a rejected organization entity.

The class is selected by required capability (`ADR-0100`), and both required
jobs need the same combination: Docker plus job credentials for checking out a private
repository. Only `integration` has that combination, so the required
run depends on exactly one class (`ADR-0102`).

The gate here is represented by **two jobs** and checks only the unpublished half
(`ADR-0110`). The code is proven in the public repository on standard GitHub runners,
including a three-OS matrix that the fleet does not have at all.

| Job | What it runs | Why it is needed specifically here |
|---|---|---|
| `docs` | `docs-check` checks directly | there are more documents here, and the indexes enumerate them |
| `package` | `back-static` checks, build, and clean installation directly | static checks run the publication report and lint unpublished code |

The workflow does not invoke the local task runner: `just` is a maintainer-machine
convenience, not a dependency of the published gate. Each job executes the recipe
commands directly; the clean-install body lives in
`release_scripts/clean_install_regress.sh`, which is called by both `just
back-regress` and the workflow, so the local and CI paths cannot diverge.
On Windows, `just back-regress` locates Git-for-Windows bash through
`release_scripts/run_bash.py` and does not invoke the `bash` on PATH: that is often
WSL and cannot see this tree.

`back-test`, `web`, and `back-python-3.12` were removed. On the mirror, they ran exactly what
the public gate runs on the same content; forty-two minutes of machine
time on the fleet's most constrained class for a second copy of an existing verdict
was the substance of `#361`.

Consolidation is checked mechanically against the published gate: the leaves of `just
check` are expanded from the justfile, each leaf is mapped to distinctive
commands from its body, and all of them must be present in the workflow
(`tests/contract/test_gate_split_covers_the_gate.py`). The converse is also checked:
no published workflow contains a call to `just`. Dropping a check from
the gate or returning a runner breaks the contract.
`just setup` is split into `setup-python`, `setup-docs`, and `setup-web`, and each job
prepares only its own part.

Splitting jobs by required capability (`ADR-0105`) and avoiding `needs`
(`ADR-0104`) remain in force and now describe the public gate: independent
checks do not wait for each other, and the run's wall-clock time is the duration of the
longest job. There is one exception, based on data rather than ordering: `coverage`
collects the `.coverage.*` files from the Linux `tests` shards and only then checks the 90%
threshold, because the threshold is a property of the union, not a fragment.

The shape of the public gate is defined by `ADR-0116`. The server suite runs only on Linux and is split
into seven jobs (`api`, `integration`, `unit-platform`, `unit-api`, `unit`,
`contract`, `property`) with eight xdist processes each. CLI and web tests
(`web-unit`, `web-e2e`, `web-profiles`) run on Linux, macOS, and Windows simultaneously;
web static analysis and Storybook remain Linux-only. The CLI process contract is a separate
`cli-process` leg. `unit` does not include `tests/unit/platform` or `tests/unit/api`:
these are Linux tests with a database, not the cross-platform CLI surface.

E2E on one OS remains one job for a measured reason: `--shard` distributes
only tests designed for parallelism, while this suite is serial by design
(process-local mock state)—in the probe, both shards ran the entire suite,
matching `playwright#30253`; expansion on one OS is possible only by
explicitly splitting specs between jobs.

Class availability for this account is checked by running
`.github/workflows/fleet-class-probe.yml` and is a measurement, not a reading
of someone else's table: an unregistered or broken name does not fail but waits
forever, and a class that correctly serves another tenant promises us
nothing.

CodeQL static analysis lives in `.github/workflows/codeql.yml` and is not part of the
gate: a finding must not look like a broken `check`. The query suite is
`security-extended`, not `security-and-quality`. The job runs on `ubuntu-latest` and
only if the repository is public: Code scanning is unavailable on the free private plan,
and this analysis does not need the `integration` class. The file lives in this tree
so the public mirror does not maintain its own workflow.

`deploy.yml` advances `deploy/prod` only if the completed `check` was a
`push` to `main`. This condition is on the `promote` job, not only in shell;
only it has `contents: write`. `verify-public` has read access only.

There is no separate aggregation job. The run verdict is already the conjunction
of its jobs. A single branch-protection context (`#188`) will be needed when protection
exists; today `main` has neither protection nor required contexts (`#361`), and
a job required by nothing cost an entire green run on a class that did not schedule it
(`ADR-0102`).

This run no longer starts deployments. The public repository advances `deploy/prod`
and deploys production (`ADR-0109`); a green `check`
here is a verdict on the tree and nothing more.

An unregistered target does not produce an error: the job queues and waits
indefinitely, and the run appears unfinished rather than failed. Therefore, an absent
role is recorded as an open external release barrier, not a temporary
delay, and the target is not moved to a runner with another role merely to get a green run.

## Cross-repository order

1. change and release the provider contract;
2. update the public setup-system repository;
3. release the signed provider artifact;
4. update the allowlist/manifest in `ai_stp`;
5. run integration tests;
6. only then promote the release.

The step “confirm in the closed authoring environment” no longer exists here: that environment
is named as a role, not a repository, and is not a dependency, submodule, or
runtime source. The artifact's own `provider-info` confirms the release.

Green Linux CI is not proof of macOS. Missing macOS evidence
is called `not_verified` and does not become a support claim.
