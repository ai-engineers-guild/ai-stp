# Single entry point for local checks. `just` is a maintainer convenience,
# never a CI dependency: workflows write the recipe bodies out inline, and
# tests/contract/test_gate_split_covers_the_gate.py proves the two unions
# match. The conventions this file follows live in standards/just.md.
#
# The file rests on a duality: `gen` writes, `check` reads. Everything else is
# the same operations narrowed to one group.
#
# A group is a check's owner, and the prefix is mandatory:
#   docs-*    — current documentation and MkDocs;
#   back-*    — Python: packages/, apps/api, apps/platform, tests/;
#   cli-*  — apps/cli (native CLI and its boundary proofs);
#   web-*     — apps/web;
#   desktop-* — apps/desktop (UI + core + src-tauri crates);
#   infra-*   — Docker images, Compose stacks and the host-side deploy chain.
#
# `desktop-*` and `infra-*` are deliberately not in `check`: they need the
# WebKitGTK and Docker toolchains, which are not universal — fleet
# devices exist with no Docker at all, and `check` is the gate every host
# can run.
#
# Every group carries the same verb set, so a command is derived, not
# remembered:
#   <group>-gen      rewrite machine text (format and generated artifacts);
#   <group>-static   read source without executing it;
#   <group>-test     run tests;
#   <group>-build    build the artifact;
#   <group>-regress  run the built artifact in a real engine;
#   <group>-check    the group's aggregate.
#
# No `-check` writes anything: generated-vs-source drift is caught in
# `-static` and repaired by an explicit `-gen` call.

# The floor equals the bootstrap pin in docs_scripts/bootstrap_just.py; raise
# the two together. A parse-time error beats a feature silently mis-read by an
# older binary.
set minimum-version := "1.58.0"

scripts := "docs_scripts"
py := "uv run --locked --group docs python"
run := "uv run --locked"
native := "cd apps/cli && cargo run --quiet --locked --manifest-path xtask/Cargo.toml --"
# Test processes. The fleet class that runs the gate is a 4-vCPU machine, so 4
# is the shape CI actually has; a laptop with more cores can raise it and a
# constrained one can set 0 to go back to a single process. `auto` is
# deliberately not the default: it reads the host's core count, and on a
# 12-core machine that starts twelve workers against 8 GiB of memory.
test_workers := env_var_or_default("AI_STP_TEST_WORKERS", "4")

# xdist scheduling granularity. `load` (the plugin default) sends individual
# tests to whichever worker is free; that is the right shape here because the
# suite has no cross-test coupling — every PostgreSQL test owns its database
# and the root conftest isolates everything else per test. Coarser modes
# (`loadfile`, `loadgroup`) exist for local diagnosis of a skewed tail and are
# selected explicitly, not by default.
test_dist := env_var_or_default("AI_STP_TEST_DIST", "load")

# Coverage tracing backend. `ctrace` is the historical default; `sysmon`
# (Python 3.12+ sys.monitoring) traces with far less interpreter overhead.
# Exported so a focused run sees the same backend as the gate. pyproject pins
# `core = "sysmon"` and must not list greenlet under concurrency — that pair
# made coverage fall back to ctrace with a warning per worker (ADR-0117).
export COVERAGE_CORE := env_var_or_default("AI_STP_TEST_COVERAGE_CORE", "sysmon")

# A missing bun must fail the recipe, not skip the step. The version is
# checked exactly: bun writes its lockfile in the format of its own line, and
# `bun install` from another version silently rewrites `bun.lock` into
# something the gate cannot read. The error then surfaces in CI, not here.
bunreq := 'test "$(bun --version)" = "$(cat .bun-version)" || { echo "bun $(cat .bun-version) required, found $(bun --version 2>/dev/null || echo none)" >&2; exit 1; }'

# The same for uv, but for a different reason and only on the builder. uv
# stamps its own version into `dist-info/WHEEL`, so a candidate built by a
# different version differs from the released one — with fully identical
# modules. Once this already cost an investigation: ten mismatched digests
# turned out to be a single `Generator:` line, and the version read as byte
# substitution.
uvreq := 'have=$(uv --version 2>/dev/null | cut -d" " -f2); want=$(cat .uv-version); test "$have" = "$want" || { echo "uv $want required, found ${have:-none}; get it with: bash .github/scripts/install-uv.sh $want <dir> && export PATH=<dir>:\$PATH" >&2; exit 1; }'

