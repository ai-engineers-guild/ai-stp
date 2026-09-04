---
description: "Required checks and release evidence."
last_verified: "2026-09-04"
---

# Quality gates

## Documentation foundation

- frontmatter, links, and anchors;
- no unfinished placeholders;
- completeness and `index.md` parity;
- Markdown and YAML;
- actual Mermaid rendering;
- structure and traceability of active specs;
- semantic regressions: cancelled terms, branch parity, check-policy coverage,
  tracked session state, and returns of closed vision decisions—published
  mandatory `not_run`, indefinite consent, a permanent harness ceiling, reduced
  web, hard-coded counters, environment facts in the developer passport, an
  excluded complaint channel, and lost canonical decision contracts;
- unit tests for documentation validators;
- strict MkDocs build.

The semantic pass differs from the markup pass: it catches a return of an already
cancelled decision under a different word, which breaks neither links nor
frontmatter. History in `docs/adr/` is intentionally excluded: a replaced decision
must be able to describe what it replaced.

## Code after bootstrap

- Ruff format/check;
- Pyright strict;
- architecture imports;
- secret scan;
- dependency review, including the absence of a model-interface client;
- unit/property;
- integration;
- contract/schema/golden;
- security;
- package/install;
- E2E.

Since Phase 1, `just check` has included Ruff format/check and Pyright in one
`back-static` run (strict for `packages/`, `apps/`, and `tests/`, basic for
`docs_scripts/` until the validators are fully typed), pytest with unit, property,
contract, and golden checks (`back-test`), a coverage report for `packages/`
and `apps/` that does not fail on a percentage (`ADR-0147`, see below), byte
parity between `schemas/v1` and the models and the freshness of Skill projections
(both in `back-static`), and installation of the built wheel into a clean
environment (`back-regress`).

### Font redistribution conditions

`just fonts-licence` reads the `name` table of every tracked font and reports what
the file says about itself: records `0`, `7`, `13`, and `14` carry copyright,
trademark, license, and license URL information.

The check exists because a font is the only binary the repository usually carries
that can prohibit its own presence, and because a manual discovery is not repeated
once it has been done. Manual inspection found half as many files as `git ls-files`
because it looked at one directory.

It also found its own gap. Web font subsetting removes license text from record
`13` while leaving its URL in record `14`; for files the site actually serves, the
URL is often the only remaining statement of the terms. Until the check read it,
every OFL typeface looked `restricted` because of the phrase "all rights reserved"
in its copyright field.

Observed state: sixteen tracked files. Eight are typefaces served by the site: IBM
Plex Sans and IBM Plex Mono under OFL, `permissive`. The other eight are two copies
of the original typefaces in `docs/references/prototypes/`; the site does not serve
them, but the repository still distributes them. They remain an owner decision:
removal breaks prototype rendering, while retention is incompatible with public
visibility and AGPL.

Replacing the typefaces also closed the second problem: the replacements lacked
Cyrillic glyphs, so the Russian interface silently fell back to Arial. IBM Plex is
one superfamily, so the sans/mono relationship on which the brand relies survived
the replacement.

The recipe is intentionally outside `just check` and returns `0` by default.
Whether a restricted font remains in the repository is an owner licensing decision
with a cost, and a gate failing today would make that decision on the owner's
behalf. `--strict` returns a non-zero code and is intended for the release gate
after the decision is made. `fonttools` is supplied through `uv run --with` and is
not part of the project lockfile.

### Coverage is reported, not a fail gate

Coverage is collected on `packages/` and `apps/`, combined from the Linux
shards, and printed at `precision = 2`. A percentage does not fail
`just back-test` or public `check`
(`docs/adr/ADR-0147-the-test-gate-does-not-fail-on-a-coverage-percentage.md`).
The tracing core is `sysmon`
(`docs/adr/ADR-0117-the-test-run-does-not-repeat-expensive-work.md`);
`concurrency` must not contain `greenlet`, or coverage silently falls back to
`ctrace`.

