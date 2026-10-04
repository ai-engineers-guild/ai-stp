#!/usr/bin/env bash
# Build the ai-stp CLI as a single-file sidecar binary for Tauri
# `bundle.externalBin`: PyInstaller freezes the workspace CLI into
# `src-tauri/sidecar/ai-stp-desktop-cli-<target-triple>[.exe]`, which the
# bundler embeds next to the app executable (where core's bundled-path
# resolver looks first). The name is deliberately not `ai-stp`: a bare
# `ai-stp` sidecar would be installed at /usr/bin/ai-stp by Linux packages
# and collide with the standalone CLI package.
#
# Requires uv on PATH and a checkout of this repository. The package set is
# the workspace's locked graph plus a pinned PyInstaller — fetched through uv
# so the repository's package-manager contract still holds (uv and bun only).
#
# `--stub` writes a stand-in instead: on POSIX hosts a minimal shell stub
# that answers `version --json`, on Windows a marked non-runnable
# placeholder — the shell crate's checks need the externalBin path to
# exist at compile time but never execute it. An existing sidecar is never
# overwritten either way, so `cargo check`/`cargo test`/`tauri dev` work
# without a 5-minute freeze and a real build is left in place.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
out_dir="${repo_root}/apps/desktop/src-tauri/sidecar"

triple="$(rustc -vV | sed -n 's/^host: //p')"
case "${triple}" in
  *windows*) suffix=".exe" ;;
  *) suffix="" ;;
esac
bin="ai-stp-desktop-cli-${triple}${suffix}"

if [[ "${1:-}" == "--stub" ]]; then
  # Never overwrite an existing sidecar — a real PyInstaller build must not
  # be silently replaced by a stub during a local `desktop-check`.
  if [[ -f "${out_dir}/${bin}" ]]; then
    echo "sidecar already exists: ${out_dir}/${bin} (stub not written)"
    exit 0
  fi
  if [[ -n "${suffix}" ]]; then
    # Windows: shell-crate checks need the file to exist (tauri-build
    # verifies externalBin paths at compile time) but never execute it —
    # the real CLI tests are gated behind AI_STP_REAL_CLI. A marked
    # non-runnable placeholder is honest; running it fails loudly.
    mkdir -p "${out_dir}"
    printf '# stub sidecar — not a runnable binary; build the real one\n' \
      > "${out_dir}/${bin}"
    echo "stub sidecar placeholder written: ${out_dir}/${bin} (exists for compile-time checks only)"
    exit 0
  fi
  mkdir -p "${out_dir}"
  cat > "${out_dir}/${bin}" <<'STUB'
#!/bin/sh
# Dev stub for `cargo check`/`tauri dev` without a PyInstaller freeze.
# Answers `version` minimally; everything else fails with DESKTOP_STUB.
case "$1" in
  version)
    printf '{"schema_version":1,"ok":true,"data":{"version":"0.0.0-stub","cli_version":"0.0.0-stub"},"warnings":["stub sidecar — build the real one for CLI calls"],"continuations":[],"error":null,"request_id":null,"operation_id":null,"next_actions":[]}\n'
    ;;
  *)
    printf '{"schema_version":1,"ok":false,"data":null,"warnings":[],"continuations":[],"error":{"code":"DESKTOP_STUB","message":"dev stub — build the real sidecar for CLI calls"},"request_id":null,"operation_id":null,"next_actions":[]}\n'
    ;;
esac
STUB
  chmod +x "${out_dir}/${bin}"
  echo "stub sidecar written: ${out_dir}/${bin} (replace with a real build before release/dev use)"
  exit 0
fi

work_dir="$(mktemp -d)"
trap 'rm -rf "${work_dir}"' EXIT

# The toolset that decides what lands in the bundle is pinned as a set —
# pinning PyInstaller alone left `pyinstaller-hooks-contrib` floating, and
# a hook release silently changed which modules reached the frozen CLI
# (the `_cffi_backend` loss below surfaced exactly that way). The same is
# true one level down: altgraph/macholib/pefile/pywin32-ctypes/setuptools
# are open lower bounds of `pyinstaller`, so they are pinned too — the
# versions below are the closure `uv pip compile` resolved for this pair.
PYINSTALLER_VERSION="${PYINSTALLER_VERSION:-6.22.3}"
PYINSTALLER_HOOKS_VERSION="${PYINSTALLER_HOOKS_VERSION:-2026.7}"
PYINSTALLER_TOOLSET=(
  "pyinstaller==${PYINSTALLER_VERSION}"
  "pyinstaller-hooks-contrib==${PYINSTALLER_HOOKS_VERSION}"
  "altgraph==0.17.5"
  "packaging==26.3"
  "setuptools==84.0.0"
  "macholib==1.16.4; sys_platform == 'darwin'"
  "pefile==2024.8.26; sys_platform == 'win32'"
  "pywin32-ctypes==0.2.3; sys_platform == 'win32'"
)

