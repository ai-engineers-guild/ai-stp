#!/usr/bin/env bash
# Install pinned safety scanner CLIs into PREFIX (default: /opt/safety-bin).
# Intended for Dockerfile.worker-safety and local Linux ops hosts.
# Does not modify the application venv; Python tools go to SAFETY_PIP_PREFIX.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/versions.env"

PREFIX="${SAFETY_BIN_PREFIX:-/opt/safety-bin}"
# Isolated venv for Python scanners (bandit, pip-audit); never the app venv.
# Built with `uv venv` and populated with `uv pip`; the name is historical.
PIP_VENV="${SAFETY_PIP_VENV:-/opt/safety-venv}"
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

install_gitleaks() {
  local ver="${GITLEAKS_VERSION}"
  local asset archive
  case "${OS}-${ARCH}" in
    linux-x86_64|linux-amd64) asset="gitleaks_${ver}_linux_x64.tar.gz" ;;
    linux-aarch64|linux-arm64) asset="gitleaks_${ver}_linux_arm64.tar.gz" ;;
    *) log "skip gitleaks: unsupported ${OS}-${ARCH}"; return 0 ;;
  esac
  archive="$(mktemp)"
  download "https://github.com/gitleaks/gitleaks/releases/download/v${ver}/${asset}" "${archive}"
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
    *) log "skip osv-scanner: unsupported ${OS}-${ARCH}"; return 0 ;;
  esac
  download \
    "https://github.com/google/osv-scanner/releases/download/v${ver}/${asset}" \
    "${PREFIX}/osv-scanner"
  chmod +x "${PREFIX}/osv-scanner"
  log "osv-scanner ${ver} -> ${PREFIX}/osv-scanner"
}

install_shellcheck() {
  local ver="${SHELLCHECK_VERSION}"
  local asset archive
  case "${OS}-${ARCH}" in
    linux-x86_64|linux-amd64) asset="shellcheck-v${ver}.linux.x86_64.tar.xz" ;;
    linux-aarch64|linux-arm64) asset="shellcheck-v${ver}.linux.aarch64.tar.xz" ;;
    *) log "skip shellcheck: unsupported ${OS}-${ARCH}"; return 0 ;;
  esac
  archive="$(mktemp)"
  download "https://github.com/koalaman/shellcheck/releases/download/v${ver}/${asset}" "${archive}"
  tar -xJf "${archive}" -C /tmp
  mv "/tmp/shellcheck-v${ver}/shellcheck" "${PREFIX}/shellcheck"
  rm -rf "/tmp/shellcheck-v${ver}" "${archive}"
  chmod +x "${PREFIX}/shellcheck"
  log "shellcheck ${ver} -> ${PREFIX}/shellcheck"
}

install_opengrep() {
  # Opengrep ships standalone manylinux binaries (not versioned tarballs).
  local ver="${OPENGREP_VERSION}"
  local asset
  case "${OS}-${ARCH}" in
    linux-x86_64|linux-amd64) asset="opengrep_manylinux_x86" ;;
    linux-aarch64|linux-arm64) asset="opengrep_manylinux_aarch64" ;;
    *)
      log "skip opengrep binary: unsupported ${OS}-${ARCH} (in-proc fallback remains)"
      return 0
      ;;
  esac
  if ! download \
    "https://github.com/opengrep/opengrep/releases/download/v${ver}/${asset}" \
    "${PREFIX}/opengrep"; then
    log "opengrep release asset unavailable; skipping CLI (vendored rules still used in-proc)"
    rm -f "${PREFIX}/opengrep"
    return 0
  fi
  chmod +x "${PREFIX}/opengrep"
  log "opengrep ${ver} -> ${PREFIX}/opengrep"
}

install_python_tools() {
  # `uv`, not `pip`: one package manager per language, which is what
  # `.gds/compiled-policy.json` says and what the rest of the repository does.
  # `pip-audit` and `bandit` stay — they are scanners this image runs against
  # other people's artefacts. How *this* image installs them is our business.
  require_cmd uv
  require_cmd git
  log "creating safety venv at ${PIP_VENV}"
  uv venv "${PIP_VENV}"
  uv pip install --python "${PIP_VENV}" --no-cache \
    "bandit==${BANDIT_VERSION}" \
    "pip-audit==${PIP_AUDIT_VERSION}"

  # NVIDIA SkillSpector: not on PyPI; pin a git tag (CLI entrypoint: skillspector).
  local ss_url="${SKILLSPECTOR_GIT_URL:?SKILLSPECTOR_GIT_URL required}"
  local ss_ref="${SKILLSPECTOR_GIT_REF:?SKILLSPECTOR_GIT_REF required}"
  log "installing skillspector from ${ss_url}@${ss_ref}"
  uv pip install --python "${PIP_VENV}" --no-cache \
    "git+${ss_url}@${ss_ref}"

  # Cisco second engine: PyPI package cisco-ai-skill-scanner → CLI skill-scanner.
  local cisco_pkg="${SKILL_SCANNER_PACKAGE:-cisco-ai-skill-scanner}"
  local cisco_ver="${SKILL_SCANNER_VERSION:?SKILL_SCANNER_VERSION required}"
  log "installing ${cisco_pkg}==${cisco_ver}"
  uv pip install --python "${PIP_VENV}" --no-cache \
    "${cisco_pkg}==${cisco_ver}"

  # Symlink into PREFIX so PATH=/opt/safety-bin is enough.
  for tool in bandit pip-audit skillspector skill-scanner; do
    if [[ -x "${PIP_VENV}/bin/${tool}" ]]; then
      ln -sfn "${PIP_VENV}/bin/${tool}" "${PREFIX}/${tool}"
    else
      log "missing required python CLI after install: ${tool}"
      exit 1
    fi
  done
  log "python tools installed under ${PIP_VENV}"
}

install_gosec() {
  local ver="${GOSEC_VERSION}"
  local asset archive
  case "${OS}-${ARCH}" in
    linux-x86_64|linux-amd64) asset="gosec_${ver}_linux_amd64.tar.gz" ;;
    linux-aarch64|linux-arm64) asset="gosec_${ver}_linux_arm64.tar.gz" ;;
    *) log "skip gosec: unsupported ${OS}-${ARCH}"; return 0 ;;
  esac
  archive="$(mktemp)"
  download "https://github.com/securego/gosec/releases/download/v${ver}/${asset}" "${archive}"
  tar -xzf "${archive}" -C "${PREFIX}" gosec
  rm -f "${archive}"
  chmod +x "${PREFIX}/gosec"
  log "gosec ${ver} -> ${PREFIX}/gosec"
}

install_govulncheck() {
  # Required Go SCA. Prefer a pre-copied binary (Dockerfile go-tools stage);
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
bandit=${BANDIT_VERSION}
pip-audit=${PIP_AUDIT_VERSION}
gosec=${GOSEC_VERSION}
govulncheck=${GOVULNCHECK_VERSION}
skillspector=${SKILLSPECTOR_GIT_REF}
skill-scanner=${SKILL_SCANNER_PACKAGE}==${SKILL_SCANNER_VERSION}
installed_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
host=${OS}-${ARCH}
EOF
  log "wrote ${PREFIX}/MANIFEST.txt"
  for required in gitleaks osv-scanner shellcheck gosec govulncheck bandit pip-audit skillspector skill-scanner; do
    if [[ ! -x "${PREFIX}/${required}" ]]; then
      log "required tool missing after install: ${required}"
      exit 1
    fi
  done
  log "binaries present:"
  ls -la "${PREFIX}" >&2 || true
}

main() {
  require_cmd curl
  require_cmd tar
  install_gitleaks
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
