#!/usr/bin/env bash
# Select the installed native GUI owner and exact application source.
set -euo pipefail
bundle="apps/desktop/src-tauri/target/release/bundle"
source="${GITHUB_SHA}"
output="${RUNNER_TEMP}/installed-personal-desktop.json"
if test -n "${AI_STP_DESKTOP_DIAGNOSTIC_SOURCE:-}"; then
  test "${GITHUB_EVENT_NAME}" = workflow_dispatch
  test "${GITHUB_WORKFLOW}" = desktop
  bundle="${RUNNER_TEMP}/qualified-desktop"
  source="${AI_STP_DESKTOP_DIAGNOSTIC_SOURCE}"
fi
case "${RUNNER_OS}" in
  macOS)
    bash .github/scripts/qualify-installed-macos-desktop.sh \
      "${bundle}" "${source}" "${output}"
    ;;
  Windows)
    pwsh -STA -NoProfile -NonInteractive -File \
      .github/scripts/qualify-installed-windows-desktop.ps1 \
      -Bundle "$(cygpath -aw "${bundle}")" -Source "${source}" \
      -Output "$(cygpath -aw "${output}")"
    ;;
  *)
    exit 2
    ;;
esac
