#!/usr/bin/env bash
# Build the production application images of one qualified commit for linux/amd64,
# push them to GHCR by commit tag, and write an inventory of their digests.
#
# The host pulls these exact digests, so production runs the bytes CI built
# instead of rebuilding them on the server.
set -euo pipefail

: "${SOURCE_SHA:?}" "${REGISTRY_PREFIX:?}" "${INVENTORY:?}"
[[ "${PUSH:-true}" == true || "${PUSH:-true}" == false ]] || { echo "PUSH must be true or false" >&2; exit 2; }
[[ "${SOURCE_SHA}" =~ ^[0-9a-f]{40}$ ]] || { echo "SOURCE_SHA must be a full commit" >&2; exit 2; }
[[ "$(git rev-parse HEAD)" == "${SOURCE_SHA}" ]] || { echo "checkout differs from SOURCE_SHA" >&2; exit 2; }

# name|dockerfile|target|build arguments (space separated KEY=VALUE)
images=(
  "api|deploy/docker/Dockerfile.app|api|"
  "worker|deploy/docker/Dockerfile.app|worker|"
  "worker-safety|deploy/docker/Dockerfile.app|worker-safety|"
  "content-import|deploy/docker/Dockerfile.app|content-import|"
  "web|deploy/docker/Dockerfile.web|prod|NEXT_PUBLIC_APP_URL=${WEB_APP_URL:?} AI_STP_WEB_PROFILE=public_saas NEXT_PUBLIC_ANALYTICS_ENABLED=${WEB_ANALYTICS_ENABLED:-true} NEXT_PUBLIC_GA_MEASUREMENT_ID=${WEB_GA_MEASUREMENT_ID:-} NEXT_PUBLIC_YANDEX_METRIKA_COUNTER_ID=${WEB_YANDEX_METRIKA_COUNTER_ID:-} NEXT_PUBLIC_COOKIE_CONSENT_ENABLED=${WEB_COOKIE_CONSENT_ENABLED:-true}"
  "docs|deploy/docker/Dockerfile.docs|prod|AI_STP_USER_DOCS_SITE_URL=${DOCS_URL:?}"
)

work=$(mktemp -d)
entries=()
for image in "${images[@]}"; do
  IFS='|' read -r name dockerfile target arguments <<< "${image}"
  reference="${REGISTRY_PREFIX}/${name}:${SOURCE_SHA}"
  build_args=()
  for argument in ${arguments}; do build_args+=(--build-arg "${argument}"); done
  docker buildx build \
    --platform linux/amd64 \
    --file "${dockerfile}" \
    --target "${target}" \
    "${build_args[@]}" \
    --label "org.opencontainers.image.revision=${SOURCE_SHA}" \
    --label "org.opencontainers.image.source=https://github.com/ai-engineers-guild/ai-stp" \
    --provenance=mode=min \
    --sbom=true \
    --metadata-file "${work}/${name}.json" \
    --tag "${reference}" \
    --output "type=image,push=${PUSH:-true}" \
    .
  digest=$(jq -r '."containerimage.digest"' "${work}/${name}.json")
  [[ "${digest}" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "no digest for ${name}" >&2; exit 1; }
  entries+=("$(jq -cn --arg name "${name}" --arg target "${target}" --arg ref "${reference}" \
    --arg digest "${digest}" '{name:$name, target:$target, reference:$ref, digest:$digest, platform:"linux/amd64"}')")
  echo "built ${name} ${digest}"
done

printf '%s\n' "${entries[@]}" | jq -s \
  --arg sha "${SOURCE_SHA}" --arg run "${GITHUB_RUN_ID:-}" --arg attempt "${GITHUB_RUN_ATTEMPT:-}" \
  '{schema_version: 1, source_commit: $sha, run_id: $run, run_attempt: $attempt, images: .}' \
  > "${INVENTORY}"
cat "${INVENTORY}"
