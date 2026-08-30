#!/usr/bin/env bash
# Restore PostgreSQL logical dump + RustFS objects from a backup directory
# (SPEC-024 REQ-2409, ADR-0044). Rehearsable on a restored copy.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

usage() {
  cat <<'EOF'
Usage: deploy/restore.sh --from BACKUP_DIR [--yes]

Restores:
  - PostgreSQL from postgres/ai_stp.dump via pg_restore
  - RustFS objects by replacing volume contents from rustfs/

Requires explicit --yes. Does not print secrets or object payload bytes.
EOF
}

FROM=""
YES=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      FROM="$2"
      shift 2
      ;;
    --yes)
      YES=1
      shift
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

[[ -n "${FROM}" ]] || die "missing --from BACKUP_DIR"
[[ "${YES}" -eq 1 ]] || die "refusing restore without --yes"
[[ -f "${FROM}/postgres/ai_stp.dump" ]] || die "missing postgres dump in backup"
[[ -d "${FROM}/rustfs" ]] || die "missing rustfs directory in backup"

require_cmd docker
log info "restore_start"

# Stop writers that depend on database/storage identity before restore.
compose stop api worker web seed migrate content-import >/dev/null 2>&1 || true

# Restore PostgreSQL.
compose cp "${FROM}/postgres/ai_stp.dump" postgres:/tmp/ai_stp.dump >/dev/null
if ! compose exec -T postgres sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner /tmp/ai_stp.dump'; then
  die "postgres_restore_failed"
fi
compose exec -T postgres rm -f /tmp/ai_stp.dump >/dev/null 2>&1 || true
log info "postgres_restore_ok"

# Restore RustFS volume contents.
RUSTFS_VOLUME="$(docker volume ls -q | grep -E 'rustfs$' | head -n1 || true)"
[[ -n "${RUSTFS_VOLUME}" ]] || die "rustfs_volume_not_found"
compose stop rustfs >/dev/null 2>&1 || true
if ! docker run --rm \
  -v "${RUSTFS_VOLUME}:/dest" \
  -v "${FROM}/rustfs:/source:ro" \
  alpine:3.20 \
  sh -c 'rm -rf /dest/* /dest/.[!.]* 2>/dev/null || true; cp -a /source/. /dest/'; then
  die "rustfs_restore_failed"
fi
log info "rustfs_restore_ok"

# Bring the stack back; migrate is forward-only and should be a no-op on restored schema.
# Re-import of the current image snapshot is intended: repository articles match
# the image, staff articles come from the backup. Force a new one-shot so an
# already-exited importer container cannot skip the POST.
compose up -d postgres rustfs >/dev/null
compose run --rm migrate >/dev/null
compose rm -fs content-import >/dev/null 2>&1 || true
compose up -d api worker content-import web caddy >/dev/null
wait_for_readiness

log info "restore_complete"
