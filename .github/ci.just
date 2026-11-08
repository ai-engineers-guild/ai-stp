# Execution commands; SDKs, services, permissions and artifacts stay in workflows.

[group('ci')]
[script('bash')]
ci-secrets-verify-the-scanner-and-inspect-the-selected-source:
    set -euo pipefail
    python .github/scripts/check-source-secrets.py

[group('ci')]
[script('bash')]
ci-integration-python-check-source-contracts-and-units-without-server-services:
    set -euo pipefail
    source .github/scripts/provider-safe-path.sh
    ai_stp_use_provider_safe_path
    just back-static docs-source docs-test
    uv run --locked pytest -n 8 --dist=load -m 'not pg' tests/unit tests/contract

[group('ci')]
[script('bash')]
ci-integration-web-web-syntax-types-and-units:
    set -euo pipefail
    cd apps/web
    bun install --frozen-lockfile
    AI_STP_WEB_PROFILE=public_saas bun x next typegen
    bun run lint
    bun run format:check
    bun run type-check
    bun run i18n:check
    bun run test

[group('ci')]
[script('bash')]
ci-integration-web-desktop-types-and-component-units:
    set -euo pipefail
    cd apps/desktop
    python ../../release_scripts/desktop_version.py --check
    bun install --frozen-lockfile
    bun run format:check
    bun run messages:check
    bun x tsc --noEmit
    bun x vitest run

[group('ci')]
[script('bash')]
ci-integration-web-documentation-markdown-syntax:
    set -euo pipefail
    (cd docs_scripts && bun install --frozen-lockfile)
    python docs_scripts/run_markdownlint.py

[group('ci')]
[script('bash')]
ci-integration-native-native-formatting-all-target-analysis-and-library-units:
    set -euo pipefail
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- resources --check
    cargo fmt --manifest-path apps/cli/Cargo.toml --check
    cargo fmt --manifest-path apps/cli/xtask/Cargo.toml --check
    cargo clippy --locked --manifest-path apps/cli/xtask/Cargo.toml \
      --all-targets -- -D warnings
    cargo test --locked --manifest-path apps/cli/xtask/Cargo.toml
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- build \
      cargo clippy --locked --all-targets -- -D warnings
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- build \
      cargo test --locked --lib
    cargo fmt --manifest-path apps/desktop/core/Cargo.toml --check
    cargo clippy --locked --manifest-path apps/desktop/core/Cargo.toml \
      --all-targets -- -D warnings
    cargo test --locked --manifest-path apps/desktop/core/Cargo.toml

[group('ci')]
[script('bash')]
ci-integration-native-existing-native-vault-and-independent-cli-processes:
    set -euo pipefail
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- build cargo test --locked --test enrollments_native

[group('ci')]
[script('bash')]
ci-integration-native-public-native-configuration-across-independent-cli-processes:
    set -euo pipefail
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- build cargo test --locked --test enrollments_native public_native_configuration_keeps_original_context_across_cli_restarts -- --ignored

[group('ci')]
[script('bash')]
ci-integration-native-fresh-concurrent-linux-clients-and-independent-cli-processes:
    set -euo pipefail
    bash .github/scripts/check-native-secret-service.sh

[group('ci')]
[script('bash')]
ci-cli-native-boundary-checks:
    set -euo pipefail
    cd apps/cli
    cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- resources --check
    cargo fmt --check
    cargo fmt --manifest-path xtask/Cargo.toml --check
    cargo clippy --locked --manifest-path xtask/Cargo.toml --all-targets -- -D warnings
    cargo test --locked --manifest-path xtask/Cargo.toml
    cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- build \
      cargo clippy --locked --all-targets -- -D warnings
    cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- build cargo test --locked
    cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- build \
      cargo build --locked --release --bins --examples

[group('ci')]
[script('bash')]
ci-cli-existing-consumers-and-real-sqlite-backup:
    set -euo pipefail
    binary="$(
      cd apps/cli &&
        cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- cli-binary
    )"
    printf 'AI_STP_TEST_CLI_BINARY=%s\n' "$binary" >> "${GITHUB_ENV}"
    uv run --no-sync python tests/native_contract/verify.py "$binary"

[group('ci')]
[script('bash')]
ci-cli-build-the-immutable-previous-schema58-native-writer:
    set -euo pipefail
    bash .github/scripts/build-previous-native-cli.sh 58

