#!/usr/bin/env bash
# Freeze the released CLI wheel and its locked dependency closure as a
# complete PyInstaller directory. Tauri bundle.resources preserves the
# tree under cli/ in the platform resource directory. Keeping the name
# ai-stp-desktop-cli avoids collisions with the standalone CLI.
#
# Requires uv on PATH and a checkout of this repository. The package set is
# the CLI's slice of `uv.lock` plus a pinned PyInstaller — fetched through uv
# so the repository's package-manager contract still holds (uv and bun only).
#
# `--stub` writes a stand-in instead: on POSIX hosts a minimal shell stub
# that answers `version --json`, on Windows a marked non-runnable
# placeholder — the shell crate's checks need the resource path to
# exist at compile time but never execute it. An existing sidecar is never
# overwritten either way, so `cargo check`/`cargo test`/`tauri dev` work
# without a 5-minute freeze and a real build is left in place.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../../.." && pwd)"
out_dir="${repo_root}/apps/desktop/src-tauri/sidecar/cli"

triple="$(rustc -vV | sed -n 's/^host: //p')"
case "${triple}" in
  *windows*) suffix=".exe" ;;
  *) suffix="" ;;
esac
bin="ai-stp-desktop-cli${suffix}"

if [[ "${1:-}" == "--stub" ]]; then
  # Never overwrite an existing sidecar — a real PyInstaller build must not
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
PYINSTALLER_HOOKS_VERSION="${PYINSTALLER_HOOKS_VERSION:-2026.8}"
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

# Freeze what a user installs, not the workspace. The workspace environment
# also holds the server, the worker and the dev groups, and PyInstaller
# follows optional imports into whatever is installed: frozen from it, the
# sidecar carried hypothesis (via pydantic.v1), Pillow and its codecs (via
# pygments), uvloop (via anyio) and requests — 48 MB where the CLI's own
# closure freezes to 32 MB, and a dependency set no `pip install ai-stp-cli`
# ever gets. Here the environment is the built wheel plus the hash-checked,
# locked closure of exactly the dependencies it declares.
uv build --directory "${repo_root}" --package ai-stp-cli --wheel \
  --out-dir "${work_dir}/wheel" -q
uv export --directory "${repo_root}" --package ai-stp-cli --locked --no-dev \
  --no-emit-workspace --format requirements-txt \
  --output-file "${work_dir}/requirements.txt" -q
uv venv "${work_dir}/venv" --python "$(uv python find --directory "${repo_root}")" -q
venv_python="${work_dir}/venv/bin/python"
if [[ -n "${suffix}" ]]; then
  venv_python="${work_dir}/venv/Scripts/python.exe"
fi
uv pip install --python "${venv_python}" --require-hashes -q \
  -r "${work_dir}/requirements.txt"
wheels=("${work_dir}"/wheel/ai_stp_cli-*.whl)
uv pip install --python "${venv_python}" --no-deps -q "${wheels[@]}"
uv pip install --python "${venv_python}" -q "${PYINSTALLER_TOOLSET[@]}"

# nacl._sodium is a cffi out-of-line extension: it imports _cffi_backend
# internally at load time, which modulegraph cannot see. Past bundles only
# received it through an accidental edge — a dependency that pulled in cffi
# itself — so it is declared here or the frozen CLI dies on nacl import.
#
# setuptools is in this environment only because PyInstaller depends on it,
# and the CLI never imports it: cffi refers to it from its build-time
# helpers alone. Collected, it brought PyInstaller's setuptools runtime hook,
# which imports setuptools before the CLI starts, on every call: 2.21s against
# 2.04s for `version --json` from the same freeze (median of five, wall).
"${venv_python}" -m PyInstaller --onedir --clean \
  --name "ai-stp-desktop-cli" \
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
  --exclude-module setuptools \
  --exclude-module pkg_resources \
  --exclude-module _distutils_hack \
  "${work_dir}/entry.py"

# Replace only this script's generated tree; the build is reproducible from
# the wheel and lockfile, and stale libraries must not survive a new freeze.
rm -rf "${out_dir}"
mkdir -p "${out_dir}"
cp -a "${work_dir}/dist/ai-stp-desktop-cli/." "${out_dir}/"
chmod +x "${out_dir}/${bin}" || true

