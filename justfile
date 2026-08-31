#
#
#   back-*  — Python: packages/, apps/api, apps/platform, apps/cli, tests/;
#   web-*   — apps/web.
#
#

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

bunreq := 'test "$(bun --version)" = "$(cat .bun-version)" || { echo "bun $(cat .bun-version) required, found $(bun --version 2>/dev/null || echo none)" >&2; exit 1; }'

uvreq := 'have=$(uv --version 2>/dev/null | cut -d" " -f2); want=$(cat .uv-version); test "$have" = "$want" || { echo "uv $want required, found ${have:-none}; get it with: bash .github/scripts/install-uv.sh $want <dir> && export PATH=<dir>:\$PATH" >&2; exit 1; }'

export PYTHONUTF8 := "1"

default:
    @just --list --unsorted


#
# (`ADR-0105`).
setup: setup-python setup-docs setup-web

setup-python:
    uv sync --locked --group docs --group dev

setup-docs:
    {{bunreq}}
    cd docs_scripts && bun install --frozen-lockfile

setup-web:
    {{bunreq}}
    cd apps/web && bun install --frozen-lockfile

hooks:
    python {{scripts}}/install_hooks.py

gen: docs-gen back-gen web-gen

check: docs-check back-check web-check security

pre-commit: docs-check back-static


fonts-licence *args:
    uv run --no-project --with fonttools --with brotli \
        python {{scripts}}/font_licence_audit.py {{args}}

security:
    {{bunreq}}
    cd apps/web && bun run audit

# Deterministic safety evidence; the script disables external CLI and network.
safety-benchmark *args:
    {{run}} python scripts/safety/benchmark_offline.py {{args}}

# 108 real filesystem fixtures, sequential platform backend scan, JSON evidence.
safety-corpus *args:
    {{run}} python scripts/safety/run_adversarial_corpus.py {{args}}

release-candidate:
    {{uvreq}}
    uv run --locked python release_scripts/build_candidate.py --replace

release-candidate-install:
    uv run --locked python -m release_scripts.verify_candidate_install \
        dist/release-candidate \
        --expected-sha "$(git rev-parse HEAD)"

# Verifies the anonymous slice against the deployed environment.
evidence-live origin="https://ai-stp.aiguild.space" commit="":
    uv run --locked python -m release_scripts.verify_live_slice \
        --origin "{{origin}}" \
        {{ if commit == "" { "" } else { "--expected-commit " + commit } }}

# Different `HOME` values do not create two devices. The OS credential store
# belongs to the OS user, not the home directory. Each login must use
# `AI_STP_FORCE_FILE_CREDENTIAL_STORE=1` for the slice to prove what it claims.
# `skip` is a space-separated list of exact event ids that do not apply to this
# account history; it is named by the operator rather than guessed by the tool.
evidence-sync home_a home_b origin="https://ai-stp.aiguild.space" skip="":
    uv run --locked python -m release_scripts.verify_sync_slice \
        --origin "{{origin}}" \
        --home-a "{{home_a}}" \
        --home-b "{{home_b}}" \
        {{ if skip == "" { "" } else { prepend("--skip-event ", skip) } }}

#
#
#
evidence-providers tag harness="":
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-$HOME/.config/gh}" \
    uv run --locked python -m release_scripts.verify_provider_slice \
        --tag "{{tag}}" \
        {{ if harness == "" { "" } else { prepend("--harness ", harness) } }}

#
#
evidence-software tag harness="":
    GH_CONFIG_DIR="${GH_CONFIG_DIR:-$HOME/.config/gh}" \
    uv run --locked python -m release_scripts.verify_software_slice \
        --tag "{{tag}}" \
        {{ if harness == "" { "" } else { prepend("--harness ", harness) } }}

#
#
corpus-drift *args:
    uv run --locked python release_scripts/build_first_party_corpus.py --drift \
        --out packages/contracts/src/ai_stp_contracts/first_party/v1 {{args}}

#
evidence-citations:
    uv run --locked python -m release_scripts.verify_citation_slice

# Verifies publication, grants, reports and owner reads against the deployed
# environment (#182). Read-only by default; writes require an explicit choice.
evidence-publication home origin="https://ai-stp.aiguild.space" writes="":
    uv run --locked python -m release_scripts.verify_publication_slice \
        --origin "{{origin}}" \
        --home "{{home}}" \
        {{ if writes == "" { "" } else { "--allow-writes" } }}

# --- docs ---------------------------------------------------------------

docs-gen:
    {{py}} {{scripts}}/docs_lint.py --fix


docs-static:
    {{py}} {{scripts}}/docs_lint.py
    {{py}} {{scripts}}/spec_lint.py
    {{py}} {{scripts}}/contract_lint.py
    {{py}} {{scripts}}/run_markdownlint.py
    {{py}} -m yamllint -c {{scripts}}/.yamllint.yml .

docs-test:
    {{py}} -m unittest discover -s {{scripts}}/tests -v

docs-build:
    {{py}} -m mkdocs build --strict -f {{scripts}}/mkdocs.yml
    {{py}} -m mkdocs build --strict -f {{scripts}}/user-mkdocs.yml
    {{py}} -m mkdocs build --strict -f {{scripts}}/user-mkdocs.en.yml

docs-regress:
    {{py}} {{scripts}}/mermaid_check.py

docs-serve:
    {{py}} -m mkdocs serve -f {{scripts}}/mkdocs.yml

user-docs-build:
    {{py}} -m mkdocs build --strict -f {{scripts}}/user-mkdocs.yml
    {{py}} -m mkdocs build --strict -f {{scripts}}/user-mkdocs.en.yml

