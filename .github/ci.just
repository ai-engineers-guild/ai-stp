# Execution commands; SDKs, services, permissions and artifacts stay in workflows.

# Seal the exact processed CodeQL payload and its original source provenance.
[group('ci')]
[private]
ci-codeql-retain-analysis:
    python -m release_scripts.code_scanning seal --directory "${SARIF_DIRECTORY}" --output "${SARIF_OUTPUT}" --language "${SOURCE_LANGUAGE}" --sarif-id "${ORIGINAL_SARIF_ID}"

# Admit the exact successful source and active delivery rules without changing refs.
[group('ci')]
[private]
ci-delivery-admit:
    python -m release_scripts.source_promotion

# Reuse every original finding and fingerprint for the exact release source.
[group('ci')]
[private]
ci-delivery-register-findings:
    python -m release_scripts.code_scanning register --directory source-analysis

# Prepare the operator admission, or deploy Main after its explicit promotion.
[group('ci')]
[private]
ci-delivery-promote:
    python -m release_scripts.source_promotion --apply

# Secrets verify the scanner and inspect the selected source.
[group('ci')]
[private]
[script('bash')]
ci-secrets-verify-the-scanner-and-inspect-the-selected-source:
    set -euo pipefail
    python .github/scripts/check-source-secrets.py

# Integration python check source contracts and units without server services.
[group('ci')]
[private]
[script('bash')]
ci-integration-python-check-source-contracts-and-units-without-server-services:
    set -euo pipefail
    source .github/scripts/provider-safe-path.sh
    ai_stp_use_provider_safe_path
    just back-static docs-source docs-test
    uv run --locked pytest -n 8 --dist=load -m 'not pg' tests/unit tests/contract

# Integration web web syntax types and units.
[group('ci')]
[private]
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

# Integration web desktop types and component units.
[group('ci')]
[private]
[script('bash')]
ci-integration-web-desktop-types-and-component-units:
    set -euo pipefail
    cd apps/desktop
    python ../../release_scripts/desktop_version.py --check
    bun install --frozen-lockfile
    bun run format:check
    bun run messages:check
    bun scripts/generate-messages.mjs --check
    bun scripts/generate-theme.mjs --check
    bun scripts/generate-fonts.mjs --check
    bun scripts/generate-contracts.mjs --check
    bun run type-check
    bun x vitest run

# Integration web documentation markdown syntax.
[group('ci')]
[private]
[script('bash')]
ci-integration-web-documentation-markdown-syntax:
    set -euo pipefail
    (cd docs_scripts && bun install --frozen-lockfile)
    python docs_scripts/run_markdownlint.py

# Integration native native formatting all target analysis and library units.
[group('ci')]
[private]
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

# Integration native existing native vault and independent cli processes.
[group('ci')]
[private]
[script('bash')]
ci-integration-native-existing-native-vault-and-independent-cli-processes:
    set -euo pipefail
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- build cargo test --locked --test enrollments_native

# Integration native public native configuration across independent cli processes.
[group('ci')]
[private]
[script('bash')]
ci-integration-native-public-native-configuration-across-independent-cli-processes:
    set -euo pipefail
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- build cargo test --locked --test enrollments_native public_native_configuration_keeps_original_context_across_cli_restarts -- --ignored

# Integration native fresh concurrent linux clients and independent cli processes.
[group('ci')]
[private]
[script('bash')]
ci-integration-native-fresh-concurrent-linux-clients-and-independent-cli-processes:
    set -euo pipefail
    bash .github/scripts/check-native-secret-service.sh

# Cli native boundary checks.
[group('ci')]
[private]
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

# Cli existing consumers and real sqlite backup.
[group('ci')]
[private]
[script('bash')]
ci-cli-existing-consumers-and-real-sqlite-backup:
    set -euo pipefail
    binary="$(
      cd apps/cli &&
        cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- cli-binary
    )"
    printf 'AI_STP_TEST_CLI_BINARY=%s\n' "$binary" >> "${GITHUB_ENV}"
    uv run --no-sync python tests/native_contract/verify.py "$binary"