export PYTHONUTF8 := "1"

[doc('List available recipes')]
[group('gate')]
default:
    @just --list --unsorted

# Lockfile drift is caught here as well: all three install strictly by theirs.

# Prepares the whole environment. Kept as an aggregate because that is exactly
# what is needed locally: one call before `just check` that prepares all.
#
# Split into three parts not for taste. In CI the gate executes as several
# jobs, and a job needing only Python used to install Node, bun and the web
# dependencies — a measured 1 m 35 s on `setup-node` and 1 m 55 s on the bun
# cache, wasted every time (`ADR-0105`, unpublished; `ADR-0116` publishes the
# job split).
[doc('Prepare the whole environment: Python, documentation and web tools')]
[group('gate')]
setup: setup-python setup-docs setup-web

# The Python environment: everything `uv run` executes.
[group('gate')]
setup-python:
    uv sync --locked --group docs --group dev

# The documentation Node tools: markdownlint and the Mermaid engine.
[group('gate')]
setup-docs:
    {{ bunreq }}
    cd docs_scripts && bun install --frozen-lockfile

# The web dependencies.
[group('gate')]
setup-web:
    {{ bunreq }}
    cd apps/web && bun install --frozen-lockfile

[doc('Install the git hooks')]
[group('gate')]
hooks:
    python {{ scripts }}/install_hooks.py

# Everything that writes. The resulting diff is reviewed by hand.
[group('gate')]
gen: docs-gen back-gen web-gen cli-gen

# Everything that reads.
[group('gate')]
check: docs-check back-check cli-check web-check security

# Fast gate for the local commit hook: source-level documentation checks, their
# validator unit tests, and static Python analysis. Full documentation builds,
# backend tests, wheel/install regression, web suites, and security scans are
# CI-only and run from the pull-request or main-push workflow.
[doc('Fast local gate: docs-static, docs-test, back-static, just-fmt')]
[group('gate')]
pre-commit: docs-static docs-test back-static just-fmt

# Local-only leaf: CI runs no `just`, so this file's own format check can only
# live outside the `check` tree.
[private]
just-fmt:
    just --fmt --check

# Repository-wide rather than group-owned: there is one scanner so far. A
# Python scanner joins here when one is chosen, not as an empty recipe early.

# The redistribution terms recorded inside each tracked font. Deliberately
# outside `just check`: whether a restricted font stays in the repository is a
# licensing decision of the owner with its own price, and a gate red today
# would have taken it for them. `--strict` returns nonzero and is meant for
# the release gate once the decision is made. fonttools comes through `--with`
# and never enters the project lockfile: a one-off audit must not weigh on
# every install.
[arg('args', help='extra font_licence_audit.py arguments')]
[doc('Audit the redistribution terms recorded inside each tracked font')]
[group('misc')]
fonts-licence *args:
    uv run --no-project --with fonttools --with brotli \
        python {{ scripts }}/font_licence_audit.py {{ args }}

# Dependency scan for known vulnerabilities.
[group('misc')]
security:
    {{ bunreq }}
    cd apps/web && bun run audit
    bash scripts/safety/scan_lockfile.sh

# Offline check of an estate record (`docs/contracts/estate-release.md`).
[arg('path', help='estate record file to validate')]
[arg('args', help='extra validator arguments')]
[group('release')]
estate-validate path *args:
    {{ run }} python -m release_scripts.validate_estate_record "{{ path }}" {{ args }}

# Build one estate record from local identities. Does not fetch.
[arg('tag', help='release tag')]
[arg('commit', help='source commit')]
[arg('output', help='record output path')]
[arg('version', help='release version')]
[arg('checksums', help='checksums file')]
[group('release')]
estate-record version commit tag checksums output:
    {{ run }} python -m release_scripts.build_estate_record \
        --version "{{ version }}" \
        --commit "{{ commit }}" \
        --tag "{{ tag }}" \
        --checksums "{{ checksums }}" \
        --output "{{ output }}"

