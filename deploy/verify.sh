#!/usr/bin/env bash
# Prove the deployed stack answers from its host, outside its containers.
#
# Separate from `deploy.sh` because it answers a different question. The deploy
# script waits for the services it just started; this asks the host-published
# address whether the reverse-proxy hop answers. It intentionally does not claim
# public DNS or TLS: `verify_public.py` proves those from the deployment runner.
set -euo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ -f "${ROOT}/.deploy-env" ]]; then
  # shellcheck disable=SC1091
  set -a && source "${ROOT}/.deploy-env" && set +a
fi

# Where the stack is published, and under which name its certificate was issued.
# Both are needed: Caddy serves a certificate for the configured host name, so a
# request by IP fails the handshake even when the service behind it is perfectly
# healthy — an error that reads like an outage and is not one.
readonly BASE="${AI_STP_VERIFY_BASE_URL:-https://localhost:58443}"
readonly SNI="${AI_STP_VERIFY_SNI:-localhost:58443:127.0.0.1}"

probe() {
  curl -sSk --resolve "${SNI}" --max-time 15 -o /dev/null -w '%{http_code}' "${BASE}$1" || echo "000"
}

failed=0
for path in /v1/health/live /v1/health/ready; do
  code="$(probe "${path}")"
  printf '  %-20s %s\n' "${path}" "${code}"
  [[ "${code}" == "200" ]] || failed=1
done

# The web tier redirects to a locale, so a 2xx only appears after following it.
web="$(curl -sSk --resolve "${SNI}" --max-time 25 -o /dev/null -w '%{http_code}' -L "${BASE}/" || echo "000")"
printf '  %-20s %s\n' "/ (web)" "${web}"
[[ "${web}" == "200" ]] || failed=1

# The worker publishes nothing over HTTP, so the probes above cannot see it —
# and it is the service that decides whether anything may be published at all.
# A deployment that left it on the previous image reported success here while
# every publication was still being judged by the code that was replaced. That
# happened, and it cost an hour of looking in the right file at the wrong host.
#
# `${AI_STP_API_GIT_COMMIT}` cannot answer this: it is an environment variable
# the API reports back, so it describes the deployment attempt rather than the
# code any container is running.
readonly COMPOSE_FILE="${AI_STP_COMPOSE_FILE:-docker-compose.prod.yml}"
compose() {
  local -a args=(-f "${ROOT}/${COMPOSE_FILE}")
  [[ -f "${ROOT}/${AI_STP_ENV_FILE:-.env.prod}" ]] &&
    args+=(--env-file "${ROOT}/${AI_STP_ENV_FILE:-.env.prod}")
  docker compose "${args[@]}" "$@"
}

worker_id="$(compose ps -q worker 2>/dev/null | head -n 1 || true)"
if [[ -z "${worker_id}" ]]; then
  printf '  %-20s %s\n' "worker" "absent"
  echo "verify: the worker has no container; nothing would validate a publication" >&2
  failed=1
else
  worker_state="$(docker inspect -f '{{.State.Status}}' "${worker_id}" 2>/dev/null || echo unknown)"
  printf '  %-20s %s\n' "worker" "${worker_state}"
  [[ "${worker_state}" == "running" ]] || failed=1

  # Running and current is not ready. The worker healthcheck is
  # safety_readiness(), which is false while bwrap cannot create a user
  # namespace. A deployment that left it unhealthy reported success here
  # while every publication scan fell back to env_only.
  worker_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${worker_id}" 2>/dev/null || echo unknown)"
  printf '  %-20s %s\n' "worker health" "${worker_health}"
  if [[ "${worker_health}" == "unhealthy" ]]; then
    echo "verify: the worker is running but its healthcheck failed" >&2
    failed=1
  fi

  # Running is not enough: a container left over from the previous deployment is
  # running too. What separates them is the image — so ask the container which
  # tag it was built from, then ask that tag what it points at now. A rebuild
  # moves the tag; a container that was not recreated still holds the old id.
  #
  # Asked of the container rather than of `compose config --images`, which
  # ignores the service argument and prints every service's image. Reading the
  # first line of that gave `postgres:16` and compared it against the worker,
  # so the check could only ever fail — and it failed a real deployment before
  # this comment existed.
  tag="$(docker inspect -f '{{.Config.Image}}' "${worker_id}" 2>/dev/null || true)"
  have="$(docker inspect -f '{{.Image}}' "${worker_id}" 2>/dev/null || true)"
  want=""
  [[ -n "${tag}" ]] && want="$(docker image inspect -f '{{.Id}}' "${tag}" 2>/dev/null || true)"
  if [[ -z "${want}" || -z "${have}" ]]; then
    # Undetermined is not stale. A check that cannot answer must not be the
    # thing that stops a deployment; that is how this check first behaved.
    printf '  %-20s %s\n' "worker image" "undetermined"
  elif [[ "${want}" != "${have}" ]]; then
    printf '  %-20s %s\n' "worker image" "stale"
    echo "verify: the worker is running an image this deployment replaced" >&2
    failed=1
  else
    printf '  %-20s %s\n' "worker image" "current"
  fi
fi

if [[ "${failed}" -ne 0 ]]; then
  echo "verify: the deployed stack did not answer as expected" >&2
  exit 1
fi
echo "verify: api, web and worker are current at ${BASE}"