# Prove the frozen binary actually works on this OS before it ships inside
# a bundle — a missing hidden import would otherwise surface only at runtime.
# `version` proves the bootloader ran; `doctor` walks the interpreter/env
# surface a provider-capable CLI actually needs. Each probe is bounded by a
# Python one-shot (uv already guarantees an interpreter here — `timeout` is
# GNU coreutils and GH macOS runners ship neither it nor `gtimeout`): a hung
# probe must surface as a named failure, not burn the whole CI job budget.
probe_python="$(uv python find)"
probe_seconds=180
if [[ "$(uname -s)" == "Darwin" ]]; then
  # macOS's first-exec path for an unsigned binary can be slower than the
  # Linux/Windows spawn — keep the bound generous, still bounded.
  probe_seconds=300
fi
cat > "${work_dir}/run_bounded.py" <<'EOF'
"""Run a probe with a wall-clock bound; exit 124 on timeout.

The probe is started in its own process group where the platform supports
it so the CLI and any descendants are killed together.
"""
import os
import signal
import subprocess
import sys

seconds = float(sys.argv[1])
command = sys.argv[2:]
popen_kwargs: dict = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT}
if os.name == "posix":
    popen_kwargs["start_new_session"] = True
proc = subprocess.Popen(command, **popen_kwargs)
try:
    out = proc.communicate(timeout=seconds)[0]
except subprocess.TimeoutExpired:
    if os.name == "posix":
        os.killpg(proc.pid, signal.SIGKILL)
    else:
        proc.kill()
    proc.communicate()
    sys.exit(124)
sys.stdout.write(out.decode("utf-8", "replace"))
sys.exit(proc.returncode)
EOF

run_probe() {
  "${probe_python}" "${work_dir}/run_bounded.py" "${probe_seconds}" "$@" 2>&1
}
# Probes run against a hermetic home so the check measures the binary, not
# this host's config — a malformed host config.toml or corrupt registry
# would otherwise fail a good build. The exception is doctor's credential
# store probe on macOS: the OS keychain is only reachable through the real
# user session and a redirected HOME produces a state the shipped app never
# runs in — observed on CI as the `security` probe stalling until the job
# died. Linux reaches the file tier and Windows the session vault without
# HOME, so they stay hermetic.
mkdir -p "${work_dir}/home"
probe_env=(
  env
  "HOME=${work_dir}/home"
  "XDG_CONFIG_HOME=${work_dir}/home/.config"
  "XDG_DATA_HOME=${work_dir}/home/.local/share"
  "USERPROFILE=${work_dir}/home"
  "APPDATA=${work_dir}/home/AppData/Roaming"
  "LOCALAPPDATA=${work_dir}/home/AppData/Local"
)
doctor_env=("${probe_env[@]}")
if [[ "$(uname -s)" == "Darwin" ]]; then
  doctor_env=(env)
fi

probe_status=0
echo "probe: version --json (bounded ${probe_seconds}s)"
probe="$(run_probe "${probe_env[@]}" "${out_dir}/${bin}" version --json)" || probe_status=$?
if [[ ${probe_status} -ne 0 ]]; then
  echo "sidecar smoke check failed (version, exit ${probe_status}, bound ${probe_seconds}s): ${probe}" >&2
  exit 1
fi
case "${probe}" in
  *'"ok": true'*|*'"ok":true'*) ;;
  *) echo "sidecar smoke check failed (version): ${probe}" >&2; exit 1 ;;
esac
probe_status=0
echo "probe: doctor --json (bounded ${probe_seconds}s)"
probe="$(run_probe "${doctor_env[@]}" "${out_dir}/${bin}" doctor --json)" || probe_status=$?
if [[ ${probe_status} -ne 0 ]]; then
  echo "sidecar smoke check failed (doctor, exit ${probe_status}, bound ${probe_seconds}s): ${probe}" >&2
  exit 1
fi
case "${probe}" in
  *'"ok": true'*|*'"ok":true'*) ;;
  *) echo "sidecar smoke check failed (doctor): ${probe}" >&2; exit 1 ;;
esac
echo "sidecar built: ${out_dir}/${bin}"
