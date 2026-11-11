#!/usr/bin/env bash
# Install pinned safety scanner CLIs into PREFIX (default: /opt/safety-bin).
# Intended for the worker-safety stage of deploy/docker/Dockerfile.app and local Linux ops hosts.
# Does not modify the application venv; Python tools have isolated locked environments.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/versions.env"

PREFIX="${SAFETY_BIN_PREFIX:-/opt/safety-bin}"
# Isolated venv for Python scanners (bandit, pip-audit); never the app venv.
# Built with `uv venv` and populated with `uv pip`; the name is historical.
PIP_VENV="${SAFETY_PIP_VENV:-/opt/safety-venv}"
CISCO_ROOT="${SAFETY_CISCO_ROOT:-/opt/safety-cisco}"
ARCH="$(uname -m)"
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"

mkdir -p "${PREFIX}"
export PATH="${PREFIX}:${PIP_VENV}/bin:${PATH}"

log() { printf 'install_scanners: %s\n' "$*" >&2; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    log "missing required command: $1"
    exit 1
  }
}

download() {
  local url="$1" dest="$2"
  log "fetch ${url}"
  curl -fsSL --retry 3 --retry-delay 2 -o "${dest}" "${url}"
}

verify_sha256() {
  local file="$1" expected="$2"
  printf '%s  %s\n' "${expected}" "${file}" | sha256sum -c - >/dev/null
}

verify_upstream_checksums() {
  local file="$1" asset="$2" checksums_url="$3" checksums
  checksums="$(mktemp)"
  download "${checksums_url}" "${checksums}"
  expected="$(awk -v asset="${asset}" '$2 == asset || $2 == "*" asset {print $1; exit}' "${checksums}")"
  rm -f "${checksums}"
  [[ -n "${expected}" ]] || { log "checksum missing for ${asset}"; exit 1; }
  verify_sha256 "${file}" "${expected}"
}

install_gitleaks() {
  local ver="${GITLEAKS_VERSION}"
  local asset archive
  case "${OS}-${ARCH}" in
    linux-x86_64|linux-amd64) asset="gitleaks_${ver}_linux_x64.tar.gz" ;;
    linux-aarch64|linux-arm64) asset="gitleaks_${ver}_linux_arm64.tar.gz" ;;
    *) log "refuse gitleaks: unsupported ${OS}-${ARCH}"; exit 1 ;;
  esac
  archive="$(mktemp)"
  download "https://github.com/gitleaks/gitleaks/releases/download/v${ver}/${asset}" "${archive}"
  verify_upstream_checksums "${archive}" "${asset}" \
    "https://github.com/gitleaks/gitleaks/releases/download/v${ver}/gitleaks_${ver}_checksums.txt"
  tar -xzf "${archive}" -C "${PREFIX}" gitleaks
  rm -f "${archive}"
  chmod +x "${PREFIX}/gitleaks"
  log "gitleaks ${ver} -> ${PREFIX}/gitleaks"
}

install_osv_scanner() {
  # Asset names omit the version (google/osv-scanner release convention).
  local ver="${OSV_SCANNER_VERSION}"
  local asset
  case "${OS}-${ARCH}" in
    linux-x86_64|linux-amd64) asset="osv-scanner_linux_amd64" ;;
    linux-aarch64|linux-arm64) asset="osv-scanner_linux_arm64" ;;
    *) log "refuse osv-scanner: unsupported ${OS}-${ARCH}"; exit 1 ;;
  esac
  download \
    "https://github.com/google/osv-scanner/releases/download/v${ver}/${asset}" \
    "${PREFIX}/osv-scanner"
  verify_upstream_checksums "${PREFIX}/osv-scanner" "${asset}" \
    "https://github.com/google/osv-scanner/releases/download/v${ver}/osv-scanner_SHA256SUMS"
  chmod +x "${PREFIX}/osv-scanner"
  log "osv-scanner ${ver} -> ${PREFIX}/osv-scanner"
}

