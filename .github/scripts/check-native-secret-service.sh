#!/usr/bin/env bash
# This fixture runs only on a disposable GitHub Linux runner, never a user's bus.
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
test "${RUNNER_OS:-}" = Linux
test -n "${RUNNER_TEMP:-}"
fixture_rounds="${AI_STP_NATIVE_VAULT_ROUNDS:-100}"
[[ "${fixture_rounds}" =~ ^([1-9]|[1-9][0-9]|100)$ ]]

if [[ "${1:-}" != --inside-fixture ]]; then
  fixture_mode=native
  if [[ "${1:-}" == --installed-desktop ]]; then
    test "$#" -eq 1
    fixture_mode=desktop
  elif [[ "${1:-}" == --installed-corporate-desktop ]]; then
    test "$#" -eq 1
    fixture_mode=corporate-desktop
  else
    test "$#" -eq 0
  fi
  export AI_STP_TEST_SECRET_SERVICE_ROOT
  AI_STP_TEST_SECRET_SERVICE_ROOT="$(mktemp -d "${RUNNER_TEMP}/ai-stp-secret-service.XXXXXXXX")"
  chmod 700 "${AI_STP_TEST_SECRET_SERVICE_ROOT}"
  umask 077
  export XDG_DATA_HOME="${AI_STP_TEST_SECRET_SERVICE_ROOT}/data"
  export XDG_CONFIG_HOME="${AI_STP_TEST_SECRET_SERVICE_ROOT}/config"
  export XDG_RUNTIME_DIR="${AI_STP_TEST_SECRET_SERVICE_ROOT}/runtime"
  export AI_STP_TEST_SECRET_SERVICE=isolated
  mkdir -m 700 "${XDG_DATA_HOME}" "${XDG_CONFIG_HOME}" "${XDG_RUNTIME_DIR}" \
    "${AI_STP_TEST_SECRET_SERVICE_ROOT}/control"
  exec dbus-run-session -- bash "$0" --inside-fixture "${fixture_mode}"
fi

test "$#" -eq 2
fixture_mode="$2"
[[ "${fixture_mode}" == native || "${fixture_mode}" == desktop || "${fixture_mode}" == corporate-desktop ]]
test -d "${AI_STP_TEST_SECRET_SERVICE_ROOT}"
test "${AI_STP_TEST_SECRET_SERVICE}" = isolated

# Only synthetic credentials live here. No SSH/PKCS11 component is started.
printf '%s' 'ai-stp-disposable-ci-fixture' | gnome-keyring-daemon \
  --foreground --components=secrets --unlock \
  --control-directory="${AI_STP_TEST_SECRET_SERVICE_ROOT}/control" \
  >"${AI_STP_TEST_SECRET_SERVICE_ROOT}/daemon.log" 2>&1 &
fixture_pid=$!
fixture_cleanup() {
  fixture_status=$?
  trap - EXIT
  if [[ "${fixture_status}" -ne 0 ]]; then
    fixture_alive=false
    if kill -0 "${fixture_pid}" 2>/dev/null; then fixture_alive=true; fi
    fixture_owner="$(gdbus call --session --dest org.freedesktop.DBus \
      --object-path /org/freedesktop/DBus \
      --method org.freedesktop.DBus.GetConnectionUnixProcessID \
      org.freedesktop.secrets 2>/dev/null || true)"
    fixture_owner_unchanged=false
    if [[ "${fixture_owner}" = "(uint32 ${fixture_pid},)" ]]; then
      fixture_owner_unchanged=true
    fi
    # Print only fixed marker presence, never raw service prose or payloads.
    fixture_client_assertion=false
    fixture_session_assertion=false
    fixture_null_variant=false
    while IFS= read -r fixture_line; do
      if [[ "${fixture_line}" == *gkd_secret_service_get_pkcs11_session*assertion* ]]; then
        fixture_client_assertion=true
      fi
      if [[ "${fixture_line}" == *aes_negotiate*assertion* ]]; then
        fixture_session_assertion=true
      fi
      if [[ "${fixture_line}" == *g_variant_new*"(null)"* ]]; then
        fixture_null_variant=true
      fi
    done < "${AI_STP_TEST_SECRET_SERVICE_ROOT}/daemon.log"
    printf 'Vault fixture alive=%s owner_unchanged=%s client_assertion=%s session_assertion=%s null_variant=%s\n' \
      "${fixture_alive}" "${fixture_owner_unchanged}" "${fixture_client_assertion}" \
      "${fixture_session_assertion}" "${fixture_null_variant}"
  fi
  kill "${fixture_pid}" 2>/dev/null || true
  wait "${fixture_pid}" 2>/dev/null || true
  exit "${fixture_status}"
}
trap fixture_cleanup EXIT
for ((attempt=0; attempt<40; attempt++)); do
  kill -0 "${fixture_pid}"
  if [[ "$(gdbus call --session --dest org.freedesktop.DBus \
    --object-path /org/freedesktop/DBus \
    --method org.freedesktop.DBus.NameHasOwner org.freedesktop.secrets)" = '(true,)' ]]; then
    break
  fi
  sleep 0.25
