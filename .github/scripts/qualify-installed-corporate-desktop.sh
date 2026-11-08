#!/usr/bin/env bash
# Qualify installed corporate recovery against the actual API.
set -euo pipefail
fixture_postgres="$(docker run --detach --name ai-stp-installed-corporate \
  -e POSTGRES_USER=ai_stp -e POSTGRES_PASSWORD=ai_stp_dev -e POSTGRES_DB=ai_stp \
  -p 127.0.0.1:15434:5432 \
  docker.io/library/postgres:18@sha256:5a5a84b19854a9ffaa54082c166ff4ec27473a361e496e5ea167f298f2da9722)"
trap 'docker rm --force "${fixture_postgres}" >/dev/null' EXIT
bash .github/scripts/wait-postgres.sh "${fixture_postgres}"
uv sync --locked
bash .github/scripts/check-native-secret-service.sh --installed-corporate-desktop