[group('ci')]
[script('bash')]
ci-cli-build-the-qualified-previous-schema59-binding-writer:
    set -euo pipefail
    bash .github/scripts/build-previous-native-cli.sh 59

[group('ci')]
[script('bash')]
ci-cli-verify-the-immutable-released-schema60-native-writer:
    set -euo pipefail
    python3 .github/scripts/released-previous-native-cli.py "${RUNNER_TEMP}/ai-stp-previous-native-60-release"

[group('ci')]
[script('bash')]
ci-cli-verify-the-immutable-released-schema61-native-writer:
    set -euo pipefail
    python3 .github/scripts/released-previous-native-cli.py "${RUNNER_TEMP}/ai-stp-previous-native-61-release" --schema 61

[group('ci')]
[script('bash')]
ci-cli-ownership-and-corporate-journeys-through-the-native-http-client:
    set -euo pipefail
    docker run --detach --name ai-stp-native-ownership \
      -e POSTGRES_USER=ai_stp -e POSTGRES_PASSWORD=ai_stp_dev -e POSTGRES_DB=ai_stp \
      -p 127.0.0.1:15432:5432 \
      docker.io/library/postgres:18@sha256:5a5a84b19854a9ffaa54082c166ff4ec27473a361e496e5ea167f298f2da9722
    trap 'docker rm --force ai-stp-native-ownership >/dev/null' EXIT
    bash .github/scripts/wait-postgres.sh ai-stp-native-ownership
    uv sync --locked
    uv run --locked python -m tests.native_contract.verify_ownership \
      "${AI_STP_TEST_CLI_BINARY}"
    uv run --locked python -m tests.native_contract.verify_corporate \
      "${AI_STP_TEST_CLI_BINARY}"

[group('ci')]
[script('bash')]
ci-docs-prepare-and-check-the-documentation:
    set -euo pipefail
    source .github/scripts/provider-safe-path.sh
    ai_stp_use_provider_safe_path
    uv sync --locked --group docs --group dev
    (cd docs_scripts && bun install --frozen-lockfile)
    just docs-check

[group('ci')]
[script('bash')]
ci-docs-build-the-pinned-production-docs-image:
    set -euo pipefail
    docker build --file deploy/docker/Dockerfile.docs --target prod --tag ai-stp-docs-qualified:"${GITHUB_SHA}" .

[group('ci')]
[script('bash')]
ci-docs-qualify-the-actual-unprivileged-docs-process-and-both-languages:
    set -euo pipefail
    timeout --signal=TERM --kill-after=35s 120s python .github/scripts/qualify-docs-runtime.py --image ai-stp-docs-qualified:"${GITHUB_SHA}" --source "${GITHUB_SHA}" --proof "${RUNNER_TEMP}/docs-runtime-proof.json"

[group('ci')]
[script('bash')]
ci-package-static-analysis-packaging-and-the-install-regression:
    set -euo pipefail
    source .github/scripts/provider-safe-path.sh
    ai_stp_use_provider_safe_path
    uv sync --locked --group docs --group dev
    just back-static back-regress

[group('ci')]
[positional-arguments]
[script('bash')]
ci-tests-run-a-shard-of-the-test-suite +args:
    set -euo pipefail
    source .github/scripts/provider-safe-path.sh
    ai_stp_use_provider_safe_path
    uv sync --locked --group dev
    uv run --locked pytest -n 8 --dist=load \
      "$@"

[group('ci')]
[script('bash')]
ci-coverage-combine-shard-coverage-and-report:
    set -euo pipefail
    uv sync --locked --group dev
    uv run --locked coverage combine \
      .coverage.api .coverage.integration .coverage.scenario \
      .coverage.unit-platform .coverage.unit-api .coverage.unit \
      .coverage.contract .coverage.property
    uv run --locked coverage report --precision=2

[group('ci')]
[script('bash')]
ci-web-static-build-static-check-audit-and-storybook:
    set -euo pipefail
    cd apps/web
    bun install --frozen-lockfile
    AI_STP_WEB_PROFILE=public_saas bun run build
    bun run i18n:check
    bun run lint
    bun run format:check
    bun run type-check
    bun run audit
    bun run build-storybook

[group('ci')]
[script('bash')]
ci-web-static-dependency-advisory-scan-with-bounded-source-assessments:
    set -euo pipefail
    bash scripts/safety/scan_lockfile.sh

[group('ci')]
[script('bash')]
ci-web-unit-unit-and-component-tests:
    set -euo pipefail
    cd apps/web
    bun install --frozen-lockfile
    bun run test:coverage
    bun run test:coverage:catalog