install_shellcheck() {
  local ver="${SHELLCHECK_VERSION}"
  local asset archive
  local expected
  case "${OS}-${ARCH}" in
    linux-x86_64|linux-amd64) asset="shellcheck-v${ver}.linux.x86_64.tar.xz"; expected="${SHELLCHECK_SHA256_LINUX_X86_64}" ;;
    linux-aarch64|linux-arm64) asset="shellcheck-v${ver}.linux.aarch64.tar.xz"; expected="${SHELLCHECK_SHA256_LINUX_AARCH64}" ;;
    *) log "refuse shellcheck: unsupported ${OS}-${ARCH}"; exit 1 ;;
  esac
  archive="$(mktemp)"
  download "https://github.com/koalaman/shellcheck/releases/download/v${ver}/${asset}" "${archive}"
  verify_sha256 "${archive}" "${expected}"
  tar -xJf "${archive}" -C /tmp
  mv "/tmp/shellcheck-v${ver}/shellcheck" "${PREFIX}/shellcheck"
  rm -rf "/tmp/shellcheck-v${ver}" "${archive}"
  chmod +x "${PREFIX}/shellcheck"
  log "shellcheck ${ver} -> ${PREFIX}/shellcheck"
}

install_opengrep() {
  # Opengrep ships standalone manylinux binaries (not versioned tarballs).
  local ver="${OPENGREP_VERSION}"
  local asset expected
  case "${OS}-${ARCH}" in
    linux-x86_64|linux-amd64) asset="opengrep_manylinux_x86"; expected="${OPENGREP_SHA256_LINUX_X86}" ;;
    linux-aarch64|linux-arm64) asset="opengrep_manylinux_aarch64"; expected="${OPENGREP_SHA256_LINUX_AARCH64}" ;;
    *)
      log "refuse opengrep binary: unsupported ${OS}-${ARCH}"
      exit 1
      ;;
  esac
  download \
    "https://github.com/opengrep/opengrep/releases/download/v${ver}/${asset}" \
    "${PREFIX}/opengrep"
  verify_sha256 "${PREFIX}/opengrep" "${expected}"
  chmod +x "${PREFIX}/opengrep"
  log "opengrep ${ver} -> ${PREFIX}/opengrep"
}

install_python_tools() {
  require_cmd uv
  log "creating safety venv at ${PIP_VENV}"
  uv venv "${PIP_VENV}"
  uv pip sync --python "${PIP_VENV}" --require-hashes \
    "${SCRIPT_DIR}/requirements.lock"

  log "preparing the isolated locked Cisco scanner"
  uv sync --project "${CISCO_ROOT}" --locked --no-dev

  for tool in bandit pip-audit; do
    [[ -x "${PIP_VENV}/bin/${tool}" ]] || {
      log "missing required python CLI after install: ${tool}"
      exit 1
    }
    ln -sfn "${PIP_VENV}/bin/${tool}" "${PREFIX}/${tool}"
  done
  [[ -x "${CISCO_ROOT}/.venv/bin/skill-scanner" ]] || {
    log "missing required python CLI after install: skill-scanner"
    exit 1
  }
  ln -sfn "${CISCO_ROOT}/.venv/bin/skill-scanner" "${PREFIX}/skill-scanner"
}

python_tool_version() {
  "$1" -c 'import importlib.metadata, sys; print(importlib.metadata.version(sys.argv[1]))' "$2"
}

install_gosec() {
  local ver="${GOSEC_VERSION}"
  local asset archive
  case "${OS}-${ARCH}" in
    linux-x86_64|linux-amd64) asset="gosec_${ver}_linux_amd64.tar.gz" ;;
    linux-aarch64|linux-arm64) asset="gosec_${ver}_linux_arm64.tar.gz" ;;
    *) log "refuse gosec: unsupported ${OS}-${ARCH}"; exit 1 ;;
  esac
  archive="$(mktemp)"
  download "https://github.com/securego/gosec/releases/download/v${ver}/${asset}" "${archive}"
  verify_upstream_checksums "${archive}" "${asset}" \
    "https://github.com/securego/gosec/releases/download/v${ver}/gosec_${ver}_checksums.txt"
  tar -xzf "${archive}" -C "${PREFIX}" gosec
  rm -f "${archive}"
  chmod +x "${PREFIX}/gosec"
  log "gosec ${ver} -> ${PREFIX}/gosec"
}

