#!/usr/bin/env bash
# Qualify native ownership and corporate HTTP journeys.
set -euo pipefail
fixture_postgres="$(docker run --detach --name ai-stp-native-ownership \
  -e POSTGRES_USER=ai_stp -e POSTGRES_PASSWORD=ai_stp_dev -e POSTGRES_DB=ai_stp \
  -p 127.0.0.1:15432:5432 \
  docker.io/library/postgres:18@sha256:5a5a84b19854a9ffaa54082c166ff4ec27473a361e496e5ea167f298f2da9722)"
trap 'docker rm --force "${fixture_postgres}" >/dev/null' EXIT
bash .github/scripts/wait-postgres.sh "${fixture_postgres}"
uv sync --locked
uv run --locked python -m tests.native_contract.verify_ownership \
  "${AI_STP_TEST_CLI_BINARY}"
uv run --locked python -m tests.native_contract.verify_corporate \
  "${AI_STP_TEST_CLI_BINARY}"
