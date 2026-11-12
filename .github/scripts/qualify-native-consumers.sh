#!/usr/bin/env bash
# Qualify existing CLI consumers with the resolved native binary.
set -euo pipefail
binary="$(
  cd apps/cli &&
    cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- cli-binary
)"
printf 'AI_STP_TEST_CLI_BINARY=%s\n' "$binary" >> "${GITHUB_ENV}"
uv run --no-sync python tests/native_contract/verify.py "$binary"
