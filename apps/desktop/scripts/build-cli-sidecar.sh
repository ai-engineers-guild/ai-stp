#!/usr/bin/env bash
# Build the ai-stp CLI as a single-file sidecar binary for Tauri
# `bundle.externalBin`: PyInstaller freezes the workspace CLI into
# `src-tauri/sidecar/ai-stp-<target-triple>[.exe]`, which the bundler embeds
# next to the app executable (where core's bundled-path resolver looks first).
#
# Requires uv on PATH and a checkout of this repository. The package set is
# the workspace's locked graph plus a pinned PyInstaller — fetched through uv
# so the repository's package-manager contract still holds (uv and bun only).
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
out_dir="${repo_root}/apps/desktop/src-tauri/sidecar"
work_dir="$(mktemp -d)"
trap 'rm -rf "${work_dir}"' EXIT

PYINSTALLER_VERSION="${PYINSTALLER_VERSION:-6.22.3}"

triple="$(rustc -vV | sed -n 's/^host: //p')"
case "${triple}" in
  *windows*) suffix=".exe" ;;
  *) suffix="" ;;
esac
bin="ai-stp-${triple}${suffix}"

cat > "${work_dir}/entry.py" <<'EOF'
from ai_stp_cli.app import run

run()
EOF

uv sync --locked --all-packages --directory "${repo_root}"

uv run --directory "${repo_root}" --with "pyinstaller==${PYINSTALLER_VERSION}" \
  pyinstaller --onefile --clean \
  --name "ai-stp-${triple}" \
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
cp "${work_dir}/dist/ai-stp-${triple}${suffix}" "${out_dir}/${bin}"
chmod +x "${out_dir}/${bin}" || true

# Prove the frozen binary actually works on this OS before it ships inside
# a bundle — a missing hidden import would otherwise surface only at runtime.
probe="$("${out_dir}/${bin}" version --json)"
case "${probe}" in
  *'"ok": true'*|*'"ok":true'*) ;;
  *) echo "sidecar smoke check failed: ${probe}" >&2; exit 1 ;;
esac
echo "sidecar built: ${out_dir}/${bin}"
