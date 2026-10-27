#!/usr/bin/env bash
set -euo pipefail

# Compile exact previously qualified writers. xtask embeds its manifest directory;
# sharing its build artifacts can execute the other checkout's build commands.
# Keep source-dependent artifacts isolated by immutable commit. Cargo's ordinary
# registry/download cache remains shared on the runner.
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
export CARGO_TARGET_DIR="${RUNNER_TEMP}/ai-stp-previous-native-${previous_commit}-target"
export CARGO_BUILD_BUILD_DIR="${RUNNER_TEMP}/ai-stp-previous-native-${previous_commit}-build"
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
python3 - "${previous_binary}" "${previous_epoch}" "${previous_root}" <<'PY'
import json
import pathlib
import subprocess
import sys

binary, epoch, root = sys.argv[1:]
home = pathlib.Path(root) / "qualification-home"
home.mkdir()
environment = {key: str(home) for key in (
    "HOME", "USERPROFILE", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"
)}
environment["PATH"] = ""
result = subprocess.run(
    [binary, "help", "--json"], cwd=home, env=environment,
    capture_output=True, check=True, timeout=30,
)
assert not result.stderr and len(result.stdout) <= 1024 * 1024
envelope = json.loads(result.stdout)
assert envelope["ok"] is True
metadata = envelope["data"]
assert metadata["schema_version"] == 1 and metadata["cli_version"] == "0.1.3"
paths = [tuple(command["path"]) for command in metadata["commands"]]
assert len(paths) == len(set(paths))
assert ("corporate", "project", "link-request", "plan") in paths
assert (("corporate", "project", "unlink-request", "plan") in paths) == (epoch == "59")
assert (("corporate", "project", "unlink", "apply") in paths) == (epoch == "59")
assert ("corporate", "project", "binding-retire", "plan") not in paths
assert not any(home.iterdir()), "metadata probe created persistent state"
print(f"Verified previous writer {epoch} command boundary: {metadata['registry_digest']}")
PY
if [[ "${previous_epoch}" == 59 ]]; then
  test -x "${AI_STP_TEST_PREVIOUS_CLI_BINARY:?}"
  if cmp --silent "${previous_binary}" "${AI_STP_TEST_PREVIOUS_CLI_BINARY}"; then
    echo "Independent previous writers unexpectedly have identical bytes." >&2
    exit 1
  fi
fi
{
  printf '%s_BINARY=%s\n' "${variable}" "${previous_binary}"
  printf '%s_SOURCE=%s\n' "${variable}" "${previous_commit}"
} >> "${GITHUB_ENV:?}"
sha256sum "${previous_binary}"