# Deterministic safety evidence; the script disables external CLI and network.
[arg('args', help='extra benchmark arguments')]
[group('safety')]
safety-benchmark *args:
    {{ run }} python scripts/safety/benchmark_offline.py {{ args }}

# 108 real filesystem fixtures, sequential platform backend scan, JSON evidence.
[arg('args', help='extra corpus runner arguments')]
[group('safety')]
safety-corpus *args:
    {{ run }} python scripts/safety/run_adversarial_corpus.py {{ args }}

# The service named by AI_STP_TEST_DB_URL hosts a newly created, disposable
# database. The proof removes only that database and its temporary native roots.
[arg('binary', help='optimized native executable built with cli-build')]
[arg('digest', help='reviewed SHA-256 of that executable')]
[doc('Prove native two-device sync against the real API and isolated PostgreSQL')]
[group('evidence')]
evidence-native-sync binary digest:
    {{ run }} python -m release_scripts.verify_native_sync --binary "{{ binary }}" --binary-sha256 "{{ digest }}"

[arg('binary', help='optimized native executable built with cli-build')]
[arg('digest', help='reviewed SHA-256 of that executable')]
[doc('Prove native publication against the real API, isolated PostgreSQL and worker safety')]
[group('evidence')]
evidence-native-publication binary digest:
    {{ run }} python -m release_scripts.verify_native_publication --binary "{{ binary }}" --binary-sha256 "{{ digest }}"

# Fetches every link a harness-catalog row stands on and names the dead ones.
# Nothing in the repository opens a link, so a stale one is found by a person
# and nobody else: on 2026-08-28 there were four, two of them written the same
# day after a neighbour's pattern rather than off an open page.
#
# Not in the gate for the same reason as the other slices: `just check` may
# not depend on a vendor's site answering. 403, 405 and 429 count as
# unproven, not dead — some hosts refuse the script on HEAD.
[doc('Name dead links under harness-catalog rows')]
[group('evidence')]
evidence-citations:
    uv run --locked python -m release_scripts.verify_citation_slice

# Verifies publication, grants, reports and owner reads against the deployed
# environment (#182). Read-only by default: publishing an immutable version and
# changing somebody else's access both need an explicit decision by the operator.
[arg('home', help='signed-in home')]
[arg('origin', help='deployment origin')]
[arg('writes', help='non-empty to allow writes')]
[arg('invite', help='email to invite')]
[doc('Verify publication, grants and owner reads on the deployment')]
[group('evidence')]
evidence-publication home origin="https://ai-stp.aiguild.space" writes="" invite="":
    uv run --locked python -m release_scripts.verify_publication_slice \
        --origin "{{ origin }}" \
        --home "{{ home }}" \
        {{ if writes == "" { "" } else { "--allow-writes" } }} \
        {{ if invite == "" { "" } else { prepend("--invite-email ", invite) } }}

# --- docs ---------------------------------------------------------------

# Regenerates the documentation tables of contents and indexes.
[group('docs')]
docs-gen:
    {{ py }} {{ scripts }}/docs_lint.py --fix

# Frontmatter, links, anchors, placeholders, index.md parity, structure and
# traceability of active specs, semantic regressions, Markdown and YAML.

# Static documentation checks in one pass.
[group('docs')]
docs-static:
    {{ py }} {{ scripts }}/docs_lint.py
    {{ py }} {{ scripts }}/contract_lint.py
    {{ py }} {{ scripts }}/run_markdownlint.py
    {{ py }} -m yamllint -c {{ scripts }}/.yamllint.yml .

# Unit tests of the documentation validators themselves.
[group('docs')]
docs-test:
    {{ py }} -m unittest discover -s {{ scripts }}/tests -v

[doc('Strict builds of all three MkDocs sites')]
[group('docs')]
docs-build:
    {{ py }} -m mkdocs build --strict -f {{ scripts }}/mkdocs.yml
    {{ py }} -m mkdocs build --strict -f {{ scripts }}/user-mkdocs.yml
    {{ py }} -m mkdocs build --strict -f {{ scripts }}/user-mkdocs.en.yml

