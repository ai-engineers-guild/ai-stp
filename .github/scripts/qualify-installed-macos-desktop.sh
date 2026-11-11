#!/usr/bin/env bash
# Exercise an exact installed DMG without changing the runner's accessibility permissions.
set -euo pipefail
test "${GITHUB_ACTIONS}" = true
test "${RUNNER_ENVIRONMENT}" = github-hosted
test "${RUNNER_OS}" = macOS
test "$#" -eq 3
bundle="$1"
source="$2"
output="$3"
manifest="${bundle}/qualified-desktop-macOS.json"
entry=$(jq -ce --arg source "${source}" '
  select(.schema_version == 1 and .platform == "macOS" and .source_commit == $source) |
  .files | select(length == 1) | .[0] |
  select((.path | test("^dmg/[A-Za-z0-9_.-]+[.]dmg$")) and (.sha256 | test("^[0-9a-f]{64}$")))
' "${manifest}")
installer="${bundle}/$(jq -r .path <<<"${entry}")"
expected="$(jq -r .sha256 <<<"${entry}")"
test "$(shasum -a 256 "${installer}" | cut -d ' ' -f 1)" = "${expected}"

fixture=$(mktemp -d "${RUNNER_TEMP}/ai-stp-installed-macos.XXXXXX")
cleanup() {
  if test -f "${fixture}/mounted"; then hdiutil detach "${fixture}/mount" >/dev/null; fi
  rm -rf "${fixture}"
}
trap cleanup EXIT
mkdir -m 700 "${fixture}/mount" "${fixture}/home"
hdiutil attach -readonly -nobrowse -mountpoint "${fixture}/mount" "${installer}" >/dev/null
touch "${fixture}/mounted"
ditto "${fixture}/mount/ai-stp-desktop.app" "${fixture}/ai-stp-desktop.app"
hdiutil detach "${fixture}/mount" >/dev/null
rm "${fixture}/mounted"
app="${fixture}/ai-stp-desktop.app/Contents/MacOS/ai-stp-desktop"
cli="${fixture}/ai-stp-desktop.app/Contents/Resources/cli/ai-stp-desktop-cli"
test -x "${app}" && test -x "${cli}"
version=$(HOME="${fixture}/home" swift .github/scripts/qualify-installed-macos-desktop.swift "${app}" "${cli}")
[[ "${version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
jq -n --arg source "${source}" --arg installer "${expected}" --arg version "${version}" \
  --arg app "$(shasum -a 256 "${app}" | cut -d ' ' -f 1)" \
  --arg cli "$(shasum -a 256 "${cli}" | cut -d ' ' -f 1)" \
  '{schema_version:1,source_sha:$source,installer_sha256:$installer,app_sha256:$app,
    cli_sha256:$cli,cli_version:$version,installed_personal_workspace_restart:true,
    corporate_acceptance:false,release_authorized:false}' > "${output}"
