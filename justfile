# Single entry point for local checks. `just` is a maintainer convenience,
# never a CI dependency: workflows write the recipe bodies out inline, and
# tests/contract/test_gate_split_covers_the_gate.py proves the two unions
# match. The conventions this file follows are the working copy's own
# justfile standard; it does not ship in the public tree.
#
# The file rests on a duality: `gen` writes, `check` reads. Everything else is
# the same operations narrowed to one group.
#
# A group is a check's owner, and the prefix is mandatory:
#   docs-*  — the documentation basis (specs, ADRs, docs/, MkDocs);
#   back-*  — Python: packages/, apps/api, apps/platform, apps/cli, tests/;
#   web-*   — apps/web;
#   infra-* — Docker images, Compose stacks and the host-side deploy chain.
#
# `infra-*` is deliberately not in `check`: it needs the Docker toolchain,
# which is not universal — fleet devices exist with no Docker at all, and
# `check` is the gate every host can run.
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
# cache, wasted every time (`ADR-0105`).
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
gen: docs-gen back-gen web-gen

# Everything that reads.
[group('gate')]
check: docs-check back-check web-check security

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

# Builds, but does not publish, the public ai-stp-cli candidate. The working
# tree must be clean; a dirty tree is only for local characterization with
# explicit `--allow-dirty` and is never release evidence.
[doc('Build the public ai-stp-cli candidate without publishing')]
[group('release')]
release-candidate:
    {{ uvreq }}
    uv run --locked python release_scripts/build_candidate.py --replace

# Installs the current candidate's ai-stp-cli wheel outside checkout, runs
# the CLI, and removes the tool. The public index is used only for third-party
# dependencies.
[doc('Install the candidate wheel outside checkout, run it, remove it')]
[group('release')]
release-candidate-install:
    uv run --locked python -m release_scripts.verify_candidate_install \
        dist/release-candidate \
        --expected-sha "$(git rev-parse HEAD)"

# Verifies the anonymous slice (`#85`) against the deployed environment.
#
# Changes nothing and authenticates with nothing: an anonymous slice has to prove
# itself without credentials, and a script that cannot hold one cannot leak one.
# Not part of `just check` — the repository gate may not depend on an external
# environment, or that environment being unreachable reads as a red build here.
[arg('origin', help='deployment origin')]
[arg('commit', help='expected deployed commit')]
[doc('Verify the anonymous slice against the deployed environment')]
[group('evidence')]
evidence-live origin="https://ai-stp.aiguild.space" commit="":
    uv run --locked python -m release_scripts.verify_live_slice \
        --origin "{{ origin }}" \
        {{ if commit == "" { "" } else { "--expected-commit " + commit } }}

# Verifies the two-device synchronisation slice (#180) against the deployed
# environment. Both homes must already be signed in: the device-code flow needs a
# person, and a script able to mint a session would be proving the wrong path.
#
# Different `HOME` values do NOT create two devices. The OS credential store
# belongs to the OS user, not the home directory, so `HOME=… ai-stp auth status`
# answers `authenticated` from the shared keyring and both "devices" turn out to
# be one. Each login must use `AI_STP_FORCE_FILE_CREDENTIAL_STORE=1`, or the
# slice proves something other than what it claims.
#
# `skip` is a space-separated list of exact event ids that no client can apply to
# this account's history. The operator names them: a slice that guessed what to
# skip would go green on the strength of what it never read.
[arg('skip', help='event ids no client may apply')]
[arg('home_a', help='first signed-in home')]
[arg('home_b', help='second signed-in home')]
[arg('origin', help='deployment origin')]
[doc('Verify the two-device synchronisation slice on the deployment')]
[group('evidence')]
evidence-sync home_a home_b origin="https://ai-stp.aiguild.space" skip="":
    uv run --locked python -m release_scripts.verify_sync_slice \
        --origin "{{ origin }}" \
        --home-a "{{ home_a }}" \
        --home-b "{{ home_b }}" \
        {{ if skip == "" { "" } else { prepend("--skip-event ", skip) } }}

