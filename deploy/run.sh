#!/usr/bin/env bash
# Host-side entry point for an automated deployment.
#
# `deploy.sh` is deliberately generic: it takes its compose file, env file and
# probe addresses from the environment. Where those point is a fact about one
# machine, not about this repository, so it lives beside the deployment in
# `.deploy-env` — untracked, like `.env.prod` — and this wrapper is the one
# place that joins the two.
#
# Without it every caller (a person, the workflow, a rollback rehearsal) would
# have to remember the same five exports, and the one that forgot would probe
# the wrong port and call a healthy stack broken.
set -euo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ -f "${ROOT}/.deploy-env" ]]; then
  # shellcheck disable=SC1091
  set -a && source "${ROOT}/.deploy-env" && set +a
fi

export AI_STP_COMPOSE_FILE="${AI_STP_COMPOSE_FILE:-docker-compose.prod.yml}"
export AI_STP_ENV_FILE="${AI_STP_ENV_FILE:-.env.prod}"

if [[ ! -f "${ROOT}/${AI_STP_ENV_FILE}" ]]; then
  echo "deploy/run.sh: ${AI_STP_ENV_FILE} is absent on this host." >&2
  echo "It holds the real secrets and is never transferred; create it from" >&2
  echo ".env.prod.example before the first deployment." >&2
  exit 1
fi

exec "${ROOT}/deploy/deploy.sh"
