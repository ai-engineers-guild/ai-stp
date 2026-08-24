#!/usr/bin/env bash
# Put the pinned uv on PATH, without pip.
#
# `python -m pip install uv` was the bootstrap on twenty-one jobs: pip resolving
# and installing a wheel to get a single static binary that astral publishes
# directly. Fetching that binary is the same shape as `install-bun.sh`, keeps
# the toolchain on one package manager per language, and removes pip from the
# gate entirely — pip only appeared here to install uv.
#
# Pinned by version and checked against the per-asset `.sha256` the release
# publishes, like every other third-party byte this repository downloads.
set -euo pipefail

version="${1:?usage: install-uv.sh <version> <destination>}"
destination="${2:?usage: install-uv.sh <version> <destination>}"

case "$(uname -s)" in
  Linux) system="unknown-linux-gnu" ;;
  Darwin) system="apple-darwin" ;;
  MINGW* | MSYS* | CYGWIN* | Windows_NT) system="pc-windows-msvc" ;;
  *)
    echo "install-uv: unknown system $(uname -s)" >&2
    exit 1
    ;;
esac

case "$(uname -m)" in
  x86_64 | amd64) machine="x86_64" ;;
  arm64 | aarch64) machine="aarch64" ;;
  *)
    echo "install-uv: unknown machine $(uname -m)" >&2
    exit 1
    ;;
esac

# There is no aarch64 Windows build; the runner is x86_64 either way.
if [ "${system}" = "pc-windows-msvc" ]; then
  machine="x86_64"
  archive="uv-${machine}-${system}.zip"
else
  archive="uv-${machine}-${system}.tar.gz"
fi
base="https://github.com/astral-sh/uv/releases/download/${version}"

mkdir -p "${destination}"
work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

curl --fail --silent --show-error --location --retry 3 \
  --output "${work}/${archive}" "${base}/${archive}"
curl --fail --silent --show-error --location --retry 3 \
  --output "${work}/${archive}.sha256" "${base}/${archive}.sha256"

expected="$(cut -d' ' -f1 <"${work}/${archive}.sha256")"
if [ -z "${expected}" ]; then
  echo "install-uv: ${archive}.sha256 named no digest" >&2
  exit 1
fi
if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "${work}/${archive}" | cut -d' ' -f1)"
else
  actual="$(shasum -a 256 "${work}/${archive}" | cut -d' ' -f1)"
fi
if [ "${expected}" != "${actual}" ]; then
  echo "install-uv: ${archive} is ${actual}, expected ${expected}" >&2
  exit 1
fi

case "${archive}" in
  *.zip) unzip -q -o "${work}/${archive}" -d "${work}/unpacked" ;;
  *) mkdir -p "${work}/unpacked" && tar -xzf "${work}/${archive}" -C "${work}/unpacked" ;;
esac

# The tarball nests the binaries under a directory named after the target; the
# Windows archive puts them at the top. Find them rather than encode the shape.
for name in uv uvx; do
  found="$(find "${work}/unpacked" -type f \( -name "${name}" -o -name "${name}.exe" \) -print -quit)"
  if [ -z "${found}" ]; then
    echo "install-uv: the archive held no ${name}" >&2
    exit 1
  fi
  mv "${found}" "${destination}/"
  chmod +x "${destination}/$(basename "${found}")"
done

uv_binary="${destination}/uv"
[ -x "${uv_binary}" ] || uv_binary="${destination}/uv.exe"
installed="$("${uv_binary}" --version | awk '{print $2}')"
if [ "${installed}" != "${version}" ]; then
  echo "install-uv: installed ${installed}, expected ${version}" >&2
  exit 1
fi
echo "install-uv: uv ${installed} at ${destination}"