# Real render of diagrams in the Mermaid engine, not parsing of their text.
[group('docs')]
docs-regress:
    {{ py }} {{ scripts }}/mermaid_check.py

[doc('Serve the engineering docs locally')]
[group('docs')]
docs-serve:
    {{ py }} -m mkdocs serve -f {{ scripts }}/mkdocs.yml

# Both language lines. English builds into `/en/` inside the same site_dir,
# so order matters: Russian cleans the directory, English lands inside it.
[doc('Build both user-docs language lines')]
[group('docs')]
user-docs-build:
    {{ py }} -m mkdocs build --strict -f {{ scripts }}/user-mkdocs.yml
    {{ py }} -m mkdocs build --strict -f {{ scripts }}/user-mkdocs.en.yml

[doc('Serve the user docs locally')]
[group('docs')]
user-docs-serve:
    {{ py }} {{ scripts }}/user_docs_dev.py --host 127.0.0.1 --port 8011

[doc('Serve the English user docs locally')]
[group('docs')]
user-docs-serve-en:
    {{ py }} -m mkdocs serve -f {{ scripts }}/user-mkdocs.en.yml

[doc('The documentation aggregate')]
[group('docs')]
docs-check: docs-static docs-test docs-build docs-regress

# --- back ---------------------------------------------------------------

# Source format and the generated artifacts: schemas/v1, the standard
# inventory record `version` reads, and Skill projections.
[doc('Rewrite source format and generated artifacts')]
[group('back')]
back-gen:
    {{ run }} ruff format .
    {{ run }} python -m ai_stp_contracts.schemas schemas/v1
    {{ run }} python -m ai_stp_contracts.inventory_record
    {{ run }} python -m ai_stp_contracts.web_projections
    {{ run }} python -m ai_stp_contracts.technology_seed
    {{ run }} python release_scripts/provider_kit.py provider-kit/v3
    {{ run }} python release_scripts/first_party_corpus_digests.py
    {{ py }} {{ scripts }}/skill_projections.py

[doc('Format, lint, types and generated drift in one pass')]
[group('back')]
back-static:
    {{ run }} ruff format --check .
    {{ run }} ruff check .
    {{ run }} python -m pyright
    {{ run }} python -m ai_stp_contracts.schemas --check schemas/v1
    {{ run }} python -m ai_stp_contracts.inventory_record --check
    {{ run }} python -m ai_stp_contracts.web_projections --check
    {{ run }} python -m ai_stp_contracts.technology_seed --check
    {{ run }} python release_scripts/provider_kit.py --check provider-kit/v3
    {{ run }} python release_scripts/first_party_corpus_digests.py --check
    {{ run }} python release_scripts/safety_requirements.py --check
    {{ run }} python -m release_scripts.update_component_fixture --check
    {{ py }} {{ scripts }}/skill_projections.py --check

# Coverage is printed, not a fail-under (ADR-0147). The second call reads
# the data pytest-cov wrote so the local log matches CI's combined report.
[doc('Full test suite with coverage report')]
[group('back')]
back-test:
    {{ run }} python -m pytest {{ if test_workers == "0" { "" } else { "-n " + test_workers } }} --dist={{ test_dist }}
    {{ run }} python -m coverage report --precision=2

# Iteration run without coverage. Collecting coverage costs about a third of
# gate time (ADR-0104, unpublished, measured 325 s with it versus 252 s
# without; `ADR-0117` publishes the no-repeated-work rule), and in the
# edit-run loop it answers no question a failing test would not. It is not
# the gate: no threshold is checked here or should be.
[arg('args', help='extra pytest arguments')]
[doc('Iteration run without coverage')]
[group('back')]
back-test-fast *args:
    {{ run }} python -m pytest --no-cov {{ if test_workers == "0" { "" } else { "-n " + test_workers } }} --dist={{ test_dist }} {{ args }}

# Full single-process run writing every test's duration to .test_durations.
# The file feeds duration-based sharding once it is enabled; without it
# sharding falls back to balancing by test count. Refresh after large shifts
# in suite composition, not every run.
[doc('Record per-test durations for duration-based sharding')]
[group('back')]
back-durations:
    {{ run }} python -m pytest -n 0 --no-cov -q \
        --store-durations --durations-path .test_durations

