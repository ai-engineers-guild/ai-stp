#!/usr/bin/env bash
# Shared helpers for deploy/backup/rollback (SPEC-024, ADR-0044).
# Logs never print secrets, env values, tokens, cookies or object bytes.

set -euo pipefail

# Resolve repo root from this file's location when sourced from deploy/*.sh.
_DEPLOY_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_STP_ROOT="${AI_STP_ROOT:-$(cd "${_DEPLOY_LIB_DIR}/.." && pwd)}"
AI_STP_COMPOSE_FILE="${AI_STP_COMPOSE_FILE:-docker-compose.prod.yml}"
AI_STP_ENV_FILE="${AI_STP_ENV_FILE:-.env.prod}"
AI_STP_STATE_DIR="${AI_STP_STATE_DIR:-${AI_STP_ROOT}/.deploy-state}"
AI_STP_BACKUP_DIR="${AI_STP_BACKUP_DIR:-${AI_STP_ROOT}/.backups}"
AI_STP_BACKUP_RETENTION="${AI_STP_BACKUP_RETENTION:-7}"
AI_STP_DEPLOY_LOCK="${AI_STP_DEPLOY_LOCK:-${AI_STP_STATE_DIR}/deploy.lock}"
AI_STP_READINESS_URL="${AI_STP_READINESS_URL:-http://127.0.0.1/v1/health/ready}"
AI_STP_LIVENESS_URL="${AI_STP_LIVENESS_URL:-http://127.0.0.1/v1/health/live}"
AI_STP_READY_TIMEOUT_SECONDS="${AI_STP_READY_TIMEOUT_SECONDS:-180}"

log() {
  # Structured-ish log line: level + message only. Never pass secrets as args.
  printf '%s level=%s msg=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" >&2
}

die() {
  log error "$1"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command missing: $1"
}

compose() {
  # Compose invocation with the configured file. Env file is optional.
  local -a args=(-f "${AI_STP_ROOT}/${AI_STP_COMPOSE_FILE}")
  if [[ -f "${AI_STP_ROOT}/${AI_STP_ENV_FILE}" ]]; then
    args+=(--env-file "${AI_STP_ROOT}/${AI_STP_ENV_FILE}")
  fi
  docker compose "${args[@]}" "$@"
}

ensure_state_dir() {
  mkdir -p "${AI_STP_STATE_DIR}" "${AI_STP_BACKUP_DIR}"
}

current_git_commit() {
  # The explicit value wins, and under the pull model it is the only one there
  # is: `pull-deploy.sh` unpacks the release with `git archive`, so the
  # deployment root carries no `.git` and `rev-parse` can only answer
  # "unknown". That answer was then written into `.deploy-state/current` and
  # read back on the next tick as a commit to resolve, which wedged deployment
  # permanently (`fatal: Not a valid object name unknown^{commit}`).
  #
  # The `rev-parse` fallback stays for the manual path, where an operator does
  # rsync a checkout and the root is a repository.
  if [[ -n ${AI_STP_DEPLOY_COMMIT:-} ]]; then
    echo "${AI_STP_DEPLOY_COMMIT}"
    return 0
  fi
  git -C "${AI_STP_ROOT}" rev-parse HEAD 2>/dev/null || echo "unknown"
}

write_artifact_record() {
  # Record deploy identity for rollback. No secrets.
  local path="$1"
  local commit temporary
  commit="$(current_git_commit)"
  # `unknown` is not a commit. Written here it became a baseline that the next
  # run read back and asked Git to resolve, which failed fatally and left a
  # record that could never be replaced. An unresolvable identity is recorded as
  # an empty value instead, which every reader of this file already understands
  # as "no baseline" -- including `rollback.sh`, which would otherwise try to
  # roll back to a commit named `unknown`.
  if [[ ${commit} == "unknown" ]]; then
    commit=""
  fi
  umask 077
  temporary="$(mktemp "${AI_STP_STATE_DIR}/artifact.XXXXXX")"
  {
    echo "git_commit=${commit}"
    echo "recorded_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "compose_file=${AI_STP_COMPOSE_FILE}"
  } >"${temporary}"
  mv -f "${temporary}" "${path}"
}

record_deploy_stage() {
  # The next run restarts the idempotent forward path after an interruption.
  local commit="$1"
  local stage="$2"
  local path="${AI_STP_STATE_DIR}/in-progress"
  local temporary
  umask 077
  temporary="$(mktemp "${AI_STP_STATE_DIR}/in-progress.XXXXXX")"
  {
    echo "git_commit=${commit}"
    echo "stage=${stage}"
    echo "recorded_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >"${temporary}"
  mv -f "${temporary}" "${path}"
}

state_field() {
  local path="$1"
  local name="$2"
  sed -n "s/^${name}=//p" "${path}" | head -n1
}

acquire_deploy_lock() {
  ensure_state_dir
  exec 200>"${AI_STP_DEPLOY_LOCK}"
  if ! flock -n 200; then
    die "deploy lock held; another deploy is in progress"
  fi
  log info "deploy_lock_acquired"
}

release_deploy_lock() {
  # flock releases on FD close; explicit message for operators.
  log info "deploy_lock_released"
}

wait_for_readiness() {
  # Abort criteria: readiness must become true within the timeout.
  local deadline=$((SECONDS + AI_STP_READY_TIMEOUT_SECONDS))
  local code
  require_cmd curl
  log info "waiting_for_readiness"
  while ((SECONDS < deadline)); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "${AI_STP_READINESS_URL}" || true)"
    if [[ "${code}" == "200" ]]; then
      log info "readiness_ok"
      return 0
    fi
    sleep 3
  done
  die "readiness_timeout: aborting; traffic must not shift to unhealthy artifact"
}

wait_for_liveness() {
  local deadline=$((SECONDS + 60))
  local code
  require_cmd curl
  while ((SECONDS < deadline)); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "${AI_STP_LIVENESS_URL}" || true)"
    if [[ "${code}" == "200" ]]; then
      return 0
    fi
    sleep 2
  done
  die "liveness_timeout"
}
