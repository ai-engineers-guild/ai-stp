#!/usr/bin/env bash
# Read-only admission shared by the two explicit client release workflows.
set -euo pipefail
test -n "${REPOSITORY}"
[[ "${HEAD_SHA}" =~ ^[0-9a-f]{40}$ ]]
test "$(gh api "repos/${REPOSITORY}/git/ref/heads/main" --jq .object.sha)" = "${HEAD_SHA}"
runs="$(gh api "repos/${REPOSITORY}/actions/runs?head_sha=${HEAD_SHA}&event=push&branch=main&per_page=100")"
source="$(jq -ce --arg repo "${REPOSITORY}" --arg sha "${HEAD_SHA}" '
  select(.total_count == (.workflow_runs | length)) |
  [.workflow_runs[] | select(
    .path == ".github/workflows/check.yml" and
    .head_sha == $sha and .event == "push" and .head_branch == "main"
  )] | select(length > 0) | max_by(.id) |
  select(.repository.full_name == $repo and .head_repository.full_name == $repo and
    .status == "completed" and .conclusion == "success")
' <<< "${runs}")"
source_id="$(jq -r .id <<< "${source}")"
attempt="$(jq -r .run_attempt <<< "${source}")"
jobs="$(gh api "repos/${REPOSITORY}/actions/runs/${source_id}/attempts/${attempt}/jobs?per_page=100")"
jq -e '
  .total_count == (.jobs | length) and
  ([.jobs[] | select(.name == "qualification")] |
    length == 1 and all(.[]; .status == "completed" and .conclusion == "success"))
' <<< "${jobs}" >/dev/null
printf 'Qualified client source %s; main run %s attempt %s\n' \
  "${HEAD_SHA}" "${source_id}" "${attempt}"
