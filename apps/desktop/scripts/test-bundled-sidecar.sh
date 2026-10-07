#!/usr/bin/env bash
# Spawn the real PyInstaller sidecar through the app's filtered-env runner
# path — the same check desktop.yml runs as "Sidecar spawns under the
# app's filtered env". `CliRunner` clears the child environment and
# re-adds a passthrough set, which is the path the installed app takes;
# the test is inert unless AI_STP_SIDECAR_EXE names a real binary.
#
# Requires the sidecar to exist: run build-cli-sidecar.sh first. The
# triple/suffix derivation mirrors that script so both name the same file.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"

triple="$(rustc -vV | sed -n 's/^host: //p')"
case "${triple}" in
  *windows*) suffix=".exe" ;;
  *) suffix="" ;;
esac

export AI_STP_SIDECAR_EXE="${AI_STP_SIDECAR_EXE:-${repo_root}/apps/desktop/src-tauri/sidecar/cli/ai-stp-desktop-cli${suffix}}"
cd "${repo_root}/apps/desktop/core"
# `--exact` guards the repo's own green-meant-nothing mode: a substring
# filter that matches nothing still exits 0, so name the test precisely.
cargo test --locked --test integration -- --exact bundled_sidecar_spawns_under_runner_env --nocapture
