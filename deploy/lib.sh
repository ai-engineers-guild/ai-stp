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
# The API's own published port, not port 80. The host proxy routes by name
# (ADR-0135), so a request to the bare loopback address carries a Host header no
# site matches and lands wherever the default server points — which is a fact
# about the host's other tenants, not about this deployment being ready.
AI_STP_READINESS_URL="${AI_STP_READINESS_URL:-http://127.0.0.1:58082/v1/health/ready}"
AI_STP_LIVENESS_URL="${AI_STP_LIVENESS_URL:-http://127.0.0.1:58082/v1/health/live}"
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

env_file_value() {
  # Print the value of one key from the deploy environment file (first
  # definition wins, as for a sourced file). Never logs; callers compare or
  # measure, they do not echo. An absent key prints nothing and does not
  # fail: under `pipefail` grep's no-match would otherwise kill the caller
  # silently, which is exactly how an optional credential check must not die.
  local name="$1"
  local path="${AI_STP_ROOT}/${AI_STP_ENV_FILE}"
  LC_ALL=C grep -E "^${name}=" "${path}" 2>/dev/null | head -n1 | cut -d= -f2- || true
}

require_env_value() {
  # Check presence without sourcing or printing the environment file. A deploy
  # secret may contain shell metacharacters and is data, never executable
  # configuration. Refuse before any service is recreated so a missing
  # precondition leaves the currently healthy release serving traffic.
  #
  # A `*CHANGE_ME*` value is also refused here: the example file is the only
  # origin of that stem, and a verbatim copy is the failure mode this guard
  # exists for — `POSTGRES_PASSWORD=CHANGE_ME` and `AI_STP_DB_URL` with the
  # same embedded password agree with each other and deploy "green" on
  # published credentials.
  local name="$1"
  local path="${AI_STP_ROOT}/${AI_STP_ENV_FILE}"
  local value
  [[ -f "${path}" ]] || die "required deploy environment file missing: ${AI_STP_ENV_FILE}"
  LC_ALL=C grep -Eq "^${name}=.+$" "${path}" || die "required deploy environment value missing: ${name}"
  value="$(env_file_value "${name}")"
  case "${value}" in
    *CHANGE_ME*) die "deploy value still holds the example placeholder: ${name}" ;;
  esac
}

refuse_env_placeholder() {
  # Optional values are skipped when empty, but a copied `CHANGE_ME` is worse
  # than empty: `AI_STP_WORKER_GITHUB_TOKEN=CHANGE_ME` does not mean
  # "unauthenticated", it means an invalid token sent to api.github.com.
  local name="$1"
  local value
  value="$(env_file_value "${name}")"
  case "${value}" in
    *CHANGE_ME*) die "optional deploy value still holds the example placeholder: ${name}" ;;
  esac
}