# The directory is cleaned before building: a wheel of a yanked version left
# over from a previous run would otherwise be available to the installer
# through --find-links and substitute itself for the new one.

# Wheels of all workspace packages into dist/ (a git-ignored directory).
[group('back')]
back-build:
    {{ run }} python -c "import shutil; shutil.rmtree('dist', ignore_errors=True)"
    uv build --all-packages --out-dir dist -q

# Check server wheel dependency closure outside the source checkout.
[doc('Install server wheels in a clean environment')]
[group('back')]
back-regress:
    @just back-build
    {{ run }} python release_scripts/run_bash.py release_scripts/clean_install_regress.sh

[doc('The backend aggregate')]
[group('back')]
back-check: back-static back-test back-build back-regress

# --- web ----------------------------------------------------------------

# Source format and the typed client generated from the contract.
[doc('Regenerate the typed web client and format it')]
[group('web')]
web-gen:
    {{ run }} python -m ai_stp_contracts.web_projections
    {{ bunreq }}
    cd apps/web && bun run api:generate
    # The generator does not emit repository-Prettier form.  Formatting must
    # happen after generation so `just gen` is a deterministic clean producer
    # and `web-static` can validate its output without a repair step.
    cd apps/web && bun run format

# Ban on literal user-facing text and ru/en catalogue parity.
[group('web')]
web-i18n:
    {{ bunreq }}
    cd apps/web && bun run i18n:check

# ESLint, Prettier and TypeScript 7 in one pass.
[group('web')]
web-static: web-i18n
    {{ bunreq }}
    cd apps/web && bun run lint
    cd apps/web && bun run api:check
    cd apps/web && bun run format:check
    cd apps/web && bun run type-check

# Coverage is always measured: otherwise its thresholds would be a reference
# number, not a gate.

# Module and component tests.
[group('web')]
web-test:
    {{ bunreq }}
    cd apps/web && bun run test:coverage
    cd apps/web && bun run test:coverage:catalog

[doc('Production build of the SaaS profile')]
[group('web')]
web-build:
    {{ bunreq }}
    cd apps/web && AI_STP_WEB_PROFILE=public_saas bun run build

# Storybook builds together with the app because it has a different build
# graph: it raises its own Vite through `viteFinal`. While it was absent here,
# bumping `@vitejs/plugin-react` to 6 passed the whole gate green and broke
# only it — the plugin requires Vite 8, the app is pinned on 6, and there was
# nowhere to see it. Eleven seconds for such a divergence to be named at once.
[doc('Build Storybook with its own Vite graph')]
[group('web')]
web-storybook:
    {{ bunreq }}
    cd apps/web && bun run build-storybook

# Browser scenarios over the SaaS production build, desktop and mobile
# viewport.
#
# The build is declared a dependency, not repeated in the body. The recipe
# used to call `bun run build` itself, so inside `web-check` the production
# build of the same profile ran twice in a row: `just` runs a recipe once,
# not the same command in two bodies. The difference is measured — 45 s
# locally and about a minute and a half on the fleet's four-core machine,
# every run.
#
# A standalone `just web-regress` is unchanged all the same: the dependency
# gives the same build the recipe used to do itself.
[doc('Browser scenarios over the production build')]
[group('web')]
web-regress: web-build
    {{ bunreq }}
    # Browser bytes belong to the user's Playwright cache. OS packages belong
    # to the runner image and are provisioned out of band: a repository check
    # may not invoke sudo or block waiting for an administrator password.
    {{ run }} python release_scripts/run_bash.py .github/scripts/ensure-chrome.sh
    cd apps/web && bun run test:e2e

# Two independent production builds prove build-time feature exclusion.
[group('web')]
web-feature-profiles:
    {{ bunreq }}
    {{ run }} python release_scripts/run_bash.py .github/scripts/ensure-chrome.sh
    cd apps/web && bun run test:feature-profiles

