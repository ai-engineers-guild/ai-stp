#!/usr/bin/env bash
# Put the pinned bun on PATH, without npm.
#
# `npm install --global bun` cost 67s on the Windows runner against 5s on
# Linux: the download is the same on both, and the difference is npm creating
# its global prefix and shims on a filesystem that charges for every file
# operation. bun ships one binary per platform, so fetching that binary and
# adding its directory to PATH does the same job in one download and one
# extraction.
#
# The archive holds `bun` only — no `bunx`. Callers use `bun x` instead, which
# is what `bunx` is; the workflow does not depend on argv[0] detection.
set -euo pipefail

version="${1:?usage: install-bun.sh <version> <destination>}"
destination="${2:?usage: install-bun.sh <version> <destination>}"

case "$(uname -s)" in
  Linux) system="linux" ;;
  Darwin) system="darwin" ;;
  MINGW* | MSYS* | CYGWIN* | Windows_NT) system="windows" ;;
  *)
    echo "install-bun: unknown system $(uname -s)" >&2
    exit 1
    ;;
esac

case "$(uname -m)" in
  x86_64 | amd64) machine="x64" ;;
  arm64 | aarch64) machine="aarch64" ;;
  *)
    echo "install-bun: unknown machine $(uname -m)" >&2
    exit 1
    ;;
esac

# There is no aarch64 Windows build; the runner is x64 either way.
if [ "${system}" = "windows" ]; then
  machine="x64"
fi

target="bun-${system}-${machine}"
base="https://github.com/oven-sh/bun/releases/download/bun-v${version}"

mkdir -p "${destination}"
work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

curl --fail --silent --show-error --location --retry 3 \
  --output "${work}/${target}.zip" "${base}/${target}.zip"
curl --fail --silent --show-error --location --retry 3 \
  --output "${work}/SHASUMS256.txt" "${base}/SHASUMS256.txt"

# The published sums cover every asset of the release; check only the one that
# was downloaded, and fail if the release does not name it at all.
expected="$(awk -v name="${target}.zip" '$2 == name || $2 == "*" name {print $1}' \
  "${work}/SHASUMS256.txt")"
if [ -z "${expected}" ]; then
  echo "install-bun: ${target}.zip is not listed in SHASUMS256.txt" >&2
  exit 1
fi
if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "${work}/${target}.zip" | cut -d' ' -f1)"
else
  actual="$(shasum -a 256 "${work}/${target}.zip" | cut -d' ' -f1)"
fi
if [ "${expected}" != "${actual}" ]; then
  echo "install-bun: ${target}.zip is ${actual}, expected ${expected}" >&2
  exit 1
fi

unzip -q -o "${work}/${target}.zip" -d "${work}"
binary="${work}/${target}/bun"
[ -f "${binary}" ] || binary="${work}/${target}/bun.exe"
if [ ! -f "${binary}" ]; then
  echo "install-bun: the archive held no bun binary" >&2
  exit 1
fi
mv "${binary}" "${destination}/"
chmod +x "${destination}/$(basename "${binary}")"

installed="$("${destination}/$(basename "${binary}")" --version)"
if [ "${installed}" != "${version}" ]; then
  echo "install-bun: installed ${installed}, expected ${version}" >&2
  exit 1
fi
echo "install-bun: bun ${installed} at ${destination}"