cat > "${work_dir}/entry.py" <<'EOF'
from ai_stp_cli.app import run

run()
EOF

uv sync --locked --all-packages --directory "${repo_root}"

# nacl._sodium is a cffi out-of-line extension: it imports _cffi_backend
# internally at load time, which modulegraph cannot see. Past bundles only
# received it through an accidental edge — a dependency that pulled in cffi
# itself — so it is declared here or the frozen CLI dies on nacl import.
TOOLSET_WITH=()
for spec in "${PYINSTALLER_TOOLSET[@]}"; do
  TOOLSET_WITH+=("--with" "${spec}")
done

uv run --directory "${repo_root}" \
  "${TOOLSET_WITH[@]}" \
  pyinstaller --onefile --clean \
  --name "ai-stp-desktop-cli-${triple}" \
  --distpath "${work_dir}/dist" \
  --workpath "${work_dir}/build" \
  --specpath "${work_dir}" \
  --hidden-import _cffi_backend \
  --collect-all ai_stp_cli \
  --collect-all ai_stp_foundation \
  --collect-all ai_stp_contracts \
  --collect-all ai_stp_passports \
  --collect-all ai_stp_assurance \
  --collect-all ai_stp_sources \
  "${work_dir}/entry.py"

mkdir -p "${out_dir}"
cp "${work_dir}/dist/ai-stp-desktop-cli-${triple}${suffix}" "${out_dir}/${bin}"
chmod +x "${out_dir}/${bin}" || true

# Prove the frozen binary actually works on this OS before it ships inside
# a bundle — a missing hidden import would otherwise surface only at runtime.
# `version` proves the bootloader ran; `doctor` walks the interpreter/env
# surface a provider-capable CLI actually needs. Both probes run against a
# hermetic home so the check measures the binary, not this host's config —
# a malformed host config.toml or corrupt registry would otherwise fail a
# good build (and doctor would probe the real OS keyring).
# Each probe is bounded: a hung probe (observed once on macOS — the frozen
# binary never returned from first exec, likely an ad-hoc-signing/
# Gatekeeper stall) must surface as a named failure, not burn the whole
# CI job budget.
probe_env=(
  env
  "HOME=${work_dir}/home"
  "XDG_CONFIG_HOME=${work_dir}/home/.config"
  "XDG_DATA_HOME=${work_dir}/home/.local/share"
  "USERPROFILE=${work_dir}/home"
  "APPDATA=${work_dir}/home/AppData/Roaming"
  "LOCALAPPDATA=${work_dir}/home/AppData/Local"
)
probe_seconds=180
if [[ "$(uname -s)" == "Darwin" ]]; then
  # macOS's first-exec path for an unsigned binary can be slower than the
  # Linux/Windows spawn — keep the bound generous, still bounded.
  probe_seconds=300
fi
# `timeout` is GNU coreutils: Git Bash ships it, GH macOS runners ship it as
# `gtimeout`; absent either, the probe runs unbounded — as before — with a
# warning rather than silently pretending it is bounded.
TIMEOUT_CMD=""
for _cand in timeout gtimeout; do
  if command -v "${_cand}" >/dev/null 2>&1; then
    TIMEOUT_CMD="${_cand}"
    break
  fi
done
if [[ -z "${TIMEOUT_CMD}" ]]; then
  echo "warning: no timeout/gtimeout found — smoke probes run unbounded" >&2
fi
mkdir -p "${work_dir}/home"
run_probe() {
  if [[ -n "${TIMEOUT_CMD}" ]]; then
    "${TIMEOUT_CMD}" "${probe_seconds}" "${probe_env[@]}" "${out_dir}/${bin}" "$@" 2>&1
  else
    "${probe_env[@]}" "${out_dir}/${bin}" "$@" 2>&1
  fi
}
probe="$(run_probe version --json)" || {
  echo "sidecar smoke check failed (version, exit $?, timeout ${probe_seconds}s): ${probe}" >&2
  exit 1
}
case "${probe}" in
  *'"ok": true'*|*'"ok":true'*) ;;
  *) echo "sidecar smoke check failed (version): ${probe}" >&2; exit 1 ;;
esac
probe="$(run_probe doctor --json)" || {
  echo "sidecar smoke check failed (doctor, exit $?, timeout ${probe_seconds}s): ${probe}" >&2
  exit 1
}
case "${probe}" in
  *'"ok": true'*|*'"ok":true'*) ;;
  *) echo "sidecar smoke check failed (doctor): ${probe}" >&2; exit 1 ;;
esac
echo "sidecar built: ${out_dir}/${bin}"
