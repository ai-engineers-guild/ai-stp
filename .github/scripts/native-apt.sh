#!/usr/bin/env bash
# Project-owned package source for disposable GitHub native qualification.
set -euo pipefail

if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_OS:-}" != Linux ||
  "${RUNNER_ARCH:-}" != X64 ]]; then
  echo 'native-apt requires the declared disposable GitHub Linux runner' >&2
  exit 64
fi
# shellcheck source=/dev/null
source /etc/os-release
if [[ "${ID:-}" != ubuntu || "${VERSION_ID:-}" != 26.04 ||
  "${VERSION_CODENAME:-}" != resolute ]]; then
  echo 'native-apt requires the declared Ubuntu 26.04 distribution' >&2
  exit 64
fi
case "${1:-}" in
  update) options=(--error-on=any) ;;
  install) options=() ;;
  *) exit 64 ;;
esac

# OSU is a registered Ubuntu archive mirror. APT retains Ubuntu's signing key
# and package hashes; no runner sources, resolver or trust settings are changed.
temporary=$(mktemp -d "${RUNNER_TEMP:?}/ai-stp-ubuntu-source.XXXXXX")
cleanup() {
  rm -- "${temporary}/ubuntu.sources"
  rmdir -- "${temporary}"
}
trap cleanup EXIT
chmod 755 "${temporary}"
cat > "${temporary}/ubuntu.sources" <<'SOURCES'
Types: deb
URIs: https://ubuntu.osuosl.org/ubuntu
Suites: resolute resolute-updates resolute-backports resolute-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
SOURCES
sudo apt-get \
  -o "Dir::Etc::sourcelist=${temporary}/ubuntu.sources" \
  -o Dir::Etc::sourceparts=- \
  "${options[@]}" "$@"
