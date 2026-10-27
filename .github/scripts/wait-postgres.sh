#!/usr/bin/env bash
set -euo pipefail

test "$#" -eq 1
postgres_container="$1"

ready() {
  # The image's initialization server accepts Unix sockets without TCP.
  docker exec "${postgres_container}" pg_isready \
    -h 127.0.0.1 -p 5432 -U ai_stp -d ai_stp
}

for ((attempt=0; attempt<30; attempt++)); do
  if ready; then
    exit 0
  fi
  sleep 1
done

if ready; then
  exit 0
else
  postgres_status=$?
fi

# Both consumers call this before fixture migrations or application traffic.
# Preserve startup evidence before their owned-container cleanup trap runs.
docker logs --tail 80 "${postgres_container}" >&2 || true
exit "${postgres_status}"