require_env_secret() {
  # Presence alone is not enough for the values pydantic/zod gate at boot:
  # `min_length=32` fields refuse to start the app, and the example file's
  # `CHANGE_ME*` stem is worse than missing — a verbatim copy ships a secret
  # every reader of the public repository can mint. The value is compared,
  # never printed.
  local name="$1"
  local value
  require_env_value "${name}"
  value="$(env_file_value "${name}")"
  case "${value}" in
    CHANGE_ME*) die "deploy secret still holds the example placeholder: ${name}" ;;
  esac
  [[ ${#value} -ge 32 ]] || die "deploy secret shorter than 32 characters: ${name}"
}

require_env_public_origin() {
  # A browser-facing URL ships in responses and build artifacts, so the
  # example's `*.example.invalid` hosts and the settings' `localhost`
  # defaults are deployment defects, not working configuration. Refuse them
  # the same way a missing value is refused: before any effect.
  local name="$1"
  local value
  require_env_value "${name}"
  value="$(env_file_value "${name}")"
  case "${value}" in
    *example.invalid* | *localhost* | *127.0.0.1*)
      die "deploy public origin still holds a placeholder or loopback host: ${name}"
      ;;
  esac
}

require_env_pair_equal() {
  # The API authenticates to the internal object store with the storage pair,
  # and the store expects its own pair; when the two differ the deployment
  # passes every probe and then fails on the first object write. Compare the
  # values, never print them.
  local left="$1"
  local right="$2"
  require_env_value "${left}"
  require_env_value "${right}"
  [[ "$(env_file_value "${left}")" == "$(env_file_value "${right}")" ]] ||
    die "deploy values must match but differ: ${left} vs ${right}"
}

require_deploy_env() {
  # The whole startup contract of the serving stack, checked by name — never
  # sourced, never printed. `deploy.sh` runs this before recording progress,
  # building, migrating or recreating anything, so a missing or placeholder
  # secret leaves the currently healthy release serving traffic. The same
  # function backs `just infra-env-check`, the operator's rehearsal.
  local required_name required_secret required_origin optional_value
  for required_name in \
    AI_STP_API_ENVIRONMENT \
    POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB \
    AI_STP_DB_URL \
    AI_STP_STORAGE_ENDPOINT AI_STP_STORAGE_ACCESS_KEY_ID AI_STP_STORAGE_SECRET_ACCESS_KEY \
    AI_STP_STORAGE_ARTIFACT_BUCKET AI_STP_STORAGE_ASSET_BUCKET \
    RUSTFS_ACCESS_KEY RUSTFS_SECRET_KEY \
    AI_STP_CONTENT_IMPORT_TOKEN; do
    require_env_value "${required_name}"
  done
  # The pydantic and zod `min_length=32` fields: auth key, cursor secret,
  # session secret. `AI_STP_API_ENVIRONMENT` is required above because its
  # absence defaults to `dev` — the one value that lets fixture seeding into
  # a serving stack. The importer token is required because web waits on the
  # one-shot, and without it Compose leaves web stopped behind the failed
  # dependency.
  for required_secret in \
    AI_STP_AUTH_SECRET_KEY \
    AI_STP_CATALOG_CURSOR_SIGNING_SECRET \
    AI_STP_SESSION_SECRET; do
    require_env_secret "${required_secret}"
  done
  # Browser-facing origins. The compose defaults (`*.example.invalid`) and the
  # settings default (`localhost`) would ship on the public site — a green
  # deploy with a broken canonical URL and dead OAuth redirects.
  for required_origin in \
    NEXT_PUBLIC_APP_URL \
    AI_STP_USER_DOCS_URL \
    AI_STP_AUTH_PUBLIC_BASE_URL; do
    require_env_public_origin "${required_origin}"
  done
  # The API and the internal object store must authenticate with the same pair.
  require_env_pair_equal AI_STP_STORAGE_ACCESS_KEY_ID RUSTFS_ACCESS_KEY
  require_env_pair_equal AI_STP_STORAGE_SECRET_ACCESS_KEY RUSTFS_SECRET_KEY
  # Optional credentials are allowed to stay empty — an absent GitHub token is
  # a rate limit, not a failure — but a leftover placeholder is a bad
  # credential, which fails where empty would have worked.
  for optional_value in \
    AI_STP_WORKER_GITHUB_TOKEN \
    AI_STP_AUTH_GOOGLE_CLIENT_SECRET \
    AI_STP_AUTH_GITHUB_CLIENT_SECRET \
    AI_STP_GITHUB_CONNECTOR_CLIENT_SECRET \
    AI_STP_GITHUB_CONNECTOR_ENCRYPTION_KEY \
    AI_STP_CORPORATE_BOOTSTRAP_SECRET \
    AI_STP_SEO_ENRICHMENT_CREDENTIAL \
    AI_STP_CLIPROXY_API_KEY; do
    refuse_env_placeholder "${optional_value}"
  done
}

compose() {
  # Compose invocation with the configured file. Env file is optional.
  local -a args=(-f "${AI_STP_ROOT}/${AI_STP_COMPOSE_FILE}")
  if [[ -f "${AI_STP_ROOT}/${AI_STP_ENV_FILE}" ]]; then
    args+=(--env-file "${AI_STP_ROOT}/${AI_STP_ENV_FILE}")
  fi
  docker compose "${args[@]}" "$@"
}

compose_service_volume() {
  local service="$1"
  local destination="$2"
  local container volume
  container="$(compose ps -q --all "${service}" | head -n1)"
  [[ -n "${container}" ]] || die "${service}_container_not_found"
  volume="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "'"${destination}"'"}}{{.Name}}{{end}}{{end}}' "${container}")"
  [[ -n "${volume}" ]] || die "${service}_volume_not_found"
  printf '%s\n' "${volume}"
}

oauth_identity_fingerprint() {
  compose exec -T postgres sh -c \
    'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -AtF "|" -c "SELECT provider, provider_subject, account_id, state FROM oauth_identity ORDER BY provider, provider_subject"' \
    | tr -d '\r' | sha256sum | awk '{print $1}'
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
  #
  # Running `deploy.sh` by hand on a pull-model host reached neither: no
  # explicit value, no repository, so "unknown" was handed to the content
  # snapshot, which refused it as not a 40-hex SHA and failed the build. The
  # last recorded deploy answers that, and it is safe to read despite the
  # deadlock above -- `write_artifact_record` refuses to write "unknown" into
  # it, so this file holds a real commit or nothing at all.
  local recorded
  if [[ -n ${AI_STP_DEPLOY_COMMIT:-} ]]; then
    echo "${AI_STP_DEPLOY_COMMIT}"
    return 0
  fi
  if recorded="$(git -C "${AI_STP_ROOT}" rev-parse HEAD 2>/dev/null)"; then
    echo "${recorded}"
    return 0
  fi
  recorded="$(sed -n 's/^git_commit=//p' "${AI_STP_STATE_DIR}/current" 2>/dev/null | head -n 1)"
  echo "${recorded:-unknown}"
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
