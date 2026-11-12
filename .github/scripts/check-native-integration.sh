#!/usr/bin/env bash
# Check native source, platform qualification tools and library units.
set -euo pipefail
case "${RUNNER_OS}" in
  macOS)
    swiftc -typecheck .github/scripts/qualify-installed-macos-desktop.swift
    ;;
  Windows)
    pwsh -NoProfile -NonInteractive -File .github/scripts/check-native-powershell.ps1
    ;;
esac
cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- resources --check
cargo fmt --manifest-path apps/cli/Cargo.toml --check
cargo fmt --manifest-path apps/cli/xtask/Cargo.toml --check
cargo clippy --locked --manifest-path apps/cli/xtask/Cargo.toml \
  --all-targets -- -D warnings
cargo nextest run --locked --manifest-path apps/cli/xtask/Cargo.toml
cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- build \
  cargo clippy --locked --all-targets -- -D warnings
cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- build \
  cargo nextest run --locked --lib
cargo fmt --manifest-path apps/desktop/core/Cargo.toml --check
cargo clippy --locked --manifest-path apps/desktop/core/Cargo.toml \
  --all-targets -- -D warnings
cargo nextest run --locked --manifest-path apps/desktop/core/Cargo.toml
cargo test --locked --manifest-path apps/desktop/core/Cargo.toml --doc
