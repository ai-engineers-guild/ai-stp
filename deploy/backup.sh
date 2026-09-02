#!/usr/bin/env bash
# On-demand or scheduled backup of PostgreSQL logical dump + RustFS object copy
# (SPEC-024 REQ-2409, ADR-0044). Logs carry no secrets or object bytes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

usage() {
  cat <<'EOF'
Usage: deploy/backup.sh [--label NAME]

Creates a timestamped backup under AI_STP_BACKUP_DIR (default: .backups/):
  - PostgreSQL logical dump via pg_dump inside the postgres service
  - RustFS/object data directory copy from the rustfs volume mount

Environment:
  AI_STP_COMPOSE_FILE   compose file (default docker-compose.prod.yml)
  AI_STP_BACKUP_DIR     backup root directory
  AI_STP_BACKUP_RETENTION  number of newest backups to keep (default 7)

Does not print connection strings, credentials, or object payload bytes.
EOF
}

LABEL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --label)
      LABEL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

require_cmd docker
require_cmd sha256sum
ensure_state_dir

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -n "${LABEL}" ]]; then
  SAFE_LABEL="$(printf '%s' "${LABEL}" | tr -cd 'A-Za-z0-9._-')"
  NAME="${STAMP}-${SAFE_LABEL}"
else
  NAME="${STAMP}"
fi
DEST="${AI_STP_BACKUP_DIR}/${NAME}"
mkdir -p "${DEST}/postgres" "${DEST}/rustfs"

log info "backup_start name=${NAME}"

# Hold every application writer while PostgreSQL and RustFS are copied. Without
# this, the two individually valid snapshots can describe different moments.
WRITERS_PAUSED=0
resume_writers() {
  if [[ "${WRITERS_PAUSED}" -eq 1 ]]; then
    compose unpause api worker >/dev/null 2>&1 || true
  fi
}
trap resume_writers EXIT
compose pause api worker >/dev/null
WRITERS_PAUSED=1

# PostgreSQL logical dump. Credentials stay inside the container env; not logged.
if ! compose exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --file=/tmp/ai_stp.dump' \
  >/dev/null; then
  die "postgres_dump_failed"
fi
if ! compose exec -T postgres sh -c \
  'pg_restore --list /tmp/ai_stp.dump | awk '\''$4 == "TABLE" && $5 == "DATA" && $6 == "public" && $7 == "oauth_identity" { found=1 } END { exit !found }'\'''; then
  die "postgres_dump_missing_oauth_identity"
fi
if ! compose exec -T postgres sh -c \
  'pg_restore --list /tmp/ai_stp.dump | awk '\''$4 == "SEQUENCE" && $5 == "SET" && $6 == "public" && $7 == "oauth_identity_id_seq" { found=1 } END { exit !found }'\'''; then
  die "postgres_dump_missing_oauth_identity_sequence"
fi
ACCOUNT_COUNT="$(compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT count(*) FROM account"')"
OAUTH_IDENTITY_COUNT="$(compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT count(*) FROM oauth_identity"')"
OAUTH_IDENTITY_FINGERPRINT="$(oauth_identity_fingerprint)"
[[ "${ACCOUNT_COUNT}" =~ ^[0-9]+$ ]] || die "postgres_account_count_failed"
[[ "${OAUTH_IDENTITY_COUNT}" =~ ^[0-9]+$ ]] || die "postgres_oauth_identity_count_failed"
[[ "${OAUTH_IDENTITY_FINGERPRINT}" =~ ^[0-9a-f]{64}$ ]] || die "postgres_oauth_identity_fingerprint_failed"
if ! compose cp postgres:/tmp/ai_stp.dump "${DEST}/postgres/ai_stp.dump" >/dev/null; then
  die "postgres_dump_copy_failed"
fi
compose exec -T postgres rm -f /tmp/ai_stp.dump >/dev/null 2>&1 || true

# RustFS object copy: copy the service data volume contents without listing object bytes.
# Uses a temporary alpine helper sharing the rustfs volume.
RUSTFS_VOLUME="$(compose_service_volume rustfs /data)"

if ! docker run --rm \
  -v "${RUSTFS_VOLUME}:/source:ro" \
  -v "${DEST}/rustfs:/dest" \
  alpine:3.20 \
  sh -c 'cp -a /source/. /dest/ && find /dest -type f | wc -l' \
  >"${DEST}/rustfs.file_count.txt"; then
  die "rustfs_copy_failed"
fi

{
  echo "name=${NAME}"
  echo "created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_commit=$(current_git_commit)"
  echo "postgres_dump=postgres/ai_stp.dump"
  echo "account_count=${ACCOUNT_COUNT}"
  echo "oauth_identity_count=${OAUTH_IDENTITY_COUNT}"
  echo "oauth_identity_fingerprint=${OAUTH_IDENTITY_FINGERPRINT}"
  echo "rustfs_dir=rustfs/"
  echo "file_count=$(tr -d '[:space:]' <"${DEST}/rustfs.file_count.txt" 2>/dev/null || echo 0)"
} >"${DEST}/MANIFEST.txt"

resume_writers
WRITERS_PAUSED=0
trap - EXIT

# Bounded retention: keep the newest N backup directories.
mapfile -t ALL_BACKUPS < <(ls -1dt "${AI_STP_BACKUP_DIR}"/*/ 2>/dev/null || true)
COUNT=0
for dir in "${ALL_BACKUPS[@]:-}"; do
  COUNT=$((COUNT + 1))
  if ((COUNT > AI_STP_BACKUP_RETENTION)); then
    rm -rf "${dir}"
    log info "backup_pruned"
  fi
done

log info "backup_complete name=${NAME}"
printf '%s\n' "${DEST}"
