#!/usr/bin/env bash
# Install the host route split from the templates this repository owns.
#
# The stack no longer ships a proxy container (ADR-0135), so the routing contract
# lives here as a template and the deployment host's nginx executes it. This
# script is deliberately separate from `deploy.sh`: the pull-deploy unit runs
# unprivileged with NoNewPrivileges and ProtectSystem=strict and cannot write
# /etc/nginx, so applying a routing change is an operator step, run with sudo.
#
# One site per run, and the rendered file is named after its first host name, so
# a host serving several sites installs several files and retiring one is
# deleting its file. A single site may answer to several names — give them
# space-separated, as nginx's own `server_name` takes them.
#
# The certificate lineage is a separate input from the host name because certbot
# names a directory after the first request for a name, not after the name: a
# reissue lands in `example.com-0001` while the site is still `example.com`.
set -euo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly ENV_FILE="${AI_STP_ENV_FILE:-${ROOT}/.env.prod}"
readonly TARGET="${AI_STP_NGINX_CONF_DIR:-/etc/nginx/conf.d}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a && source "${ENV_FILE}" && set +a
fi

# Host names carry no scheme here: they name a server, not an origin.
# Both are optional: a host may serve only the site, only the documentation, or
# neither during a local rehearsal, and `set -u` must not turn that into a crash.
readonly MAIN_HOST="${AI_STP_PUBLIC_HOST-}"
readonly DOCS_HOST="${AI_STP_DOCS_HOST-}"
# The first name identifies the site: it names the file and, unless overridden,
# the certificate lineage. The rest are aliases nginx answers to.
primary() { local first="${1%%[ ]*}"; printf '%s' "${first#*://}"; }
readonly MAIN_PRIMARY="$(primary "${MAIN_HOST}")"
readonly DOCS_PRIMARY="$(primary "${DOCS_HOST}")"
readonly API_BIND="${AI_STP_API_BIND:-127.0.0.1:58082}"
readonly WEB_BIND="${AI_STP_WEB_BIND:-127.0.0.1:58081}"
readonly DOCS_BIND="${AI_STP_DOCS_BIND:-127.0.0.1:58083}"

render() {
  local template="$1" raw="$2" lineage="$3" out="$4"
  if [[ -z "${raw}" ]]; then
    echo "skip ${template}: no host name configured"
    return 0
  fi
  # An older .env.prod may still carry `http://` from when the proxy asked a CA
  # for certificates; a server_name never takes one.
  local names="" name
  for name in ${raw}; do names+="${name#*://} "; done
  names="${names% }"
  local host
  host="$(primary "${names}")"
  if [[ ! -s "/etc/letsencrypt/live/${lineage}/fullchain.pem" ]]; then
    echo "skip ${host}: no certificate under lineage '${lineage}'; run certbot first" >&2
    return 1
  fi
  sed -e "s|@@MAIN_HOST@@|${names}|g" \
      -e "s|@@DOCS_HOST@@|${names}|g" \
      -e "s|@@LINEAGE@@|${lineage}|g" \
      -e "s|@@API_BIND@@|${API_BIND}|g" \
      -e "s|@@WEB_BIND@@|${WEB_BIND}|g" \
      -e "s|@@DOCS_BIND@@|${DOCS_BIND}|g" \
      "${ROOT}/deploy/nginx/${template}" > "${TARGET}/${out}"
  echo "rendered ${TARGET}/${out} for ${names} (lineage ${lineage})"
}

# One site missing its certificate must not strand the other half-installed, so
# the failure is remembered rather than raised. A rendered file changes nothing
# until the reload, and the reload only happens if the whole config still tests.
missing=0
render ai-stp.conf.template "${MAIN_HOST}" \
  "${AI_STP_TLS_LINEAGE:-${MAIN_PRIMARY}}" "zz-ai-stp-${MAIN_PRIMARY}.conf" || missing=1
render ai-stp-docs.conf.template "${DOCS_HOST}" \
  "${AI_STP_DOCS_TLS_LINEAGE:-${DOCS_PRIMARY}}" "zz-ai-stp-docs-${DOCS_PRIMARY}.conf" || missing=1

nginx -t
nginx -s reload
echo "nginx reloaded"
exit "${missing}"
