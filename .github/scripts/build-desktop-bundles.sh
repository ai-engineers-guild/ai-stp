#!/usr/bin/env bash
# Compile once; retry only the known macOS disk-image creation contention.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../../apps/desktop"
configuration=()
if [[ "$#" -eq 1 && "$1" == --frontend-built ]]; then
  test -f dist/index.html
  configuration+=(--config ../../.github/tauri-frontend-built.conf.json)
elif [[ "$#" -ne 0 ]]; then
  echo 'Usage: build-desktop-bundles.sh [--frontend-built]' >&2
  exit 64
fi
# Cargo cache restores can retain installers from a previous package version.
# Rebuild only this generated output; keep compiler artifacts and strict probes.
rm -rf -- src-tauri/target/release/bundle
if [[ "${RUNNER_OS:-}" == Windows ]]; then
  exec bun x tauri build "${configuration[@]}" --config ../../.github/tauri-tools-windows.conf.json
fi
if [[ "${RUNNER_OS:-}" != macOS ]]; then
  exec bun x tauri build "${configuration[@]}"
fi

# Keep compilation and its hooks outside the idempotent packaging retry.
bun x tauri build "${configuration[@]}" --no-bundle
: "${RUNNER_TEMP:?the disposable runner temporary directory is required}"
bundle_log="$(mktemp "${RUNNER_TEMP}/ai-stp-dmg.XXXXXX")"
trap 'rm -f -- "${bundle_log}"' EXIT

for bundle_attempt in 1 2 3; do
  if bun x tauri bundle >"${bundle_log}" 2>&1; then
    cat "${bundle_log}"
    exit 0
  else
    bundle_status=$?
  fi
  cat "${bundle_log}"
  if ! LC_ALL=C grep -Fq -- 'hdiutil: create failed - Resource busy' "${bundle_log}"; then
    exit "${bundle_status}"
  fi
  if [[ "${bundle_attempt}" -eq 3 ]]; then
    exit "${bundle_status}"
  fi
  printf 'macOS DMG creation is busy; retrying packaging (%s/3).\n' \
    "$((bundle_attempt + 1))"
  sleep "$((bundle_attempt * 2))"
done