# Proves this repository's projection table still agrees with the seven
# providers **as released** — on the bytes `provider fetch` serves.
#
# Not in `just check` for the same reason as the other slices: the gate may
# not depend on somebody else's tags, or a release being unreachable reads as
# red code here.
#
# It exists because on 2026-08-27 both of our tables named a cursor surface
# the product does not read, and the check comparing them passed — they were
# wrong identically. Only the provider's declaration settled it, and no check
# compared against the **release**: the test-suite analog reads the local
# build tree, that is, whatever a person last compiled.
#
# Requires `GH_CONFIG_DIR`: the slice isolates `HOME`, and `provider fetch`
# calls `gh`, which in isolation finds no configuration and reports missing
# release metadata — not the cause.
[arg('tag', help='provider release tag')]
[arg('harness', help='limit to one harness')]
[doc('Prove projections agree with the released provider bytes')]
[group('evidence')]
evidence-providers tag harness="":
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-${APPDATA:+$APPDATA/GitHub CLI}}"; \
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-$HOME/.config/gh}" \
    uv run --locked python -m release_scripts.verify_provider_slice \
        --tag "{{ tag }}" \
        {{ if harness == "" { "" } else { prepend("--harness ", harness) } }}

# Drives every non-global provider profile through a mutating disposable-target
# lifecycle with a consumer-produced adaptation-bound bundle v2. This is local
# source evidence before release; `evidence-providers` remains the released-byte
# proof after attestation and publication.
[arg('setup_systems_root', help='checkout of the private setup-systems source')]
[doc('Drive every provider profile through a mutating lifecycle')]
[group('evidence')]
evidence-provider-scopes setup_systems_root:
    uv run --locked python -m release_scripts.verify_scoped_provider_slice \
        --setup-systems-root "{{ setup_systems_root }}"

# The second half of the same question: `evidence-providers` proves the
# contract and the bytes, while this slice drives each released provider
# through the **consumer** path — `harness install/status/update/remove`
# calls of `ai-stp` itself.
#
# These are different questions and they fail for different reasons. Every
# integration defect in this estate lived exactly between consumer and
# provider: argv the provider did not expect; a status read differently; a
# record that did not survive the sandbox; a postcondition taken from the
# wrong subject. None of them is visible to a slice that asks the provider
# directly.
#
# One line per harness, an outcome out of five, and a missing line is an
# error, not zero refusals. `GH_CONFIG_DIR` is needed for the same reason as
# its neighbour.
[arg('tag', help='provider release tag')]
[arg('harness', help='limit to one harness')]
[arg('acquire', help='non-empty to auto-acquire artifacts')]
[doc('Drive released providers through the consumer install path')]
[group('evidence')]
evidence-software tag harness="" acquire="":
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-${APPDATA:+$APPDATA/GitHub CLI}}"; \
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-$HOME/.config/gh}" \
    uv run --locked python -m release_scripts.verify_software_slice \
        --tag "{{ tag }}" \
        {{ if harness == "" { "" } else { prepend("--harness ", harness) } }} \
        {{ if acquire == "" { "" } else { "--acquire" } }}

# The third question of the same pair, and the only one about
# **configuration**. `evidence-providers` asks the contract,
# `evidence-software` the program, and this drives each harness's native
# surface through the full arc: seed → adopt → release → propose → confirm →
# plan → approve → apply → target observation → removal plan → apply → the
# target is clean again.
#
# It exists because before it the end-to-end property — "capture a machine's
# configuration and put it on the next one" — was measured by hand and only
# on linux/x86_64. The verdict is taken from the target, not from the
# provider's answer.
#
# Not in `just check` for the same reason as the neighbours: the gate may not
# depend on somebody else's release. `GH_CONFIG_DIR` is needed by
# `provider fetch`.
[arg('tag', help='provider release tag')]
[arg('scope', help='limit to one scope')]
[arg('harness', help='limit to one harness')]
[arg('from_import', help='non-empty to seed from an import')]
[doc('Drive each harness through the full configuration arc')]
[group('evidence')]
evidence-config tag harness="" from_import="" scope="":
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-${APPDATA:+$APPDATA/GitHub CLI}}"; \
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-$HOME/.config/gh}" \
    uv run --locked python -m release_scripts.verify_config_slice \
        --tag "{{ tag }}" \
        {{ if harness == "" { "" } else { prepend("--harness ", harness) } }} \
        {{ if from_import == "" { "" } else { "--from-import" } }} \
        {{ if scope == "" { "" } else { "--scope " + scope } }}

# Acceptance of `#54`: one MCP component in three native forms — a key in
# somebody else's settings file, its own file, and a product that has no such
# kind at all.
#
# The script existed since 2026-08-31 and was called from nowhere: no recipe,
# no workflow step, no line in a document. The first real run found three
# defects in it — adoption from an arbitrary directory, a version adopt does
# not return, and a claude-code control going green on somebody else's
# refusal.
[arg('tag', help='provider release tag')]
[doc('Acceptance of #54: one MCP component in three native forms')]
[group('evidence')]
evidence-contribution tag:
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-${APPDATA:+$APPDATA/GitHub CLI}}"; \
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-$HOME/.config/gh}" \
    uv run --locked python -m release_scripts.verify_contribution_slice \
        --tag "{{ tag }}"

