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
  if test -f "${fixture}/personal-journey.json"; then
    rm -rf "${fixture}"
  else
    echo "Retained refused native fixture until disposable runner teardown" >&2
  fi
}
trap cleanup EXIT
mkdir -m 700 "${fixture}/mount" "${fixture}/data" "${fixture}/config" "${fixture}/cache"
hdiutil attach -readonly -nobrowse -mountpoint "${fixture}/mount" "${installer}" >/dev/null
touch "${fixture}/mounted"
ditto "${fixture}/mount/ai-stp-desktop.app" "${fixture}/ai-stp-desktop.app"
hdiutil detach "${fixture}/mount" >/dev/null
rm "${fixture}/mounted"
app="${fixture}/ai-stp-desktop.app/Contents/MacOS/ai-stp-desktop"
cli="${fixture}/ai-stp-desktop.app/Contents/Resources/cli/ai-stp-desktop-cli"
test -x "${app}" && test -x "${cli}"
# Preserve the disposable login session for the existing native Keychain.
export XDG_DATA_HOME="${fixture}/data"
export XDG_CONFIG_HOME="${fixture}/config"
export XDG_CACHE_HOME="${fixture}/cache"
swift .github/scripts/qualify-installed-macos-desktop.swift "${app}" "${cli}" apps/desktop/src/locales "${fixture}/personal-journey.json"
journey=$(cat "${fixture}/personal-journey.json")
jq -e '.cli_version | test("^[0-9]+[.][0-9]+[.][0-9]+$")' <<<"${journey}" >/dev/null
jq -n --arg source "${source}" --arg installer "${expected}" --argjson journey "${journey}" \
  --arg app "$(shasum -a 256 "${app}" | cut -d ' ' -f 1)" \
  --arg cli "$(shasum -a 256 "${cli}" | cut -d ' ' -f 1)" \
  '{schema_version:2,source_sha:$source,installer_sha256:$installer,app_sha256:$app,
    cli_sha256:$cli,cli_version:$journey.cli_version,installed_personal_workspace_restart:true,
    personal_controls:$journey.personal_controls,theme_locale_observations:$journey.theme_locale_observations,
    corporate_acceptance:false,release_authorized:false}' > "${output}"