install_govulncheck() {
  # Required Go SCA. Prefer a pre-copied binary (Dockerfile.app go-tools stage);
  # otherwise go install when the toolchain is present. No silent skip.
  if [[ -x "${PREFIX}/govulncheck" ]]; then
    log "govulncheck already present at ${PREFIX}/govulncheck"
    return 0
  fi
  if ! command -v go >/dev/null 2>&1; then
    log "govulncheck missing and go not available; provide binary or go toolchain"
    exit 1
  fi
  export GOPATH="${GOPATH:-/tmp/gopath}"
  export GOCACHE="${GOCACHE:-/tmp/gocache}"
  export GOMODCACHE="${GOMODCACHE:-/tmp/gomodcache}"
  mkdir -p "${GOPATH}" "${GOCACHE}" "${GOMODCACHE}"
  log "installing govulncheck ${GOVULNCHECK_VERSION} via go install"
  GOBIN="${PREFIX}" CGO_ENABLED=0 go install \
    "golang.org/x/vuln/cmd/govulncheck@${GOVULNCHECK_VERSION}"
  if [[ ! -x "${PREFIX}/govulncheck" ]]; then
    log "govulncheck install did not produce ${PREFIX}/govulncheck"
    exit 1
  fi
  log "govulncheck ${GOVULNCHECK_VERSION} -> ${PREFIX}/govulncheck"
}

write_manifest() {
  cat > "${PREFIX}/MANIFEST.txt" <<EOF
gitleaks=${GITLEAKS_VERSION}
opengrep=${OPENGREP_VERSION}
osv-scanner=${OSV_SCANNER_VERSION}
shellcheck=${SHELLCHECK_VERSION}
bandit=$(python_tool_version "${PIP_VENV}/bin/python" bandit)
pip-audit=$(python_tool_version "${PIP_VENV}/bin/python" pip-audit)
gosec=${GOSEC_VERSION}
govulncheck=${GOVULNCHECK_VERSION}
skill-scanner=$(python_tool_version "${CISCO_ROOT}/.venv/bin/python" cisco-ai-skill-scanner)
clamscan=$(clamscan --version | head -n 1)
yara=$(yara --version | head -n 1)
bwrap=$(bwrap --version | head -n 1)
installed_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
host=${OS}-${ARCH}
EOF
  log "wrote ${PREFIX}/MANIFEST.txt"
  for required in gitleaks opengrep osv-scanner shellcheck gosec govulncheck bandit pip-audit skill-scanner; do
    if [[ ! -x "${PREFIX}/${required}" ]]; then
      log "required tool missing after install: ${required}"
      exit 1
    fi
  done
  log "binaries present:"
  ls -la "${PREFIX}" >&2 || true
}

main() {
  if [[ "$#" -gt 1 || ( "$#" -eq 1 && "$1" != --gitleaks-only ) ]]; then
    log "usage: install_scanners.sh [--gitleaks-only]"
    exit 2
  fi
  require_cmd curl
  require_cmd tar
  require_cmd sha256sum
  install_gitleaks
  if [[ "${1:-}" == --gitleaks-only ]]; then
    [[ -x "${PREFIX}/gitleaks" ]]
    [[ "$("${PREFIX}/gitleaks" version)" == "${GITLEAKS_VERSION}" ]]
    return
  fi
  install_osv_scanner
  install_shellcheck
  install_opengrep
  install_gosec
  install_python_tools
  install_govulncheck
  write_manifest
  log "done; PATH should include ${PREFIX} and ${PIP_VENV}/bin"
}

main "$@"