# Asks the source whether the first-party corpus drifted from what is
# published. The corpus's forty objects are bound to `passport_digest` and
# immutable under `REQ-2606` — that is, protected from being **changed**, and
# by nothing from having been **wrong**. They cannot be re-derived locally:
# their content lives in seven outside repositories.
#
# The difference between the two protections is not theoretical: on 2026-08-29
# the corpus carried seven setups out of twenty-eight published, under a role
# name no source carries — and every digest agreed the whole time (`#461`).
#
# The recipe exists because before it only somebody who could type the script
# path could do this. It reports and never refuses, and is not in
# `just check`: the repository gate may not depend on somebody else's
# network.
[arg('args', help='extra corpus builder arguments')]
[doc('Report first-party corpus drift against published sources')]
[group('evidence')]
corpus-drift *args:
    uv run --locked python release_scripts/build_first_party_corpus.py --drift \
        --out packages/contracts/src/ai_stp_contracts/first_party/v1 {{ args }}

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
    {{ py }} {{ scripts }}/spec_lint.py
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

# Source format and both generated artifacts: schemas/v1 and Skill
# projections.
[doc('Rewrite source format and generated artifacts')]
[group('back')]
back-gen:
    {{ run }} ruff format .
    {{ run }} python -m ai_stp_contracts.schemas schemas/v1
    {{ run }} python -m ai_stp_contracts.web_projections
    {{ run }} python release_scripts/provider_kit.py provider-kit/v3
    {{ run }} python release_scripts/verifier_requirements.py
    {{ py }} {{ scripts }}/skill_projections.py

# Format, lint, types and generated-vs-source drift in one pass.
# What may enter the public `ai-stp` repository, and what may never.
# The report writes nothing and refuses if an unnamed root or private
# infrastructure appears in a published file.
[doc('Report what may and may never enter the public tree')]
[group('release')]
public-report:
    {{ run }} python -m release_scripts.public_export --report

# Builds the public tree into `public/build`: manifest, overlay, its own git
# and rebuilt indexes.
[doc('Build the public tree into public/build')]
[group('release')]
public-build:
    {{ run }} python -m release_scripts.public_export

# Publishes the built tree to `ai-stp` in one commit from the identity of the
# global git config. The delta is computed through the API, so nothing needs
# downloading.
[arg('tree', help='built public tree')]
[arg('message', help='file containing the commit message')]
[doc('Publish the built tree to ai-stp in one commit')]
[group('release')]
public-publish tree message:
    {{ run }} python -m release_scripts.public_publish --tree "{{ tree }}" --message-file "{{ message }}"

# Pulls the public tree back here (`ADR-0110`). The argument is a checkout of
# `ai-stp`. Generators are called next, because the public tree's indexes
# enumerate only its own documents and this tree has more.
[arg('tree', help='checkout of the public ai-stp repository')]
[doc('Pull the public tree back here (ADR-0110)')]
[group('release')]
public-sync tree:
    {{ run }} python -m release_scripts.public_import --tree "{{ tree }}"
    just docs-gen
    just back-gen

# Shows what a sync would change, writing nothing.
[arg('tree', help='checkout of the public ai-stp repository')]
[group('release')]
public-sync-report tree:
    {{ run }} python -m release_scripts.public_import --tree "{{ tree }}" --report

# Verifies the published half of this tree matches the public repository byte
# for byte. This is a round-trip check of sync and export at once.
[arg('tree', help='checkout of the public ai-stp repository')]
[doc('Verify the published half matches the public repository')]
[group('release')]
public-sync-verify tree:
    {{ run }} python -m release_scripts.public_import --tree "{{ tree }}" --verify

[doc('Format, lint, types and generated drift in one pass')]
[group('back')]
back-static:
    {{ run }} ruff format --check .
    {{ run }} ruff check .
    {{ run }} python -m pyright
    {{ run }} python -m release_scripts.public_export --report
    {{ run }} python -m ai_stp_contracts.schemas --check schemas/v1
    {{ run }} python -m ai_stp_contracts.web_projections --check
    {{ run }} python release_scripts/provider_kit.py --check provider-kit/v3
    {{ run }} python release_scripts/verifier_requirements.py --check
    {{ py }} {{ scripts }}/skill_projections.py --check

# Coverage is printed, not a fail-under (ADR-0147). The second call reads
# the data pytest-cov wrote so the local log matches CI's combined report.
[doc('Full test suite with coverage report')]
[group('back')]
back-test:
    {{ run }} python -m pytest {{ if test_workers == "0" { "" } else { "-n " + test_workers } }} --dist={{ test_dist }}
    {{ run }} python -m coverage report --precision=2