# Cli build the immutable previous schema58 native writer.
[group('ci')]
[private]
[script('bash')]
ci-cli-build-the-immutable-previous-schema58-native-writer:
    set -euo pipefail
    bash .github/scripts/build-previous-native-cli.sh 58

# Cli build the qualified previous schema59 binding writer.
[group('ci')]
[private]
[script('bash')]
ci-cli-build-the-qualified-previous-schema59-binding-writer:
    set -euo pipefail
    bash .github/scripts/build-previous-native-cli.sh 59

# Cli verify the immutable released schema60 native writer.
[group('ci')]
[private]
[script('bash')]
ci-cli-verify-the-immutable-released-schema60-native-writer:
    set -euo pipefail
    python3 .github/scripts/released-previous-native-cli.py "${RUNNER_TEMP}/ai-stp-previous-native-60-release"

# Cli verify the immutable released schema61 native writer.
[group('ci')]
[private]
[script('bash')]
ci-cli-verify-the-immutable-released-schema61-native-writer:
    set -euo pipefail
    python3 .github/scripts/released-previous-native-cli.py "${RUNNER_TEMP}/ai-stp-previous-native-61-release" --schema 61

# Cli ownership and corporate journeys through the native http client.
[group('ci')]
[private]
ci-cli-ownership-and-corporate-journeys-through-the-native-http-client:
    bash .github/scripts/qualify-native-http-client.sh

# Docs prepare and check the documentation.
[group('ci')]
[private]
[script('bash')]
ci-docs-prepare-and-check-the-documentation:
    set -euo pipefail
    source .github/scripts/provider-safe-path.sh
    ai_stp_use_provider_safe_path
    uv sync --locked --group docs --group dev
    (cd docs_scripts && bun install --frozen-lockfile)
    just docs-check

# Docs build the pinned production docs image.
[group('ci')]
[private]
[script('bash')]
ci-docs-build-the-pinned-production-docs-image:
    set -euo pipefail
    docker build --file deploy/docker/Dockerfile.docs --target prod --tag ai-stp-docs-qualified:"${GITHUB_SHA}" .

# Docs qualify the actual unprivileged docs process and both languages.
[group('ci')]
[private]
[script('bash')]
ci-docs-qualify-the-actual-unprivileged-docs-process-and-both-languages:
    set -euo pipefail
    timeout --signal=TERM --kill-after=35s 120s python .github/scripts/qualify-docs-runtime.py --image ai-stp-docs-qualified:"${GITHUB_SHA}" --source "${GITHUB_SHA}" --proof "${RUNNER_TEMP}/docs-runtime-proof.json"

# Package static analysis packaging and the install regression.
[group('ci')]
[private]
[script('bash')]
ci-package-static-analysis-packaging-and-the-install-regression:
    set -euo pipefail
    source .github/scripts/provider-safe-path.sh
    ai_stp_use_provider_safe_path
    uv sync --locked --group docs --group dev
    just back-static back-regress

# Tests run a shard of the test suite.
[group('ci')]
[positional-arguments]
[private]
[script('bash')]
ci-tests-run-a-shard-of-the-test-suite +args:
    set -euo pipefail
    source .github/scripts/provider-safe-path.sh
    ai_stp_use_provider_safe_path
    uv sync --locked --group dev
    uv run --locked pytest -n 8 --dist=load \
      "$@"

# Coverage combine shard coverage and report.
[group('ci')]
[private]
[script('bash')]
ci-coverage-combine-shard-coverage-and-report:
    set -euo pipefail
    uv sync --locked --group dev
    uv run --locked coverage combine \
      .coverage.api .coverage.integration .coverage.scenario \
      .coverage.unit-platform .coverage.unit-api .coverage.unit \
      .coverage.contract .coverage.property
    uv run --locked coverage report --precision=2

