#!/usr/bin/env bash
set -euo pipefail

# Compile exact previously qualified writers. Common dependency artifacts may
# be reused between these two producers; each installed executable is retained
# separately before the next build can replace the shared target's binary.
previous_epoch="${1:-58}"
case "${previous_epoch}" in
  58)
    previous_commit=0f2589f40e7ebc3155a305965b1056fb6df63581
    previous_tree=61bd5e324d3b3b7817ab54d45f08f24cfb991bcb
    variable=AI_STP_TEST_PREVIOUS_CLI
    ;;
  59)
    previous_commit=b44d1b606f9564741fe2c7eda7aa9ee005d9fa02
    previous_tree=797476ecd2a338612c3b536838b38612fe51ad24
    variable=AI_STP_TEST_PREVIOUS_BINDING_CLI
    ;;
  *) echo "Only the two explicit qualified writer epochs are supported." >&2; exit 2 ;;
esac
previous_root="${RUNNER_TEMP:?}/ai-stp-previous-native-${previous_epoch}-source"
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
mkdir "${previous_root}/installed"
cp "${previous_binary}" "${previous_root}/installed/ai-stp"
cmp "${previous_binary}" "${previous_root}/installed/ai-stp"
previous_binary="${previous_root}/installed/ai-stp"
{
  printf '%s_BINARY=%s\n' "${variable}" "${previous_binary}"
  printf '%s_SOURCE=%s\n' "${variable}" "${previous_commit}"
} >> "${GITHUB_ENV:?}"
sha256sum "${previous_binary}"
