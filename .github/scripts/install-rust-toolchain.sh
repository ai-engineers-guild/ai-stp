#!/usr/bin/env bash
# Retry transient bootstrap failures without changing the repository's pin.
set -euo pipefail

toolchain_file="${1:?the native toolchain file is required}"
shift
toolchain="$(sed -n 's/^channel = "\(.*\)"/\1/p' "${toolchain_file}")"
if [[ ! "${toolchain}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "The native toolchain must name one exact stable Rust version." >&2
  exit 2
fi

arguments=(toolchain install "${toolchain}" --profile minimal --no-self-update)
for component in "$@"; do
  case "${component}" in
    clippy|rustfmt) arguments+=(--component "${component}") ;;
    *) echo "The native bootstrap component is unsupported." >&2; exit 2 ;;
  esac
done

for attempt in 1 2 3; do
  if rustup "${arguments[@]}"; then
    printf 'RUSTUP_TOOLCHAIN=%s\n' "${toolchain}" >> "${GITHUB_ENV:?the job environment file is required}"
    exit 0
  else
    status=$?
  fi
  if [[ "${attempt}" == 3 ]]; then
    exit "${status}"
  fi
  echo "Retrying the same pinned Rust toolchain after attempt ${attempt}." >&2
  sleep "$((attempt * 2))"
done
