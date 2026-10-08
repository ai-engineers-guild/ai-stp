#!/usr/bin/env bash
# Scan the repository lockfile for known vulnerabilities with the pinned
# osv-scanner.
#
# The binary is fetched into a temp directory on every run and verified
# against the release's own SHA256SUMS. The gate must not depend on a
# scanner already living on the host, nor on the version that happens to
# be there -- the pin in `versions.env` is the same one the worker-safety
# image installs, so CI and production weigh the same dependency set with
# the same scanner build.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/versions.env"

ARCH="$(uname -m)"
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"

case "${OS}-${ARCH}" in
  linux-x86_64|linux-amd64) asset="osv-scanner_linux_amd64" ;;
  linux-aarch64|linux-arm64) asset="osv-scanner_linux_arm64" ;;
  darwin-arm64) asset="osv-scanner_darwin_arm64" ;;
  darwin-x86_64|darwin-amd64) asset="osv-scanner_darwin_amd64" ;;
  *)
    echo "scan_lockfile: unsupported ${OS}-${ARCH}" >&2
    exit 1
    ;;
esac

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

curl -fsSL --retry 3 --retry-delay 2 \
  -o "${tmp}/osv-scanner" \
  "https://github.com/google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/${asset}"
curl -fsSL --retry 3 --retry-delay 2 \
  -o "${tmp}/SHA256SUMS" \
  "https://github.com/google/osv-scanner/releases/download/v${OSV_SCANNER_VERSION}/osv-scanner_SHA256SUMS"
expected="$(awk -v asset="${asset}" '$2 == asset || $2 == "*" asset {print $1; exit}' "${tmp}/SHA256SUMS")"
[[ -n "${expected}" ]] || {
  echo "scan_lockfile: checksum missing for ${asset}" >&2
  exit 1
}
printf '%s  %s\n' "${expected}" "${tmp}/osv-scanner" | sha256sum -c - >/dev/null
chmod +x "${tmp}/osv-scanner"

cd "${REPO_ROOT}"
scanner="${tmp}/osv-scanner"
# Every committed lockfile is weighed: Python, the web app, docs tooling,
# the desktop app and both of its Rust crates, the native CLI, the vendored
# provider-verifier env, and the worker-safety venv. Every scan runs even
# when one trips -- set -e would otherwise hide every later file behind
# the first advisory, which is how GHSA-42vr-xj54-vc7v appeared only after
# the urllib3 bump merged. `requirements.lock` needs the
# `requirements.txt:` name override; `verifier-requirements.txt` parses
# natively because the name still contains `requirements`.
status=0
for lockfile in \
  uv.lock \
  apps/web/bun.lock \
  docs_scripts/bun.lock \
  apps/desktop/bun.lock \
  apps/desktop/core/Cargo.lock \
  apps/desktop/src-tauri/Cargo.lock \
  apps/cli-v2/Cargo.lock \
  apps/cli/src/ai_stp_cli/provider/verifier-requirements.txt \
  requirements.txt:scripts/safety/requirements.lock; do
  "${scanner}" scan source "--lockfile=${lockfile}" || status=1
done
exit "${status}"
