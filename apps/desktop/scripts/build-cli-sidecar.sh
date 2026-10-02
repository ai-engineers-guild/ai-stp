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
# `--stub` writes a minimal POSIX stub instead (Unix hosts only): it answers
# `version --json` and satisfies tauri-build's externalBin existence check,
# so `cargo check`/`cargo test`/`tauri dev` work without a 5-minute freeze.
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
  if [[ -n "${suffix}" ]]; then
    echo "--stub cannot produce a runnable .exe; build the real sidecar" >&2
    exit 1
  fi
  mkdir -p "${out_dir}"
  cat > "${out_dir}/${bin}" <<'STUB'
#!/bin/sh
# Dev stub for `cargo check`/`tauri dev` without a PyInstaller freeze.
# Answers `version` minimally; everything else fails with AI_STP_STUB.
case "$1" in
  version)
    printf '{"schema_version":1,"ok":true,"data":{"version":"0.0.0-stub","cli_version":"0.0.0-stub"},"warnings":["stub sidecar — build the real one for CLI calls"],"continuations":[],"error":null,"request_id":null,"operation_id":null,"next_actions":[]}\n'
    ;;
  *)
    printf '{"schema_version":1,"ok":false,"data":null,"warnings":[],"continuations":[],"error":{"code":"AI_STP_STUB","message":"dev stub — build the real sidecar for CLI calls"},"request_id":null,"operation_id":null,"next_actions":[]}\n'
    ;;
esac
STUB
  chmod +x "${out_dir}/${bin}"
  echo "stub sidecar written: ${out_dir}/${bin} (replace with a real build before release/dev use)"
  exit 0
fi

work_dir="$(mktemp -d)"
trap 'rm -rf "${work_dir}"' EXIT

PYINSTALLER_VERSION="${PYINSTALLER_VERSION:-6.22.3}"

cat > "${work_dir}/entry.py" <<'EOF'
from ai_stp_cli.app import run

run()
EOF

uv sync --locked --all-packages --directory "${repo_root}"

uv run --directory "${repo_root}" --with "pyinstaller==${PYINSTALLER_VERSION}" \
  pyinstaller --onefile --clean \
  --name "ai-stp-desktop-cli-${triple}" \
  --distpath "${work_dir}/dist" \
  --workpath "${work_dir}/build" \
  --specpath "${work_dir}" \
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
probe="$("${out_dir}/${bin}" version --json)"
case "${probe}" in
  *'"ok": true'*|*'"ok":true'*) ;;
  *) echo "sidecar smoke check failed: ${probe}" >&2; exit 1 ;;
esac
echo "sidecar built: ${out_dir}/${bin}"