# The build goes first on purpose. `tsconfig` includes `.next/types/**/*.ts`
# — the route validator `next build` generates. While the build ran after
# statics, that include meant nothing in a clean checkout (no directory, the
# pattern matches nothing) and gave a false refusal locally, where the
# directory survived from another branch. `just` runs each recipe once, so
# the order costs nothing: the build is in this aggregate anyway.
[doc('The web aggregate')]
[group('web')]
web-check: web-build web-storybook web-static web-test web-regress web-feature-profiles

# --- cli ----------------------------------------------------------------

# Format native sources explicitly; checks never rewrite them
[group('cli')]
cli-gen:
    {{ native }} resources
    cd apps/cli && cargo fmt
    cd apps/cli && cargo fmt --manifest-path xtask/Cargo.toml

# Native formatting and compiler diagnostics, including evidence examples
[group('cli')]
cli-static:
    {{ native }} resources --check
    cd apps/cli && cargo fmt --check
    cd apps/cli && cargo fmt --manifest-path xtask/Cargo.toml --check
    cd apps/cli && cargo clippy --locked --manifest-path xtask/Cargo.toml --all-targets -- -D warnings
    {{ native }} build cargo clippy --locked --all-targets -- -D warnings

# Canonical vectors, real binary behavior and adversarial signed provenance
[group('cli')]
cli-test:
    cd apps/cli && cargo test --locked --manifest-path xtask/Cargo.toml
    {{ native }} build cargo test --locked

# Optimized native executable and explicit provider evidence runner
[group('cli')]
cli-build:
    {{ native }} build cargo build --locked --release --bins --examples

# Existing envelope consumer, registry digest and live-WAL backup compatibility
[group('cli')]
cli-regress: cli-build
    {{ run }} python tests/native_contract/verify.py apps/cli/target/release/ai-stp

# Native CLI boundary gate (also part of the repository gate)
[group('cli')]
cli-check: cli-static cli-test cli-build cli-regress

# --- desktop ---------------------------------------------------------------

# Mirrors .github/workflows/desktop.yml minus the OS matrix and the
# `tauri build` bundling leg: same frontend checks, same crate checks, same
# real-sidecar spawn test. `desktop-build` writes `dist/` and a stub
# sidecar because tauri-build and `generate_context!` read both at compile
# time; the stub is written only when no sidecar exists, so a real
# native build is never replaced. `desktop-*` is deliberately outside
# `gen`/`check` — it needs Rust plus WebKitGTK system packages and is
# covered in CI by desktop.yml, not check.yml — the same exclusion
# `infra-*` has.

# Formats both Rust crates (writes only).
[doc('Format the two Rust crates')]
[group('desktop')]
desktop-gen:
    cd apps/desktop/core && cargo fmt
    cd apps/desktop/src-tauri && cargo fmt

# The frozen lockfile is the contract; `vite build` emits `dist/` and the
# stub resource satisfies the existence check before the crates compile.
# The repository-only Rust tool drives identical operations on all three OSes.
[doc('Frontend build plus a stub sidecar for compile-time checks')]
[group('desktop')]
desktop-build:
    {{ bunreq }}
    cd apps/desktop && bun install --frozen-lockfile
    cd apps/desktop && bun x vite build
    {{ native }} desktop-stub

[doc('tsc, fmt and clippy for the UI and both crates')]
[group('desktop')]
desktop-static: desktop-build
    cd apps/desktop && bun x tsc --noEmit
    cd apps/desktop/core && cargo fmt --check
    cd apps/desktop/core && cargo clippy --locked --all-targets -- -D warnings
    cd apps/desktop/src-tauri && cargo fmt --check
    cd apps/desktop/src-tauri && cargo clippy --locked --all-targets -- -D warnings

[doc('vitest and cargo test for both crates')]
[group('desktop')]
desktop-test: desktop-build
    cd apps/desktop && bun x vitest run
    cd apps/desktop/core && cargo test --locked
    cd apps/desktop/src-tauri && cargo test --locked

# Builds the optimized Rust sidecar, replaces the generated stub, and runs
# the same filtered-env resource probe as desktop.yml. The build and resource
# qualification use Rust; no interpreter is required.
[doc('Build the real sidecar and spawn it under the filtered env')]
[group('desktop')]
desktop-regress: desktop-build
    {{ native }} desktop-build
    {{ native }} desktop-probe

