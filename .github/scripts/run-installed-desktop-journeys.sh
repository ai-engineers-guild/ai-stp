#!/usr/bin/env bash
# Run three actual installed personal journeys.
set -euo pipefail
for round in 1 2 3; do
  printf 'Installed Desktop journey %s/3\n' "${round}"
  bash .github/scripts/check-native-secret-service.sh --installed-desktop
  mv "${RUNNER_TEMP}/installed-desktop-proof.json" \
    "${RUNNER_TEMP}/installed-desktop-proof-${round}.json"
done