[group('ci')]
[script('bash')]
ci-web-e2e-ensure-a-google-chrome-is-present:
    set -euo pipefail
    bash .github/scripts/ensure-chrome.sh

[group('ci')]
[positional-arguments]
[script('bash')]
ci-web-e2e-build-and-run-the-browser-scenarios shard:
    set -euo pipefail
    cd apps/web
    bun install --frozen-lockfile
    AI_STP_WEB_PROFILE=public_saas bun run build
    # Two shards, not four, and the difference was measured rather than
    # reasoned about. Four shards do split the suite correctly —
    # 46/44/46/44 whose union is exactly 180 — and bought nothing: the
    # slowest Windows shard ran 269s against 262s at two. The tests were
    # never the cost. Before one of them runs, the Windows leg spends
    # ~140s installing bun and restoring its cache and another ~120s
    # building Next.js, and splitting the list pays that fixed cost on
    # four runners instead of two. It also put six more jobs in a queue
    # that was already the binding constraint, and the run got slower.
    #
    # Serial execution is untouched — `fullyParallel: false` and one
    # worker still hold inside each shard, so the process-local mock
    # state the suite depends on is exactly as isolated as before.
    bun run test:e2e -- --shard=${1:?one browser shard is required}/2

[group('ci')]
[script('bash')]
ci-web-profiles-feature-profile-builds:
    set -euo pipefail
    cd apps/web
    bun install --frozen-lockfile
    bun run test:feature-profiles

[group('ci')]
[script('bash')]
ci-desktop-frontend-checks-tsc-vitest-vite-build:
    set -euo pipefail
    cd apps/desktop
    bun run format:check
    bun run messages:check
    bun x tsc --noEmit
    bun x vitest run
    bun x vite build

[group('ci')]
[script('bash')]
ci-desktop-core-crate-tests:
    set -euo pipefail
    cd apps/desktop/core
    cargo fmt --check
    cargo clippy --locked --all-targets -- -D warnings
    cargo test --locked

[group('ci')]
[script('bash')]
ci-desktop-stub-sidecar-for-shell-crate-checks:
    set -euo pipefail
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- desktop-stub

[group('ci')]
[script('bash')]
ci-desktop-shell-crate-tests:
    set -euo pipefail
    cd apps/desktop/src-tauri
    cargo fmt --check
    cargo clippy --locked --all-targets -- -D warnings
    cargo test --locked

[group('ci')]
[script('bash')]
ci-desktop-build-the-bundled-cli-sidecar:
    set -euo pipefail
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- desktop-build

[group('ci')]
[script('bash')]
ci-desktop-sidecar-spawns-under-the-app-s-filtered-env:
    set -euo pipefail
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- desktop-probe

[group('ci')]
[script('bash')]
ci-desktop-tauri-build:
    set -euo pipefail
    bash .github/scripts/build-desktop-bundles.sh

