#!/usr/bin/env bash
# Package the optimized native CLI as the desktop's sole execution engine.
# The generated resource tree contains no interpreter or Python runtime.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
cli_root="${repo_root}/apps/cli-v2"
out_dir="${repo_root}/apps/desktop/src-tauri/sidecar/cli"
triple="$(cd "${cli_root}" && rustc -vV | sed -n 's/^host: //p')"
case "${triple}" in
  *windows*) suffix=".exe" ;;
  *) suffix="" ;;
esac
bin="ai-stp-desktop-cli${suffix}"

if [[ "${1:-}" == "--stub" ]]; then
  # Never overwrite an existing sidecar — a real Rust build must not
  # be silently replaced by a stub during a local `desktop-check`.
  if [[ -f "${out_dir}/${bin}" ]]; then
    echo "sidecar already exists: ${out_dir}/${bin} (stub not written)"
    exit 0
  fi
  if [[ -n "${suffix}" ]]; then
    # Windows: shell-crate checks need the file to exist (tauri-build
    # verifies resource paths at compile time) but never execute it —
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
# Dev stub for `cargo check`/`tauri dev` without a native build.
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

cd "${cli_root}"
uv run --locked python scripts/with_libclang.py cargo build --locked --release --target-dir target --bin ai-stp-v2
mkdir -p "$(dirname "${out_dir}")"
work_dir="$(mktemp -d "$(dirname "${out_dir}")/.native-cli-XXXXXX")"
trap 'rm -rf "${work_dir}"' EXIT
cp "target/release/ai-stp-v2${suffix}" "${work_dir}/${bin}"
if [[ -z "${suffix}" ]]; then chmod +x "${work_dir}/${bin}"; fi

# Verify the copied executable itself before replacing the generated resources.
# Python is only a build-time probe, never part of the shipped sidecar.
uv run --locked python - "${work_dir}/${bin}" "${triple}" <<'PYPROBE'
import hashlib, json, subprocess, sys
from pathlib import Path
executable=Path(sys.argv[1]).resolve()
def read(command):
    result=subprocess.run([str(executable),*command,'--json'],capture_output=True,timeout=30)
    value=json.loads(result.stdout)
    if result.returncode or result.stderr or not value.get('ok'):
        raise SystemExit('native desktop resource probe failed')
    return value['data']
version=read(['version'])
if version.get('runtime')!='rust': raise SystemExit('desktop resource is not the Rust engine')
capabilities=read(['capabilities'])
help=read(['help','--agent'])
if capabilities['registry_digest']!=help['registry_digest']:
    raise SystemExit('native desktop registry changed during packaging')
manifest={'schema_version':1,'runtime':'rust','target':sys.argv[2],
          'cli_version':version['cli_version'],'registry_digest':capabilities['registry_digest'],
          'executable':executable.name,'sha256':hashlib.sha256(executable.read_bytes()).hexdigest()}
(executable.parent/'sidecar.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
PYPROBE

# This directory contains only generated build resources. Retiring it also
# removes obsolete interpreter libraries from previous desktop builds.
rm -rf "${out_dir}"
mv "${work_dir}" "${out_dir}"
trap - EXIT
echo "Rust sidecar ready: ${out_dir}/${bin}"
