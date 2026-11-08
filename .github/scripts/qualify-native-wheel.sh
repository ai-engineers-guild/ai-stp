#!/usr/bin/env bash
# Qualify the native wheel through uv and pip.
set -euo pipefail
stem="ai-stp-cli-${RELEASE_VERSION}-${RELEASE_TARGET}"
cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- wheel \
  --archive "release/${stem}.${RELEASE_EXTENSION}" \
  --target "${RELEASE_TARGET}" --version "${RELEASE_VERSION}" \
  --revision "${GITHUB_SHA}" --output wheels
wheel=$(find wheels -maxdepth 1 -name '*.whl' -type f)
test -n "${wheel}"
uv tool install --no-index "${wheel}"
cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- probe \
  --binary "${UV_TOOL_BIN_DIR}/${RELEASE_BINARY}" --version "${RELEASE_VERSION}"
python -m venv "${RUNNER_TEMP}/pip-native"
if [[ "${RUNNER_OS}" == Windows ]]; then
  pip_python="${RUNNER_TEMP}/pip-native/Scripts/python.exe"
  pip_binary="${RUNNER_TEMP}/pip-native/Scripts/${RELEASE_BINARY}"
else
  pip_python="${RUNNER_TEMP}/pip-native/bin/python"
  pip_binary="${RUNNER_TEMP}/pip-native/bin/${RELEASE_BINARY}"
fi
"${pip_python}" -m pip install --no-index --no-deps "${wheel}"
cargo run --quiet --locked --manifest-path apps/cli/xtask/Cargo.toml -- probe \
  --binary "${pip_binary}" --version "${RELEASE_VERSION}"
cp "${wheel}" release/
(cd release && sha256sum -- *.whl > "$(basename "${wheel}").sha256")
