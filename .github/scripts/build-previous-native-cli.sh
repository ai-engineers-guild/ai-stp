#!/usr/bin/env bash
set -euo pipefail

# Compile an immutable, previously qualified schema58 writer. Keep both its
# xtask and crate artifacts separate from the candidate under qualification.
previous_commit=0f2589f40e7ebc3155a305965b1056fb6df63581
previous_tree=61bd5e324d3b3b7817ab54d45f08f24cfb991bcb
previous_root="${RUNNER_TEMP:?}/ai-stp-previous-native-source"
test ! -e "${previous_root}"
git fetch --no-tags origin "${previous_commit}"
test "$(git rev-parse FETCH_HEAD)" = "${previous_commit}"
test "$(git show --no-patch --format=%T "${previous_commit}")" = "${previous_tree}"
mkdir -p "${previous_root}"
git archive --format=tar "${previous_commit}" apps/cli |
  tar --extract --directory="${previous_root}"
cmp apps/cli/rust-toolchain.toml "${previous_root}/apps/cli/rust-toolchain.toml"
export CARGO_TARGET_DIR="${RUNNER_TEMP}/ai-stp-previous-native-target"
export CARGO_BUILD_BUILD_DIR="${RUNNER_TEMP}/ai-stp-previous-native-build"
cd "${previous_root}/apps/cli"
previous_binary="$(cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- cli-binary)"
test -x "${previous_binary}"
case "${previous_binary}" in
  /*) ;;
  *) exit 1 ;;
esac
{
  printf 'AI_STP_TEST_PREVIOUS_CLI_BINARY=%s\n' "${previous_binary}"
  printf 'AI_STP_TEST_PREVIOUS_CLI_SOURCE=%s\n' "${previous_commit}"
} >> "${GITHUB_ENV:?}"
sha256sum "${previous_binary}"
