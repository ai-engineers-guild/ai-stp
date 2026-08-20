#!/usr/bin/env bash
# Lower the schema to an exact revision (SPEC-024 REQ-2418, ADR-0081).
#
# Separate from rollback.sh on purpose. Rolling the application back is a
# frequent, cheap operation and must never cost data; lowering the schema can
# cost data and must therefore be asked for. Keeping them in one command is what
# made the whole thing dangerous enough to forbid.
#
# The backup is taken here rather than assumed: a copy made yesterday does not
# cover a column dropped today, and "there is a backup somewhere" is exactly the
# belief that loses one.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

usage() {
  cat <<'EOF'
Usage: deploy/downgrade.sh --to <revision> [--yes] [--skip-backup]

Lowers the database schema to <revision> via `alembic downgrade`, under the
deploy lock, after taking a backup in this same run.

  --to <revision>  exact target revision, or `-1` for one step back. Required:
                   there is no default, because a default target is a guess
                   about which data may be lost.
  --yes            required. Confirms the target after reading it back.
  --skip-backup    refuses unless AI_STP_DOWNGRADE_ACCEPT_DATA_LOSS=1 is also
                   set. For a scratch stack that holds nothing worth keeping.

The current revision is printed before anything runs, and both revisions are
recorded in the deploy state so the next operator can see what happened here.
EOF
}

TARGET=""
YES=0
SKIP_BACKUP=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --to)
      [[ $# -ge 2 ]] || die "--to requires a revision"
      TARGET="$2"
      shift 2
      ;;
    --yes)
      YES=1
      shift
      ;;
    --skip-backup)
      SKIP_BACKUP=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "${TARGET}" ]] || die "refusing downgrade without an explicit --to <revision>"
[[ "${YES}" -eq 1 ]] || die "refusing downgrade without --yes"
if [[ "${SKIP_BACKUP}" -eq 1 && "${AI_STP_DOWNGRADE_ACCEPT_DATA_LOSS:-0}" != "1" ]]; then
  die "--skip-backup requires AI_STP_DOWNGRADE_ACCEPT_DATA_LOSS=1"
fi

require_cmd docker
require_cmd flock
ensure_state_dir
acquire_deploy_lock
trap release_deploy_lock EXIT

# Read the current revision before touching anything: the record is only useful
# if it says where this started, and an operator who mistyped the target finds
# out here rather than afterwards.
FROM_REVISION="$(compose run --rm --entrypoint alembic migrate current 2>/dev/null | tail -n1 | awk '{print $1}')"
[[ -n "${FROM_REVISION}" ]] || die "could not read the current schema revision"
log info "downgrade_start"
log info "from_revision=${FROM_REVISION}"
log info "to_revision=${TARGET}"

BACKUP_NAME="none"
if [[ "${SKIP_BACKUP}" -eq 0 ]]; then
  # backup.sh names the directory itself and prints the path as its last line;
  # taking the name from there rather than guessing it keeps one owner for the
  # naming rule.
  BACKUP_PATH="$("${SCRIPT_DIR}/backup.sh" --label downgrade | tail -n1)"
  [[ -s "${BACKUP_PATH}/postgres/ai_stp.dump" ]] ||
    die "backup produced no dump at ${BACKUP_PATH}; refusing to downgrade"
  BACKUP_NAME="$(basename "${BACKUP_PATH}")"
  log info "backup_ok name=${BACKUP_NAME}"
fi

compose run --rm --entrypoint alembic migrate downgrade "${TARGET}"
NOW_REVISION="$(compose run --rm --entrypoint alembic migrate current 2>/dev/null | tail -n1 | awk '{print $1}')"
log info "downgrade_ok revision=${NOW_REVISION}"

{
  echo "from_revision=${FROM_REVISION}"
  echo "to_revision=${NOW_REVISION}"
  echo "requested=${TARGET}"
  echo "backup=${BACKUP_NAME}"
  echo "git_commit=$(current_git_commit)"
  echo "at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"${AI_STP_STATE_DIR}/last-downgrade"

log info "downgrade_complete"
