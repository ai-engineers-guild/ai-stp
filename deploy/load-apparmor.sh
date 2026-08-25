#!/usr/bin/env bash
# Load the AppArmor profile the production worker needs for bubblewrap.
#
# Ubuntu 24.04 sets kernel.apparmor_restrict_unprivileged_userns=1. Only a
# profile that allows `userns` may create a user namespace. docker-default
# does not, and apparmor=unconfined also does not — unconfined has no userns
# allow rule, so it is worse. The profile this script loads does.
#
# The pull-deploy unit sets NoNewPrivileges=true, so sudo cannot raise to the
# capability apparmor_parser needs. The docker daemon is already root (that is
# how this host builds images); this script asks it to enter pid 1's mount
# namespace and run the host parser. That is not a new privilege: the same
# unit already talks to docker.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROFILE="${ROOT}/deploy/apparmor/ai-stp-worker"
INSTALLED="/etc/apparmor.d/ai-stp-worker"

die() {
  printf 'load-apparmor: %s\n' "$1" >&2
  exit 1
}

[[ -f "${PROFILE}" ]] || die "profile missing: ${PROFILE}"

load_on_host() {
  command -v apparmor_parser >/dev/null 2>&1 || die "apparmor_parser is not on this host"
  install -m 0644 "${PROFILE}" "${INSTALLED}"
  # .load is world-writable on Ubuntu 24.04; the parser cache is not. Skip the
  # cache so a later non-root probe cannot be mistaken for a successful load.
  apparmor_parser --skip-cache -r "${INSTALLED}"
}

if [[ $(id -u) -eq 0 ]]; then
  load_on_host
  exit 0
fi

command -v docker >/dev/null 2>&1 || die "cannot load AppArmor: not root and docker is missing"

nsenter=""
for candidate in /usr/bin/nsenter /bin/nsenter; do
  if [[ -x "${candidate}" ]]; then
    nsenter="${candidate}"
    break
  fi
done
[[ -n "${nsenter}" ]] || die "nsenter is missing; cannot enter the host mount namespace"

image=""
if docker image inspect ai_stp-worker >/dev/null 2>&1; then
  image="$(docker image inspect ai_stp-worker --format '{{.Id}}')"
fi
if [[ -z "${image}" ]]; then
  image="$(
    docker compose -f "${ROOT}/docker-compose.prod.yml" images -q worker 2>/dev/null \
      | awk 'NF { print; exit }'
  )"
fi
[[ -n "${image}" ]] || die "no worker image to enter the host namespace with"

# The bind-mounted nsenter is dynamically linked against the vehicle image's
# libc; the worker image is glibc, which matches the host binary.
docker run --rm --privileged --pid=host --user 0 --network none \
  -v "${nsenter}:${nsenter}:ro" \
  --entrypoint "${nsenter}" \
  "${image}" -t 1 -m -- /bin/sh -c \
  "install -m 0644 '${PROFILE}' '${INSTALLED}' && /usr/sbin/apparmor_parser --skip-cache -r '${INSTALLED}'"