# Iteration run without coverage. Collecting coverage costs about a third of
# gate time (ADR-0104: 325 s with it versus 252 s without), and in the
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

# SQLite emits its direct ResourceWarning only on Python 3.13+ finalization.
# Run the focused long-lived CLI lifecycle with both warning forms as errors;
# the broad suite also owns platform logging handlers, whose lifecycle belongs
# to the platform track and must not weaken this CLI-specific acceptance gate.
[doc('CLI lifecycle under ResourceWarning-as-error')]
[group('back')]
back-resource:
    {{ run }} python -m pytest --no-cov -q \
        -W error::ResourceWarning \
        -W error::pytest.PytestUnraisableExceptionWarning \
        tests/contract/test_cli_resource_lifecycle.py

# The cross-platform CLI surface, split the way the CI matrix consumes it.
# The flags are part of the contract and live here, not in the workflow YAML:
# `-vv` because addopts already carries `-q` and a single `-v` cancels out;
# `faulthandler_timeout` names the hanging test instead of ending mid-line,
# which is how three CI runs died on their own timeout without saying why.
# Local runs on one OS exercise the same invocation the three-OS matrix runs.
[arg('suite', help='test suite directory under tests/: unit, contract, process')]
[group('back')]
back-cli-suite suite:
    {{ run }} python -m pytest "tests/{{ suite }}" --no-cov -vv \
        -o faulthandler_timeout=300 {{ if test_workers == "0" { "" } else { "-n " + test_workers } }} --dist={{ test_dist }} \
        {{ if suite == "unit" { "--ignore=tests/unit/platform --ignore=tests/unit/api" } else { "" } }}

# The directory is cleaned before building: a wheel of a yanked version left
# over from a previous run would otherwise be available to the installer
# through --find-links and substitute itself for the new one.

# Wheels of all workspace packages into dist/ (a git-ignored directory).
[group('back')]
back-build:
    {{ run }} python -c "import shutil; shutil.rmtree('dist', ignore_errors=True)"
    uv build --all-packages --out-dir dist -q

# Installs the built wheels and runs the CLI two ways. The body lives in
# release_scripts/clean_install_regress.sh: both this recipe and the CI gate
# call it, so a clean install cannot diverge between the local and the CI
# path. The working environment carries the docs and dev group dependencies,
# so an undeclared package dependency is invisible in it and only shows for
# whoever installed the wheel: an unimported-by-declaration yaml import in
# apps/cli already slipped through that way once.
# Windows PATH `bash` is frequently WSL, which cannot run this checkout.
# `run_bash.py` locates Git-for-Windows bash (or PATH bash on POSIX) so the
# same recipe body is the local path; CI still calls the shell script itself.
[doc('Install built wheels and run the CLI in a clean environment')]
[group('back')]
back-regress:
    @just back-build
    {{ run }} python release_scripts/run_bash.py release_scripts/clean_install_regress.sh

[doc('The backend aggregate')]
[group('back')]
back-check: back-static back-test back-resource back-build back-regress

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
# they are validated in the combinations the runbooks actually use.
[doc('Lint Dockerfiles, deploy scripts and every valid compose combination')]
[group('infra')]
infra-static:
    hadolint Dockerfile Dockerfile.user-docs Dockerfile.worker-safety apps/web/Dockerfile.prod apps/web/Dockerfile.dev
    shellcheck -x -S warning deploy/*.sh
    docker compose -f docker-compose.prod.yml config -q
    docker compose -f docker-compose.dev.yml config -q
    docker compose -f docker-compose.dev.yml -f docker-compose.corporate-local.yml config -q
    docker compose -f docker-compose.dev.yml -f docker-compose.seo-enrichment.yml --profile seo_enrichment config -q

# Builds the production images the way the deployment host does — from this
# checkout, no registry push, `.env.prod` not required: build args carry
# defaults and `env_file` is `required: false` precisely so config and build
# work without secrets.
[doc('Build the production images from this checkout, as the deploy host does')]
[group('infra')]
infra-build:
    docker compose -f docker-compose.prod.yml build

# The development stack is the only stack meant for local bring-up; prod is
# brought up by deploy/deploy.sh under its lock, on the deployment host.
[doc('Bring the development stack up with a fresh build')]
[group('infra')]
infra-up:
    docker compose -f docker-compose.dev.yml up -d --build

[doc('Bring the development stack down')]
[group('infra')]
infra-down:
    docker compose -f docker-compose.dev.yml down