The historical 90% fail-under compared a rounded total. That is why
`precision = 2` stays on the printed report if a floor is restored:
coverage's `should_fail_under` evaluates `round(total, precision) < fail_under`.
At the former default `precision = 0`, a threshold of `95` accepted `94.55`.
pytest-cov printed `FAIL Required test coverage of 95% not reached` and still
exited 0 (`letya999@6a41c28`). Two decimals narrow that band from half a percent
to `0.005`.

`back-test` still rereads the recorded data with
`coverage report --precision=2` so the local log matches the combined CI
report. It does not pass `--fail-under`.

The mandatory `back-resource` promotes both a direct `ResourceWarning` and a
`PytestUnraisableExceptionWarning` to errors: the SQLite finalizer in Python 3.13+
can wrap the first in the second, so one filter is insufficient. The gate runs only
the contract CLI lifecycle check, repeatedly invokes read commands in one process,
forces GC, and requires an unchanged number of open descriptors. This protects the
long-running agent process, not only the ordinary short-lived CLI process. Shared
`back-test` separately keeps `PytestUnraisableExceptionWarning` as an error for the
whole Python workspace.

Platform tests with PostgreSQL (`tests/api/platform`, `tests/integration/platform`)
read `AI_STP_TEST_DB_URL`. Without it they skip. The local DSN and container are in
`QUICKSTART.md`; CI starts `postgres:16` and sets the same URL.

Test isolation is defined by the repository, not by a test author's memory.
`tests/conftest.py` redirects XDG directories into a temporary tree and replaces
secret-store discovery, so no test reads the developer's configuration, identity,
or keys: reaching the real keyring would require deliberate effort. The resulting
code rule is that discovery is called through the module, not through a name
imported at load time—the name can no longer be replaced, and once `doctor` in
tests accessed the real store because of this.

`back-regress` installs wheels built by `back-build` in `dist/` and performs two
consecutive steps; the second sees what the first does not. The first exists because
the working environment contains the `docs` and `dev` dependency groups: an
undeclared package dependency is invisible there and appears only for someone who
installs the wheel. That is how the `yaml` import in `apps/cli` went unnoticed. The
step builds every package, installs `ai-stp-cli` into a clean venv, runs declared
commands, and checks that the installed closure has no model-interface client
(SPEC-011 REQ-1118). The second step installs the CLI using exactly the command
promised by the landing page and removes it again: it checks the PATH entry point,
operation outside the source tree, and that removal removes only program files.
Local data remains after removal—cleaning it is a separate explicit user action.
For `docs_scripts/`, only the ambiguous Cyrillic rules RUF001–RUF003 are disabled:
Russian is the documented prose language for validators.

Three contract documents own machine facts, and code is tied to them by checks: the
configuration field list with defaults (`cli-config.md`), the completion-class
table (`cli-json.md`), and the closed device summary (`device-passport.md`). Each
check has been tested to fail: two lists that match and are never checked are two
lists that will diverge, and the document is read before the code exists.

Hooks are separated by cost. `pre-commit` runs `docs-check` and `back-static`, but
not thousands of backend tests, wheel builds, or install regression. Full
`back-check` and `just check` run on push and in CI. The practical reason is simple:
a hook taking more than a minute is bypassed with `--no-verify`, and a bypassed hook
protects nothing.

The `LN002` rule in `docs_lint` requires a document name in backticks to point to an
existing file. Markdown link checking does not see this because it is not a link.
That allowed two dangling references to survive: cli-api-contract in `ADR-0013`
and contracts/component-setup-manifests.md in `ADR-0012` (the names are written
without backticks intentionally here: no file backs them, and the rule is right to
reject them). Both documents had been folded away, but the mentions remained and
read as current.

A separate reachability gate checks that no module-level public function in
`apps/cli`, `apps/api`, `apps/platform`, or `apps/worker` exists without a caller in
first-party source. Tests do not count as callers: otherwise a function called only
by its test would look alive. FastAPI handlers and pydantic constructors are not
orphans merely because a decorator or model construction reaches them. `packages/*`
is excluded from the definition set because it is a public API with consumers
outside the repository. The gate appeared after four safeguards were written,
documented, and tested—but connected to nothing. Coverage does not see this: a
function reached only by its own test is 100% covered and dead.

`back-static` keeps native Skill projections generated rather than hand-written: a
projection with its own command list would diverge from the registry at the first
change. The reverse operation is `back-gen`, which regenerates both `schemas/v1`
and Skill projections.

