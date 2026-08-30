#!/usr/bin/env bash
# Record an incoming exact tree before rsync can change the remote checkout.

set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo "mark-transfer: expected one full lowercase git SHA" >&2
  exit 2
fi

readonly COMMIT="$1"
readonly ROOT="${AI_STP_REMOTE_ROOT:-${HOME}/ai_stp}"
readonly STATE_DIR="${ROOT}/.deploy-state"
readonly STATE_FILE="${STATE_DIR}/in-progress"

umask 077
mkdir -p "${STATE_DIR}"
temporary="$(mktemp "${STATE_DIR}/in-progress.XXXXXX")"
trap 'rm -f "${temporary}"' EXIT
{
  echo "git_commit=${COMMIT}"
  echo "stage=transfer_started"
  echo "recorded_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${temporary}"
mv -f "${temporary}" "${STATE_FILE}"
trap - EXIT
