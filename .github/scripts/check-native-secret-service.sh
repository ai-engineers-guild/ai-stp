#!/usr/bin/env bash
# This fixture runs only on a disposable GitHub Linux runner, never a user's bus.
set -euo pipefail
test "${GITHUB_ACTIONS:-}" = true
test "${RUNNER_OS:-}" = Linux
test -n "${RUNNER_TEMP:-}"

if [[ "${1:-}" != --inside-fixture ]]; then
  test "$#" -eq 0
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
  exec dbus-run-session -- bash "$0" --inside-fixture
fi

test "$#" -eq 1
test -d "${AI_STP_TEST_SECRET_SERVICE_ROOT}"
test "${AI_STP_TEST_SECRET_SERVICE}" = isolated

# Only synthetic credentials live here. No SSH/PKCS11 component is started.
printf '%s' 'ai-stp-disposable-ci-fixture' | gnome-keyring-daemon \
  --foreground --components=secrets --unlock \
  --control-directory="${AI_STP_TEST_SECRET_SERVICE_ROOT}/control" \
  >"${AI_STP_TEST_SECRET_SERVICE_ROOT}/daemon.log" 2>&1 &
fixture_pid=$!
trap 'kill "${fixture_pid}" 2>/dev/null || true; wait "${fixture_pid}" 2>/dev/null || true' EXIT
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
gdbus call --session --dest org.freedesktop.secrets \
  --object-path /org/freedesktop/secrets \
  --method org.freedesktop.Secret.Service.ReadAlias default >/dev/null

cd apps/cli
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
test "${selected}" -eq 2
"${checks[@]}" --ignored
