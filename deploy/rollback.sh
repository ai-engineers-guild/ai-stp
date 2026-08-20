#!/usr/bin/env bash
# Rollback by redeploying the previous exact git commit artifact
# (SPEC-024 REQ-2410, ADR-0044).
#
# NEVER runs a destructive schema down-migration. Schema remains at the current
# head; only application images/code revert. Incompatible schema changes require
# a separate procedure (docs/engineering/schema-evolution.md).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

usage() {
  cat <<'EOF'
Usage: deploy/rollback.sh [--yes]

Redeploys the commit recorded in .deploy-state/previous by checking out that
commit (detached), building, and running the same deploy path without any
alembic downgrade.

Requires explicit --yes. Leaves the working tree on the rollback commit;
operators re-attach or create a branch as needed.
EOF
}

YES=0
while [[ $# -gt 0 ]]; do
  case "$1" in
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

[[ "${YES}" -eq 1 ]] || die "refusing rollback without --yes"
[[ -f "${AI_STP_STATE_DIR}/previous" ]] || die "no previous artifact recorded; cannot rollback"

require_cmd docker
require_cmd git
require_cmd flock
ensure_state_dir
acquire_deploy_lock
trap release_deploy_lock EXIT

PREV_COMMIT="$(grep -E '^git_commit=' "${AI_STP_STATE_DIR}/previous" | head -n1 | cut -d= -f2-)"
[[ -n "${PREV_COMMIT}" && "${PREV_COMMIT}" != "unknown" ]] || die "previous git_commit missing"

log info "rollback_start"
log info "target_git_commit=${PREV_COMMIT}"

# Save current as the new previous before switching.
if [[ -f "${AI_STP_STATE_DIR}/current" ]]; then
  cp -f "${AI_STP_STATE_DIR}/current" "${AI_STP_STATE_DIR}/previous"
fi

git -C "${AI_STP_ROOT}" checkout --detach "${PREV_COMMIT}"
export AI_STP_API_GIT_COMMIT="${PREV_COMMIT}"

compose config >/dev/null
compose build
# Forward-only migrate: no downgrade. If the previous app is incompatible with
# the current schema, readiness will fail and we abort.
compose up -d postgres rustfs
compose run --rm migrate
compose run --rm seed || true
compose up -d api worker web caddy

wait_for_liveness
wait_for_readiness

write_artifact_record "${AI_STP_STATE_DIR}/current"
log info "rollback_complete"
