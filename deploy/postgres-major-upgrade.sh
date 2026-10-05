#!/usr/bin/env bash
# PostgreSQL major upgrade by dump and restore (SPEC-024 REQ-2410). deploy.sh
# runs it before the stack starts; it does nothing unless the postgres
# container still mounts the pre-18 data directory.
#
# Images from 18 on keep data under /var/lib/postgresql/<major>/docker, so a
# later major can use `pg_upgrade --link` inside one volume. The 16 cluster
# lives in volume `pgdata` at /var/lib/postgresql/data; the 18 service mounts
# `pgdata18` at /var/lib/postgresql. With the writers stopped, this copies the
# database into a one-off container of the new service and compares every
# table's row count; deploy.sh's ordinary bring-up then replaces the serving
# container. `pgdata` is never written or removed: it is the rollback copy
# (docs/operations/runbooks/database-migration.md).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

LEGACY_DATA=/var/lib/postgresql/data
FAILED="${AI_STP_STATE_DIR}/postgres-upgrade-failed"
COPIED="${AI_STP_STATE_DIR}/postgres-upgrade-copied"
WRITERS=(api worker content-import)

require_cmd docker
require_cmd sha256sum
ensure_state_dir

# A failed copy restarts the old writers, so the previous release keeps
# serving. Retrying on every pull-deploy tick would take it down once a
# minute; an operator reads the log, fixes the cause and removes this file.
[[ ! -f "${FAILED}" ]] || die "postgres_upgrade_failed_previously remove=${FAILED}"

legacy="$(compose ps -q --all postgres | head -n1)"
if [[ -z "${legacy}" ]]; then
  log info "postgres_upgrade_skipped reason=no_container"
  exit 0
fi
legacy_volume="$(docker inspect --format \
  '{{range .Mounts}}{{if eq .Destination "'"${LEGACY_DATA}"'"}}{{.Name}}{{end}}{{end}}' "${legacy}")"
if [[ -z "${legacy_volume}" ]]; then
  rm -f "${COPIED}"
  log info "postgres_upgrade_skipped reason=current_layout"
  exit 0
fi
project="$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "${legacy}")"
target_volume="${project}_pgdata18"
copy="${project}-postgres-upgrade"

# The copy is current only while the container it was taken from has not run
# since: a rollback to 16 recreates that container, and its later writes must
# be copied again rather than dropped.
legacy_identity() {
  docker inspect --format '{{.Id}} {{.State.StartedAt}} {{.State.Running}}' "${legacy}"
}

if [[ -f "${COPIED}" && "$(cat "${COPIED}")" == "$(legacy_identity)" ]]; then
  log info "postgres_upgrade_skipped reason=copy_verified"
  exit 0
fi

wait_ready() {
  # TCP, not the socket: the image entrypoint first runs a socket-only server
  # to initialize the cluster, and that one answers before the real one starts.
  local container="$1"
  local attempt
  for attempt in $(seq 1 60); do
    if docker exec "${container}" sh -c \
      'pg_isready -q -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'; then
      return 0
    fi
    sleep 2
  done
  die "postgres_not_ready container=${container} attempts=${attempt}"
}

row_counts() {
  # One line per table, `schema.table|rows`; the superuser reads past RLS.
  docker exec -i "$1" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -AtX -v ON_ERROR_STOP=1' <<'SQL'
SELECT format('SELECT %L, count(*) FROM %I.%I', n.nspname || '.' || c.relname, n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
ORDER BY 1 \gexec
SQL
}

copying=0
on_exit() {
  local status=$?
  if ((status != 0 && copying)); then
    log error "postgres_upgrade_failed restoring_previous_release"
    docker rm -f "${copy}" >/dev/null 2>&1 || true
    docker start "${legacy}" >/dev/null 2>&1 || true
    compose start "${WRITERS[@]}" >/dev/null 2>&1 || true
    : >"${FAILED}"
  fi
}
trap on_exit EXIT

log info "postgres_upgrade_start legacy_volume=${legacy_volume} target_volume=${target_volume}"
# Pulled while the writers still serve: the image is the slow part.
compose pull --quiet postgres
copying=1
rm -f "${COPIED}"
compose stop "${WRITERS[@]}" >/dev/null
# Whatever the target holds is an interrupted attempt: no container serves it
# until this run records a verified copy.
docker rm -f "${copy}" >/dev/null 2>&1 || true
docker volume rm "${target_volume}" >/dev/null 2>&1 || true
docker start "${legacy}" >/dev/null
wait_ready "${legacy}"
compose run -d --no-deps --name "${copy}" postgres >/dev/null
wait_ready "${copy}"

docker exec "${legacy}" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
  | docker exec -i "${copy}" sh -c \
    'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --exit-on-error --single-transaction'
log info "postgres_upgrade_restored"

legacy_counts="$(row_counts "${legacy}")"
copy_counts="$(row_counts "${copy}")"
if [[ "${legacy_counts}" != "${copy_counts}" ]]; then
  die "postgres_upgrade_row_counts_differ"
fi
log info "postgres_upgrade_verified tables=$(wc -l <<<"${copy_counts}")"

docker stop "${copy}" >/dev/null
docker rm "${copy}" >/dev/null
docker stop "${legacy}" >/dev/null
legacy_identity >"${COPIED}"
copying=0
log info "postgres_upgrade_copy_complete"