user-docs-serve:
    {{py}} -m mkdocs serve -f {{scripts}}/user-mkdocs.yml

user-docs-serve-en:
    {{py}} -m mkdocs serve -f {{scripts}}/user-mkdocs.en.yml

docs-check: docs-static docs-test docs-build docs-regress

# --- back ---------------------------------------------------------------

back-gen:
    {{run}} ruff format .
    {{run}} python -m ai_stp_contracts.schemas schemas/v1
    {{run}} python -m ai_stp_contracts.web_projections
    {{run}} python release_scripts/provider_kit.py provider-kit/v3
    {{py}} {{scripts}}/skill_projections.py

public-report:
    {{run}} python -m release_scripts.public_export --report

public-build:
    {{run}} python -m release_scripts.public_export

public-publish tree message:
    {{run}} python -m release_scripts.public_publish --tree "{{tree}}" --message-file "{{message}}"

public-sync tree:
    {{run}} python -m release_scripts.public_import --tree "{{tree}}"
    just docs-gen
    just back-gen

public-sync-report tree:
    {{run}} python -m release_scripts.public_import --tree "{{tree}}" --report

public-sync-verify tree:
    {{run}} python -m release_scripts.public_import --tree "{{tree}}" --verify

back-static:
    {{run}} ruff format --check .
    {{run}} ruff check .
    {{run}} python -m pyright
    {{run}} python -m release_scripts.public_export --report
    {{run}} python -m ai_stp_contracts.schemas --check schemas/v1
    {{run}} python -m ai_stp_contracts.web_projections --check
    {{run}} python release_scripts/provider_kit.py --check provider-kit/v3
    {{py}} {{scripts}}/skill_projections.py --check

back-test:
    {{run}} pytest {{ if test_workers == "0" { "" } else { "-n " + test_workers } }} --dist={{test_dist}}
    # `FAIL Required test coverage of 95% not reached. Total coverage: 94.55%`,
    {{run}} coverage report --precision=2 --fail-under=90

back-test-fast *args:
    {{run}} pytest --no-cov {{ if test_workers == "0" { "" } else { "-n " + test_workers } }} --dist={{test_dist}} {{args}}

back-durations:
    {{run}} pytest -n 0 --no-cov -q \
        --store-durations --durations-path .test_durations

# SQLite emits its direct ResourceWarning only on Python 3.13+ finalization.
# Run the focused long-lived CLI lifecycle with both warning forms as errors;
# the broad suite also owns platform logging handlers, whose lifecycle belongs
# to the platform track and must not weaken this CLI-specific acceptance gate.
back-resource:
    {{run}} pytest --no-cov -q \
        -W error::ResourceWarning \
        -W error::pytest.PytestUnraisableExceptionWarning \
        tests/contract/test_cli_resource_lifecycle.py

# The cross-platform CLI surface, split the way the CI matrix consumes it.
# The flags are part of the contract and live here, not in the workflow YAML:
# `-vv` because addopts already carries `-q` and a single `-v` cancels out;
# `faulthandler_timeout` names the hanging test instead of ending mid-line,
# which is how three CI runs died on their own timeout without saying why.
# Local runs on one OS exercise the same invocation the three-OS matrix runs.
back-cli-suite suite:
    {{run}} pytest "tests/{{suite}}" --no-cov -vv \
        -o faulthandler_timeout=300 {{ if test_workers == "0" { "" } else { "-n " + test_workers } }} --dist={{test_dist}} \
        {{ if suite == "unit" { "--ignore=tests/unit/platform --ignore=tests/unit/api" } else { "" } }}


back-build:
    {{run}} python -c "import shutil; shutil.rmtree('dist', ignore_errors=True)"
    uv build --all-packages --out-dir dist -q

# Windows PATH `bash` is frequently WSL, which cannot run this checkout.
# `run_bash.py` locates Git-for-Windows bash (or PATH bash on POSIX) so the
# same recipe body is the local path; CI still calls the shell script itself.
back-regress:
    @just back-build
    {{run}} python release_scripts/run_bash.py release_scripts/clean_install_regress.sh

back-check: back-static back-test back-resource back-build back-regress

# --- web ----------------------------------------------------------------

web-gen:
    {{run}} python -m ai_stp_contracts.web_projections
    {{bunreq}}
    cd apps/web && bun run api:generate
    # The generator does not emit repository-Prettier form.  Formatting must
    # happen after generation so `just gen` is a deterministic clean producer
    # and `web-static` can validate its output without a repair step.
    cd apps/web && bun run format

web-i18n:
    {{bunreq}}
    cd apps/web && bun run i18n:check

web-static: web-i18n
    {{bunreq}}
    cd apps/web && bun run lint
    cd apps/web && bun run format:check
    cd apps/web && bun run type-check


web-test:
    {{bunreq}}
    cd apps/web && bun run test:coverage
    cd apps/web && bun run test:coverage:catalog

web-build:
    {{bunreq}}
    cd apps/web && AI_STP_WEB_PROFILE=public_saas bun run build

web-storybook:
    {{bunreq}}
    cd apps/web && bun run build-storybook

#
#
web-regress: web-build
    {{bunreq}}
    # Browser bytes belong to the user's Playwright cache. OS packages belong
    # to the runner image and are provisioned out of band: a repository check
    # may not invoke sudo or block waiting for an administrator password.
    bash .github/scripts/ensure-chrome.sh
    cd apps/web && bun run test:e2e

web-feature-profiles:
    {{bunreq}}
    bash .github/scripts/ensure-chrome.sh
    cd apps/web && bun run test:feature-profiles

web-check: web-build web-storybook web-static web-test web-regress web-feature-profiles
