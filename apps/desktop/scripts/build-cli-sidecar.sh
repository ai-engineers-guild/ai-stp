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
# (the `_cffi_backend` loss below surfaced exactly that way).
PYINSTALLER_VERSION="${PYINSTALLER_VERSION:-6.22.3}"
PYINSTALLER_HOOKS_VERSION="${PYINSTALLER_HOOKS_VERSION:-2026.7}"

cat > "${work_dir}/entry.py" <<'EOF'
from ai_stp_cli.app import run

run()
EOF

uv sync --locked --all-packages --directory "${repo_root}"

# nacl._sodium is a cffi out-of-line extension: it imports _cffi_backend
# internally at load time, which modulegraph cannot see. Past bundles only
# received it through an accidental edge — a dependency that pulled in cffi
# itself — so it is declared here or the frozen CLI dies on nacl import.
uv run --directory "${repo_root}" \
  --with "pyinstaller==${PYINSTALLER_VERSION}" \
  --with "pyinstaller-hooks-contrib==${PYINSTALLER_HOOKS_VERSION}" \
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
# surface a provider-capable CLI actually needs.
probe="$("${out_dir}/${bin}" version --json)"
case "${probe}" in
  *'"ok": true'*|*'"ok":true'*) ;;
  *) echo "sidecar smoke check failed (version): ${probe}" >&2; exit 1 ;;
esac
probe="$("${out_dir}/${bin}" doctor --json)"
case "${probe}" in
  *'"ok": true'*|*'"ok":true'*) ;;
  *) echo "sidecar smoke check failed (doctor): ${probe}" >&2; exit 1 ;;
esac
echo "sidecar built: ${out_dir}/${bin}"