Since Sprint 1, schema checks in `back-static` cover two artifacts rather than one:
file-level schemas and `schemas/v1/openapi.json`. Both are produced by one generator
from the same models, so divergence between them is impossible by construction, and
the gate catches manual edits. Contract checks additionally validate the OpenAPI
document with the OpenAPI validator—validating each component schema against the
meta-schema is insufficient because the surrounding document is its own
specification—and check that every embedded example matches its schema, every
published type is reachable from a route, and the fixture corpus satisfies its
invariants from `docs/contracts/fixture-corpus.md`.

## Provider

- exact release manifest;
- digest/signature and trust policy;
- public contract;
- validate/plan without mutation;
- bundle adversarial tests;
- apply/status/restore;
- software lifecycle;
- release pin parity.

## Release

- Linux x86_64 evidence is required;
- macOS evidence is created manually only before a future support-matrix expansion;
- evidence age is limited;
- the first release is blocked by core support, product-requirement completeness,
  and a populated launch catalog according to `release-evidence.md`;
- beta lines advance independently and do not block the release;
- a skipped lane is not called verified;
- the final artifact is inspected;
- documentation and schemas are synchronized.

## Recipe naming

`justfile` follows a duality: `gen` writes, `check` reads. Everything else is the
same pair of operations narrowed to one group. The group owns the check, and its
prefix is mandatory:

| Prefix | Owner | Aggregate |
|---|---|---|
| `docs-*` | documentation foundation: specs, ADRs, `docs/`, MkDocs | `docs-check` |
| `back-*` | Python: `packages/`, `apps/api`, `apps/platform`, `apps/cli`, `tests/` | `back-check` |
| `web-*` | `apps/web` | `web-check` |

Each group uses the same verbs, so commands are derived rather than memorized:

| Verb | `docs-` | `back-` | `web-` |
|---|---|---|---|
| `gen` — rewrite machine text | indexes and tables | `ruff format`, `schemas/v1`, Skill projections | `prettier --write`, typed client from the contract |
| `static` — read source without running it | doc linters, Markdown, YAML, index divergence | `ruff format --check`, `ruff check`, `pyright`, schema and projection parity | ESLint, Prettier check, TypeScript 7 |
| `test` — run tests | validator unit tests | `pytest` with coverage report | Vitest with coverage thresholds |
| `build` — build an artifact | `mkdocs build --strict` | all package wheels in `dist/` | `next build` |
| `regress` — run the built artifact in the real engine | Mermaid diagram rendering | wheel installation in a clean venv and through `uv tool` | Playwright over the production build |
| `check` — group aggregate | `static`, `test`, `build`, `regress` | same | same |

No `-check` recipe writes anything: generated/source divergence is caught in
`-static` and fixed by an explicit `-gen` call. Each recipe remains independently
callable so a failure can be reproduced precisely without running neighboring
groups.

Outside the groups are `setup`, `hooks`, `gen`, `check`, `pre-commit`, and
`security`. No aliases are added: `ci` and `pre-push` were second names for `check`
and were removed. The Git pre-commit hook calls fast `just pre-commit`; full
`just check` remains the push/CI gate.

`security` is repository-wide, not group-specific: the dependency scanner is
currently one tool (`bun audit`). A Python scanner is added to the same recipe when
chosen, rather than creating an empty `back-security` in advance.

## Frontend (`apps/web`)

Frontend checks enter `just check` through `web-check`. Local and CI paths match
(issues #82/#83, ADR-0043). The runner needs `bun` (the workflow installs it through
`oven-sh/setup-bun`); missing `bun` fails the recipe rather than skipping the step.
Dependency installation from `bun.lock` lives in shared `just setup`, not in a
separate recipe.

`web-check` order is fixed: static checks, tests, build, and browser regression. The
default site profile for `web-build` and CI is `public_saas`; `self_hosted` is checked
by a separate explicit profile run. `web-regress` depends on `web-build` because
Playwright starts `next start` over the production build and checks desktop and
mobile viewports. The recipe installs only pinned browser bytes in the user cache.
System libraries belong to the self-hosted runner image and are not installed by a
check: `just check` does not call `sudo` or wait for an administrator password.

