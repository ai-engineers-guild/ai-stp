#!/usr/bin/env bash
# Bounded DNS evidence only; package installation remains the acceptance gate.
set -euo pipefail

stage="${1:-}"
case "${stage}" in
  before-native | before-index) ;;
  *) exit 64 ;;
esac

for owner in runner apt; do
  command_prefix=()
  if [[ "${owner}" == apt ]]; then
    command_prefix=(sudo -n -u _apt)
  fi
  if "${command_prefix[@]}" test -r /etc/resolv.conf; then
    readable=yes
  else
    readable=no
  fi
  printf 'native-package-network stage=%s owner=%s resolver_readable=%s\n' \
    "${stage}" "${owner}" "${readable}"
  for host in github.com azure.archive.ubuntu.com archive.ubuntu.com security.ubuntu.com; do
    if "${command_prefix[@]}" timeout --signal=TERM --kill-after=1s 5s \
      getent ahosts "${host}" >/dev/null 2>&1; then
      result=resolved
    else
      code=$?
      case "${code}" in
        124 | 137) result=deadline ;;
        2) result=lookup_failed ;;
        *) result=probe_failed ;;
      esac
    fi
    printf 'native-package-network stage=%s owner=%s host=%s result=%s\n' \
      "${stage}" "${owner}" "${host}" "${result}"
  done
done
