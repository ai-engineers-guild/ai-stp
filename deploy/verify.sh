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

if [[ "${failed}" -ne 0 ]]; then
  echo "verify: the deployed stack did not answer as expected" >&2
  exit 1
fi
echo "verify: api and web answer at ${BASE}"