`web-test` always measures coverage: first ordinary `test:coverage`, then
`test:coverage:catalog` from `vitest.catalog.config.ts` with a 95% threshold for
`statements` / `branches` / `functions` / `lines` over the fixed catalog file set.
There is intentionally no separate coverage recipe: a threshold not invoked by
`just web-test` would be a reference number only.

Coverage thresholds are read with one caveat. The line threshold measures what it
claims; provider `v8` branch and function thresholds are inflated by unimported
files—a file loaded by no test reports 0% lines and 100% branches because it has no
branches counted at all. Therefore the line threshold must grow; branch and
function thresholds are regression guards and rise only together with the line
threshold.

## Enforcement

GitHub Actions executes the same commands as local recipes, but calls them directly:
`just` remains a developer-machine convenience and is not a dependency of the
published gate (this is tested). The job grouping covers exactly the leaves of
`just check`, which is also checked mechanically rather than by inspection.

One package manager per language. Python uses `uv` from the root `uv.lock`; docs
tools live in the `docs` group and development tools in the `dev` group. Node uses
`bun` from `docs_scripts/bun.lock` for documentation tools and `apps/web/bun.lock`
for the web. `pip`, `npm`, `npx`, and `pnpm` are not called by the gate; `uv` and
`bun` themselves are installed from signed release archives by
`.github/scripts/install-uv.sh` and `install-bun.sh`, with checksum verification.

Checks run on standard GitHub-hosted runners in the public tree, where minutes are
free and unlimited (`ADR-0110`). There is no separate pre-production tier under
`ADR-0084`: there is one environment, so the pre-deployment check is `just check`,
not a second surface.

There is no deployment in `check.yml`, which is not the same as having no deployment
in CI. It lives in a separate `deploy.yml` workflow, triggers from a green `check`
on `main`, and only advances one monotonic ref; the target host performs the actual
transfer on its timer (`ADR-0103`). The ref source is the public repository, so the
fetch uses anonymous HTTPS and the host retains no deployment key (`ADR-0109`).
The trust-domain separation from `ADR-0046` is stronger than before: untrusted pull
request code and deployment share no job.

CodeQL is not a gate. Who runs it and on which runner is defined in
`docs/operations/ci-cd.md`.

CodeQL is not a gate. Who runs it and on which runner is defined in
`docs/operations/ci-cd.md`.

`check` and `back-python-3.12` jobs run on pushes to `main` and on every pull
request. Push branches in the workflow must match the line from `git-workflow.md`.
An obsolete run is superseded on every event: there is nothing else to interrupt,
and the freed slot goes to the current run.

Nothing more is said here about fleet classes because they do not exist in this
tree: checks run on GitHub-hosted runners (`ubuntu-latest`, `macos-15`, and the OS
matrix), and a one-job queue does not apply to them. The former wording described a
private fleet and pointed to a record absent from the public tree.

These statuses are not made required, and that is a decision rather than a platform
limitation (`ADR-0115`). The repository has no participant protections: no branch
protection, mandatory approvals, protected environments, or tag rules. The reason
is who works here: the primary participant is a coding agent, and each such rule
puts a step in its cycle that it cannot perform while none checks the change itself.
The gate checks the change.

The boundary is one line and worth remembering for the next similar question: a
rule that checks the **change** remains; a rule that checks **permission** goes.
Therefore the gate, the published-path allowlist, and product confirmation of an
irreversible operation are not "protections" in this sense and remain.

The existence of a workflow without an observed run and branch rules does not count
as satisfying a requirement. After every merge to `main`, the exact merge SHA is
checked; a successful pull-request run on another tree does not replace checking
the main line.

`just evidence-live` proves an anonymous slice against the deployed environment:
exact deployed-commit identity, machine surface, anonymous catalog, equality of
the CLI projection and published catalog, and an offline replay returning the exact
cached object without asserting freshness. The recipe is not part of `just check`
and cannot be: the repository gate must not depend on an external environment, or
its unavailability would be read as a red code. Scenarios requiring a person or a
deterministic provider test environment enter the report as `not_verified` with a
reason rather than being omitted.
