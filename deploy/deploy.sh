#!/usr/bin/env bash
# Serialized, idempotent deploy from the current git checkout
# (SPEC-024 REQ-2410/2412, ADR-0044).
#
# Abort criteria: if readiness fails within the timeout, exit non-zero and do
# not treat the new artifact as healthy. Rollback is a separate script that
# redeploys the previous recorded commit artifact without schema down-migration.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

usage() {
  cat <<'EOF'
Usage: deploy/deploy.sh [--compose-file FILE] [--skip-build]

Deploy steps (order):
  1. Acquire deploy lock (flock)
  2. Record previous artifact for rollback
  3. Build images (unless --skip-build)
  4. migrate -> seed -> api/worker + content-import -> web/caddy up
  5. Wait for readiness; abort on timeout
  6. Record current artifact

Environment:
  AI_STP_COMPOSE_FILE   default docker-compose.prod.yml
  AI_STP_ENV_FILE       default .env.prod
  AI_STP_API_GIT_COMMIT injected into api for safe diagnostics
EOF
}

SKIP_BUILD=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --compose-file)
      AI_STP_COMPOSE_FILE="$2"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD=1
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

require_cmd docker
require_cmd git
require_cmd flock
ensure_state_dir
acquire_deploy_lock
trap release_deploy_lock EXIT

COMMIT="$(current_git_commit)"
export AI_STP_API_GIT_COMMIT="${AI_STP_API_GIT_COMMIT:-${COMMIT}}"

# Web waits for the repository content import to complete. Without its shared
# token the one-shot refuses, and Compose then leaves web stopped behind the
# failed dependency. Check the precondition before build, migration or any
# container recreation so a missing secret cannot take the current site down.
require_env_value "AI_STP_CONTENT_IMPORT_TOKEN"

# An interrupted run leaves this marker. Every stage below is idempotent, so
# recovery deterministically restarts the forward path instead of guessing
# which remote process survived a cancelled SSH session.
if [[ -f "${AI_STP_STATE_DIR}/in-progress" ]]; then
  RECOVERY_COMMIT="$(state_field "${AI_STP_STATE_DIR}/in-progress" git_commit)"
  RECOVERY_STAGE="$(state_field "${AI_STP_STATE_DIR}/in-progress" stage)"
  log warning "recovering_interrupted_deploy commit=${RECOVERY_COMMIT} stage=${RECOVERY_STAGE}"
fi
record_deploy_stage "${COMMIT}" "started"

log info "deploy_start"
log info "git_commit=${COMMIT}"

# Config validation before mutating the stack.
compose config >/dev/null
log info "compose_config_ok"
record_deploy_stage "${COMMIT}" "config_validated"

if [[ "${SKIP_BUILD}" -eq 0 ]]; then
  compose build
  log info "images_built"
fi
record_deploy_stage "${COMMIT}" "images_ready"

# Worker compose names apparmor=ai-stp-worker. Load it before that container
# starts: Docker looks the profile up in the kernel, not in the image.
if grep -q 'apparmor=ai-stp-worker' "${AI_STP_ROOT}/${AI_STP_COMPOSE_FILE}"; then
  "${SCRIPT_DIR}/load-apparmor.sh"
  log info "worker_apparmor_loaded"
fi

# Ordered bring-up: dependencies, migrate, seed, then serving processes.
compose up -d postgres rustfs
record_deploy_stage "${COMMIT}" "dependencies_started"
# Wait for postgres health via compose depends_on on one-shot jobs.
compose run --rm migrate
log info "migrate_ok"
record_deploy_stage "${COMMIT}" "migrated"
compose run --rm seed
log info "seed_ok"
record_deploy_stage "${COMMIT}" "seeded"
# One-shot importer: an exited container from the previous release is not
# current. Remove it so `up` POSTs this image's snapshot (same digest is no-op).
compose rm -fs content-import >/dev/null 2>&1 || true
compose up -d api worker content-import web caddy
# rsync deploys replace bind-mounted files by new inodes. The official
# caddy:2 image does not follow that; a long-lived container keeps serving
# the Caddyfile it opened at start, and `caddy reload` reloads that inode.
compose up -d --force-recreate --no-deps caddy
log info "services_started"
record_deploy_stage "${COMMIT}" "services_started"

wait_for_liveness
record_deploy_stage "${COMMIT}" "liveness_passed"
wait_for_readiness
record_deploy_stage "${COMMIT}" "readiness_passed"

# Rotate rollback identity only after the new deployment has proved ready.
if [[ -f "${AI_STP_STATE_DIR}/current" ]]; then
  cp -f "${AI_STP_STATE_DIR}/current" "${AI_STP_STATE_DIR}/previous"
  log info "previous_artifact_recorded"
fi
write_artifact_record "${AI_STP_STATE_DIR}/current"
rm -f "${AI_STP_STATE_DIR}/in-progress"
log info "deploy_complete"
