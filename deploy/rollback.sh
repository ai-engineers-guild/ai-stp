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

if [[ -d "${AI_STP_ROOT}/.git" ]]; then
  # Repo-model root: the previous artifact is a commit the checkout can
  # return to directly.
  require_cmd git
  git -C "${AI_STP_ROOT}" checkout --detach "${PREV_COMMIT}"
else
  # Pull-model root: no .git exists here — pull-deploy.sh materializes each
  # ref into ${release_root}/<sha> and keeps exactly the live tree and the
  # previous one, which is the artifact this rollback restores. The exclude
  # list matches the promote rsync so runtime state is never clobbered.
  require_cmd rsync
  RELEASE_ROOT="${AI_STP_PULL_STATE_ROOT:-${HOME}/.local/state/ai-stp-deployer}/releases"
  PREV_TREE="${RELEASE_ROOT}/${PREV_COMMIT}"
  [[ -d "${PREV_TREE}" ]] || die "no retained release tree at ${PREV_TREE}; cannot rollback"
  rsync -a --delete --delete-delay --delay-updates \
    --exclude '.env.prod' --exclude '.env.dev' --exclude '.deploy-env' \
    --exclude '.deploy-state' --exclude '.backups' \
    --exclude '.venv' --exclude 'node_modules' --exclude '.next' \
    --exclude 'dist' --exclude '.site' --exclude '__pycache__' \
    "${PREV_TREE}/" "${AI_STP_ROOT}/"
  chmod u+x \
    "${AI_STP_ROOT}/deploy/pull-deploy.sh" \
    "${AI_STP_ROOT}/deploy/run.sh" \
    "${AI_STP_ROOT}/deploy/verify.sh" \
    "${AI_STP_ROOT}/deploy/deploy.sh" \
    "${AI_STP_ROOT}/deploy/lib.sh" \
    "${AI_STP_ROOT}/deploy/load-apparmor.sh" \
    "${AI_STP_ROOT}/deploy/mark-transfer.sh"
fi
# The pull-model root cannot derive the commit from bytes on disk; the
# explicit value is what the artifact record and the API version endpoint
# report (lib.sh current_git_commit).
export AI_STP_DEPLOY_COMMIT="${PREV_COMMIT}"
export AI_STP_API_GIT_COMMIT="${PREV_COMMIT}"

compose config >/dev/null
compose build
# Forward-only migrate: no downgrade. If the previous app is incompatible with
# the current schema, readiness will fail and we abort.
compose up -d postgres rustfs
compose run --rm migrate
# Same semantics as deploy.sh: a failed integrity reconcile stops the rollback
# rather than silently skipping it — the forward path treats it as fatal.
compose run --rm seed
compose rm -fs content-import >/dev/null 2>&1 || true
compose up -d api worker content-import web docs

wait_for_liveness
wait_for_readiness

write_artifact_record "${AI_STP_STATE_DIR}/current"
log info "rollback_complete"