[group('ci')]
[script('bash')]
ci-desktop-verify-the-macos-disk-image:
    set -euo pipefail
    images=(apps/desktop/src-tauri/target/release/bundle/dmg/*.dmg)
    test "${#images[@]}" -eq 1 && test -f "${images[0]}"
    /usr/bin/hdiutil verify "${images[0]}"

[group('ci')]
[script('bash')]
ci-desktop-probe-the-packaged-cli-resource-tree:
    set -euo pipefail
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- desktop-package-probe

[group('ci')]
[script('bash')]
ci-desktop-three-installed-linux-desktop-journeys-with-bundled-cli-and-native-vault:
    set -euo pipefail
    for round in 1 2 3; do
      printf 'Installed Desktop journey %s/3\n' "${round}"
      bash .github/scripts/check-native-secret-service.sh --installed-desktop
      mv "${RUNNER_TEMP}/installed-desktop-proof.json" \
        "${RUNNER_TEMP}/installed-desktop-proof-${round}.json"
    done

[group('ci')]
[script('bash')]
ci-desktop-installed-corporate-onboarding-lost-reply-and-original-binding-recovery:
    set -euo pipefail
    fixture_postgres="$(docker run --detach --name ai-stp-installed-corporate \
      -e POSTGRES_USER=ai_stp -e POSTGRES_PASSWORD=ai_stp_dev -e POSTGRES_DB=ai_stp \
      -p 127.0.0.1:15434:5432 \
      docker.io/library/postgres:18@sha256:5a5a84b19854a9ffaa54082c166ff4ec27473a361e496e5ea167f298f2da9722)"
    trap 'docker rm --force "${fixture_postgres}" >/dev/null' EXIT
    bash .github/scripts/wait-postgres.sh "${fixture_postgres}"
    uv sync --locked
    bash .github/scripts/check-native-secret-service.sh --installed-corporate-desktop

[group('ci')]
[script('bash')]
ci-build-build-the-native-executable:
    set -euo pipefail
    cd apps/cli
    binary="$(cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- cli-binary)"
    printf 'CLI_SOURCE_BINARY=%s\n' "$binary" >> "${GITHUB_ENV}"

[group('ci')]
[script('bash')]
ci-build-package-and-verify-the-extracted-executable-outside-checkout:
    set -euo pipefail
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- package \
      --binary "${CLI_SOURCE_BINARY}" \
      --target "${RELEASE_TARGET}" --version "${RELEASE_VERSION}" \
      --revision "${GITHUB_SHA}" --output release
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- package \
      --binary "${CLI_SOURCE_BINARY}" \
      --target "${RELEASE_TARGET}" --version "${RELEASE_VERSION}" \
      --revision "${GITHUB_SHA}" --output release-repeat
    stem="ai-stp-cli-${RELEASE_VERSION}-${RELEASE_TARGET}"
    cmp "release/${stem}.${RELEASE_EXTENSION}" "release-repeat/${stem}.${RELEASE_EXTENSION}"
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- verify \
      --archive "release/${stem}.${RELEASE_EXTENSION}" \
      --target "${RELEASE_TARGET}" --version "${RELEASE_VERSION}" \
      --revision "${GITHUB_SHA}" --install-directory "${RUNNER_TEMP}/ai-stp-rust-install"
    uv run --no-sync python tests/native_contract/verify.py \
      "${RUNNER_TEMP}/ai-stp-rust-install/${RELEASE_BINARY}"

[group('ci')]
[script('bash')]
ci-build-package-and-qualify-the-native-wheel:
    set -euo pipefail
    stem="ai-stp-cli-${RELEASE_VERSION}-${RELEASE_TARGET}"
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- wheel \
      --archive "release/${stem}.${RELEASE_EXTENSION}" \
      --target "${RELEASE_TARGET}" --version "${RELEASE_VERSION}" \
      --revision "${GITHUB_SHA}" --output wheels
    wheel=$(find wheels -maxdepth 1 -name '*.whl' -type f)
    test -n "${wheel}"
    uv tool install --no-index "${wheel}"
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- probe \
      --binary "${UV_TOOL_BIN_DIR}/${RELEASE_BINARY}" --version "${RELEASE_VERSION}"
    python -m venv "${RUNNER_TEMP}/pip-native"
    if [[ "${RUNNER_OS}" == Windows ]]; then
      pip_python="${RUNNER_TEMP}/pip-native/Scripts/python.exe"
      pip_binary="${RUNNER_TEMP}/pip-native/Scripts/${RELEASE_BINARY}"
    else
      pip_python="${RUNNER_TEMP}/pip-native/bin/python"
      pip_binary="${RUNNER_TEMP}/pip-native/bin/${RELEASE_BINARY}"
    fi
    "${pip_python}" -m pip install --no-index --no-deps "${wheel}"
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- probe \
      --binary "${pip_binary}" --version "${RELEASE_VERSION}"
    cp "${wheel}" release/
    (cd release && sha256sum -- *.whl > "$(basename "${wheel}").sha256")

[group('ci')]
[script('bash')]
ci-build-qualify-the-standalone-cargo-source-package:
    set -euo pipefail
    cd apps/cli
    cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- resources --check
    cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- \
      build cargo package --locked
    cp "target/package/ai-stp-cli-${RELEASE_VERSION}.crate" ../../release/
    cd ../../release
    sha256sum -- *.crate > "ai-stp-cli-${RELEASE_VERSION}.crate.sha256"

[group('ci')]
[script('bash')]
ci-component-compile-one-portable-component-without-third-party-guest-dependencies:
    set -euo pipefail
    python .github/scripts/qualify-wasi-confinement.py build "${ARTIFACT}"

[group('ci')]
[script('bash')]
ci-confinement-verify-runtime-digest-and-exercise-the-identical-guest-component:
    set -euo pipefail
    python .github/scripts/qualify-wasi-confinement.py exercise "${ARTIFACT}"