# Requires existing OS bundles from `bun x tauri build`; extraction is local
# and never installs the application on the developer's machine.
[doc('Extract an existing desktop bundle and probe its CLI resource tree')]
[group('desktop')]
desktop-bundle-test:
    {{ native }} desktop-package-probe

[doc('The desktop aggregate')]
[group('desktop')]
desktop-check: desktop-build desktop-static desktop-test desktop-regress

# Docker and Compose surface. Not a dependency of `check`: hadolint, shellcheck
# and the Compose CLI are infra tools, not gate prerequisites — a maintainer
# touches infra files knowingly and runs this group explicitly. The deploy
# chain's own checks live in tests/ (test_deploy_contract.py,
# test_container_bases_are_pinned.py) and run under `back-test` in CI.
[doc('The infra aggregate')]
[group('infra')]
infra-check: infra-static

# Dockerfile lint (hadolint, governed by .hadolint.yaml), deploy-script lint
# (shellcheck), and `docker compose config` over every file and overlay
# combination that must render. `config -q` resolves interpolation and service
# references without contacting the daemon — read-only, no build, no mutation.
# The two overlays are invalid alone by design (they patch dev services), so
# they are validated in the combinations the runbooks actually use. Values an
# overlay requires by design — the SEO-enrichment credential, the observability
# image — are supplied as inert placeholders: `config` checks the shape, and a
# missing required value is the deploy preflight's refusal, not this one's.
[doc('Lint Dockerfiles, deploy scripts and every valid compose combination')]
[group('infra')]
infra-static:
    hadolint deploy/docker/Dockerfile.app deploy/docker/Dockerfile.web deploy/docker/Dockerfile.docs
    shellcheck -x -S warning deploy/*.sh
    docker compose -f deploy/compose.prod.yml config -q
    docker compose -f deploy/compose.dev.yml config -q
    docker compose -f deploy/compose.dev.yml -f deploy/compose.corporate-local.yml config -q
    AI_STP_SEO_ENRICHMENT_CREDENTIAL=infra-static-placeholder docker compose -f deploy/compose.dev.yml -f deploy/compose.seo-enrichment.yml --profile seo_enrichment config -q
    docker compose -f deploy/compose.dev.yml -f deploy/compose.oidc-local.yml config -q
    docker compose -f deploy/compose.dev.yml -f deploy/compose.corporate-e2e.yml config -q
    docker compose -f deploy/compose.prod.yml -f deploy/compose.corporate.yml config -q
    AI_STP_OPENOBSERVE_IMAGE=openobserve/openobserve@sha256:0000000000000000000000000000000000000000000000000000000000000000 docker compose -f deploy/compose.prod.yml -f deploy/compose.observability.yml config -q

# The same contract deploy.sh enforces on the host, run against the local
# `.env.prod` before a deploy window: required values present and non-
# placeholder, 32-char secrets long enough, public origins real, the
# storage/RustFS pair equal. It never sources or prints the file, and a repo
# without `.env.prod` reports exactly which key is missing.
[doc('Rehearse the deploy secret preflight against a local .env.prod')]
[group('infra')]
infra-env-check:
    bash -c 'source deploy/lib.sh && require_deploy_env && echo "deploy environment contract holds"'

# Builds the production images the way the deployment host does — from this
# checkout, no registry push, `.env.prod` not required: build args carry
# defaults and `env_file` is `required: false` precisely so config and build
# work without secrets.
[doc('Build the production images from this checkout, as the deploy host does')]
[group('infra')]
infra-build:
    docker compose -f deploy/compose.prod.yml build

# The development stack is the only stack meant for local bring-up; prod is
# brought up by deploy/deploy.sh under its lock, on the deployment host.
[doc('Bring the development stack up with a fresh build')]
[group('infra')]
infra-up:
    docker compose -f deploy/compose.dev.yml up -d --build

[doc('Bring the development stack down')]
[group('infra')]
infra-down:
    docker compose -f deploy/compose.dev.yml down