done
test "$(gdbus call --session --dest org.freedesktop.DBus \
  --object-path /org/freedesktop/DBus \
  --method org.freedesktop.DBus.GetConnectionUnixProcessID org.freedesktop.secrets)" \
  = "(uint32 ${fixture_pid},)"
# Owning the bus name does not establish that the existing default collection
# has finished loading and is unlocked. Observe readiness without creating a
# collection or asking the product to display an unlock prompt.
fixture_collection=""
fixture_locked=""
for ((attempt=0; attempt<40; attempt++)); do
  kill -0 "${fixture_pid}"
  fixture_alias="$(timeout 3s gdbus call --session --dest org.freedesktop.secrets \
    --object-path /org/freedesktop/secrets \
    --method org.freedesktop.Secret.Service.ReadAlias default)"
  fixture_collection="${fixture_alias#*\'}"
  fixture_collection="${fixture_collection%%\'*}"
  if [[ "${fixture_collection}" == /org/freedesktop/secrets/collection/* ]]; then
    fixture_locked="$(timeout 3s gdbus call --session --dest org.freedesktop.secrets \
      --object-path "${fixture_collection}" \
      --method org.freedesktop.DBus.Properties.Get org.freedesktop.Secret.Collection Locked)"
    if [[ "${fixture_locked}" == '(<false>,)' ]]; then
      break
    fi
  fi
  sleep 0.25
done
test "${fixture_collection}" != / && test "${fixture_locked}" = '(<false>,)'

if [[ "${fixture_mode}" == desktop ]]; then
  xvfb-run --auto-servernum python .github/scripts/qualify-installed-desktop.py \
    --driver "${RUNNER_TEMP}/ai-stp-webdriver/bin/tauri-driver" \
    --out "${RUNNER_TEMP}/installed-desktop-proof.json"
  exit
fi

if [[ "${fixture_mode}" == corporate-desktop ]]; then
  xvfb-run --auto-servernum uv run --no-sync python -m tests.native_contract.verify_desktop_corporate \
    --driver "${RUNNER_TEMP}/ai-stp-webdriver/bin/tauri-driver" \
    --out "${RUNNER_TEMP}/installed-corporate-desktop-proof.json"
  exit
fi

cd apps/cli
cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- build \
  cargo test --locked --lib \
  identity::secret_service::tests::transport_reuse_stays_with_the_exact_existing_unix_bus \
  -- --ignored --exact
checks=(cargo run --quiet --locked --manifest-path xtask/Cargo.toml -- build \
  cargo test --locked --test enrollments_native --)
listing="$("${checks[@]}" --ignored --list)"
printf '%s\n' "${listing}"
selected=0
while IFS= read -r line; do
  if [[ "${line}" == *': test' ]]; then
    selected=$((selected + 1))
  fi
done <<<"${listing}"
test "${selected}" -eq 3
for ((round=1; round<=fixture_rounds; round++)); do
  printf 'Native vault fixture round %s/%s\n' "${round}" "${fixture_rounds}"
  "${checks[@]}" --ignored
done
