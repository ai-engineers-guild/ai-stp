#!/usr/bin/env bash
# Refresh OSV offline vulnerability databases into AI_STP_OSV_OFFLINE_DIR.
#
# osv-scanner loads packs from OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY only
# (https://google.github.io/osv-scanner/usage/offline-mode/). Layout:
#   {cache}/osv-scanner/{ecosystem}/all.zip
#
# Primary path: HTTP download from osv-vulnerabilities.storage.googleapis.com
# (official mirror). Optional secondary: osv-scanner --download-offline-databases.
# Stamp is written only when at least one all.zip pack is present.
set -euo pipefail

DEST="${AI_STP_OSV_OFFLINE_DIR:-/var/lib/ai_stp/osv}"
MAX_AGE_HOURS="${AI_STP_OSV_MAX_AGE_HOURS:-36}"
MARKER="${DEST}/.ai_stp_osv_refreshed_at"
# Limit ecosystems when AI_STP_OSV_ECOSYSTEMS is set. Commas separate exact
# ecosystem names; a legacy whitespace-separated list remains supported when
# the complete value is not itself an upstream ecosystem name.
# Empty = all ecosystems listed upstream (large download).
ECOSYSTEMS_FILTER="${AI_STP_OSV_ECOSYSTEMS:-}"
BASE_URL="${AI_STP_OSV_MIRROR:-https://osv-vulnerabilities.storage.googleapis.com}"

export OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY="${DEST}"
export PATH="/opt/safety-bin:/opt/safety-venv/bin:/app/.venv/bin:${PATH}"

log() { printf 'refresh_osv_db: %s\n' "$*" >&2; }

count_packs() {
  find "${DEST}" -type f -name 'all.zip' 2>/dev/null | wc -l | tr -d ' '
}

mkdir -p "${DEST}/osv-scanner"
log "cache=${OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY} packs_before=$(count_packs)"

tmp="$(mktemp -d)"
cleanup() { rm -rf "${tmp}"; }
trap cleanup EXIT

download() {
  # download URL DEST
  local url="$1" dest="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 3 --retry-delay 2 -o "${dest}" "${url}"
    return $?
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 - "${url}" "${dest}" <<'PY'
import sys, urllib.request
url, dest = sys.argv[1], sys.argv[2]
urllib.request.urlretrieve(url, dest)
PY
    return $?
  fi
  log "curl or python3 required to download OSV packs"
  return 1
}

url_path_segment() {
  python3 - "$1" <<'PY'
import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=""))
PY
}

valid_zip() {
  python3 - "$1" <<'PY'
import sys
import zipfile

try:
    with zipfile.ZipFile(sys.argv[1]) as archive:
        raise SystemExit(0 if archive.testzip() is None else 1)
except (OSError, zipfile.BadZipFile):
    raise SystemExit(1)
PY
}

eco_list="${tmp}/ecosystems.txt"
if ! download "${BASE_URL}/ecosystems.txt" "${eco_list}"; then
  log "failed to fetch ecosystems.txt from ${BASE_URL}"
  exit 1
fi

mapfile -t ALL_ECOS < <(
  tr -d '\r' < "${eco_list}" \
    | grep -v '^[[:space:]]*$' \
    | grep -v '^\[EMPTY\]$'
)
if [[ "${#ALL_ECOS[@]}" -eq 0 ]]; then
  log "ecosystems.txt empty"
  exit 1
fi

SELECTED=()
if [[ -n "${ECOSYSTEMS_FILTER}" ]]; then
  filter_items=()
  if [[ "${ECOSYSTEMS_FILTER}" == *,* ]]; then
    IFS=',' read -r -a raw_filter_items <<< "${ECOSYSTEMS_FILTER}"
    for want in "${raw_filter_items[@]}"; do
      want="${want#"${want%%[![:space:]]*}"}"
      want="${want%"${want##*[![:space:]]}"}"
      [[ -n "${want}" ]] && filter_items+=("${want}")
    done
  elif printf '%s\n' "${ALL_ECOS[@]}" | grep -Fxq -- "${ECOSYSTEMS_FILTER}"; then
    filter_items=("${ECOSYSTEMS_FILTER}")
  else
    # shellcheck disable=SC2206
    filter_items=(${ECOSYSTEMS_FILTER})
  fi
  for eco in "${ALL_ECOS[@]}"; do
    for want in "${filter_items[@]}"; do
      if [[ "${eco}" == "${want}" ]]; then
        SELECTED+=("${eco}")
      fi
    done
  done
else
  SELECTED=("${ALL_ECOS[@]}")
fi

if [[ "${#SELECTED[@]}" -eq 0 ]]; then
  log "no ecosystems selected (filter=${ECOSYSTEMS_FILTER})"
  exit 1
fi

downloaded=0
failed=0
for eco in "${SELECTED[@]}"; do
  target_dir="${DEST}/osv-scanner/${eco}"
  mkdir -p "${target_dir}"
  target="${target_dir}/all.zip"
  partial="${target}.partial"
  encoded_eco="$(url_path_segment "${eco}")"
  url="${BASE_URL}/${encoded_eco}/all.zip"
  log "fetch ${eco}"
  if download "${url}" "${partial}"; then
    size="$(wc -c < "${partial}" | tr -d ' ')"
    if [[ "${size}" -lt 32 ]]; then
      log "skip ${eco}: download too small (${size} bytes)"
      rm -f "${partial}"
      failed=$((failed + 1))
      continue
    fi
    if ! valid_zip "${partial}"; then
      log "skip ${eco}: invalid zip archive"
      rm -f "${partial}"
      failed=$((failed + 1))
      continue
    fi
    mv "${partial}" "${target}"
    downloaded=$((downloaded + 1))
  else
    log "skip ${eco}: download failed"
    rm -f "${partial}"
    failed=$((failed + 1))
  fi
done

# Optional: also ask osv-scanner to refresh into the same cache (best-effort).
if command -v osv-scanner >/dev/null 2>&1; then
  scan_tmp="$(mktemp -d)"
  printf '%s\n' 'requests==2.0.0' > "${scan_tmp}/requirements.txt"
  osv-scanner scan source --offline-vulnerabilities --download-offline-databases -r "${scan_tmp}" \
    >/dev/null 2>&1 || true
  osv-scanner --offline-vulnerabilities --download-offline-databases "${scan_tmp}" \
    >/dev/null 2>&1 || true
  rm -rf "${scan_tmp}"
fi

after="$(count_packs)"
log "downloaded=${downloaded} failed=${failed} packs_after=${after}"

if [[ "${after}" -eq 0 ]]; then
  log "no all.zip packs under ${DEST}; refusing to stamp fresh"
  exit 1
fi

date -u +%Y-%m-%dT%H:%M:%SZ > "${MARKER}"
{
  echo "refreshed_at_utc=$(cat "${MARKER}")"
  echo "max_age_hours=${MAX_AGE_HOURS}"
  echo "dir=${DEST}"
  echo "cache_env=OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY"
  echo "zip_count=${after}"
  echo "downloaded=${downloaded}"
  echo "failed=${failed}"
} > "${DEST}/STATUS.txt"

log "refresh complete: $(cat "${MARKER}") zip_count=${after}"
exit 0