# Web static build static check audit and storybook.
[group('ci')]
[private]
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

# Web static dependency advisory scan with bounded source assessments.
[group('ci')]
[private]
[script('bash')]
ci-web-static-dependency-advisory-scan-with-bounded-source-assessments:
    set -euo pipefail
    bash scripts/safety/scan_lockfile.sh

# Web unit unit and component tests.
[group('ci')]
[private]
[script('bash')]
ci-web-unit-unit-and-component-tests:
    set -euo pipefail
    cd apps/web
    bun install --frozen-lockfile
    bun run test:coverage
    bun run test:coverage:catalog

# Web e2e ensure a google chrome is present.
[group('ci')]
[private]
[script('bash')]
ci-web-e2e-ensure-a-google-chrome-is-present:
    set -euo pipefail
    bash .github/scripts/ensure-chrome.sh

# Web e2e build and run the browser scenarios.
[group('ci')]
[positional-arguments]
[private]
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

# Web profiles feature profile builds.
[group('ci')]
[private]
[script('bash')]
ci-web-profiles-feature-profile-builds:
    set -euo pipefail
    cd apps/web
    bun install --frozen-lockfile
    bun run test:feature-profiles

# Desktop tauri build.
[group('ci')]
[private]
[script('bash')]
ci-desktop-tauri-build:
    set -euo pipefail
    bash .github/scripts/build-desktop-bundles.sh --frontend-built

# Desktop verify the macos disk image.
[group('ci')]
[private]
[script('bash')]
ci-desktop-verify-the-macos-disk-image:
    set -euo pipefail
    images=(apps/desktop/src-tauri/target/release/bundle/dmg/*.dmg)
    test "${#images[@]}" -eq 1 && test -f "${images[0]}"
    /usr/bin/hdiutil verify "${images[0]}"

# Desktop probe the packaged cli resource tree.
[group('ci')]
[private]
[script('bash')]
ci-desktop-probe-the-packaged-cli-resource-tree:
    set -euo pipefail
    cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- desktop-package-probe

# Desktop three installed linux desktop journeys with bundled cli and native vault.
[group('ci')]
[private]
ci-desktop-three-installed-linux-desktop-journeys-with-bundled-cli-and-native-vault:
    bash .github/scripts/run-installed-desktop-journeys.sh

# Desktop installed corporate onboarding lost reply and original binding recovery.
[group('ci')]
[private]
ci-desktop-installed-corporate-onboarding-lost-reply-and-original-binding-recovery:
    bash .github/scripts/qualify-installed-corporate-desktop.sh

# Build build the native executable.
[group('ci')]
[private]
[script('bash')]
ci-build-build-the-native-executable:
    set -euo pipefail
    cd apps/cli
    binary="$(cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- cli-binary)"
    printf 'CLI_SOURCE_BINARY=%s\n' "$binary" >> "${GITHUB_ENV}"

# Build package and verify the extracted executable outside checkout.
[group('ci')]
[private]
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

# Build package and qualify the native wheel.
[group('ci')]
[private]
ci-build-package-and-qualify-the-native-wheel:
    bash .github/scripts/qualify-native-wheel.sh

# Build qualify the standalone cargo source package.
[group('ci')]
[private]
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

# Component compile one portable component without third party guest dependencies.
[group('ci')]
[private]
[script('bash')]
ci-component-compile-one-portable-component-without-third-party-guest-dependencies:
    set -euo pipefail
    python .github/scripts/qualify-wasi-confinement.py build "${ARTIFACT}"

# Confinement verify runtime digest and exercise the identical guest component.
[group('ci')]
[private]
[script('bash')]
ci-confinement-verify-runtime-digest-and-exercise-the-identical-guest-component:
    set -euo pipefail
    python .github/scripts/qualify-wasi-confinement.py exercise "${ARTIFACT}"
