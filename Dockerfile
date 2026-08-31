# Multi-stage image for the platform apps (SPEC-019, ADR-0040).
# Base installs the locked workspace; api and worker are minimal final stages.

# Pinned by digest and named by tag, for the same reason the `uv` line below
# gives and against the same hazard: `python:3.12-slim` is republished whenever
# its Debian base takes a security update, and a republished tag leaves no
# trace at all — unlike a stale pin, which shows up as a version going
# backwards. Two builds of one commit could resolve different interpreters, and
# the image would not be reproducible from the commit that `SPEC-024` requires.
#
# The argument was already written two lines further down and applied only to
# `uv`. The base underneath it was the thing not pinned.
FROM python:3.12-slim@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217 AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"
# Pinned by digest and named by version. The tag alone used to be `:0.9`,
# which moves: two builds of the same commit could resolve different `uv`
# releases, so the image was not reproducible from the commit — which
# `SPEC-024` requires and `dependency-policy.md` states as exact versions
# rather than moving references. The version also now matches the one every
# gate installs, so what production resolves the lockfile with is what CI
# proved it with; a contract test holds the two together.
COPY --from=ghcr.io/astral-sh/uv:0.12.1@sha256:cf4eedcaa81655197f625739489effcbe71b61ceb1506f332c3facae5deceded /uv /bin/uv
WORKDIR /app

# Manifests first for layer caching, then sources.
# apps/web is excluded via .dockerignore (Node image has its own context).
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY apps/api ./apps/api
COPY apps/cli ./apps/cli
COPY apps/platform ./apps/platform
COPY apps/worker ./apps/worker
COPY docs-user-facing/legal ./docs-user-facing/legal
RUN uv sync --locked --no-dev --all-packages

COPY migrations ./migrations
COPY alembic.ini ./

# Non-root runtime user; the log volume is mounted at /var/log/ai_stp.
# chown only runtime paths — never a multi-hundred-MB tree (was the hung step).
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/log/ai_stp \
    && chown -R appuser:appuser /app /var/log/ai_stp
USER appuser

FROM base AS api
EXPOSE 8000
CMD ["python", "-m", "ai_stp_api"]

FROM base AS worker
# Safety suite: in-proc engines always run. External CLIs stay off here.
# Production scanner image: Dockerfile.worker-safety (pins + AI_STP_SAFETY_EXTERNAL_CLI=1).
ENV AI_STP_SAFETY_EXTERNAL_CLI=0 \
    AI_STP_SAFETY_SANDBOX=auto \
    AI_STP_OSV_OFFLINE_DIR=/var/lib/ai_stp/osv \
    OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=/var/lib/ai_stp/osv \
    AI_STP_OSV_MAX_AGE_HOURS=36
CMD ["python", "-m", "ai_stp_worker"]

# Bake the hub snapshot in a throwaway stage so the runtime image has no
# checkout. The importer POSTs this file; it never reads Markdown on the host.
# Bake fails closed on an empty COPY (a dockerignore miss would otherwise
# unpublish every repository article) and on the zero SHA placeholder.
FROM base AS content-snapshot
USER root
COPY docs-user-facing/content /hub
ARG AI_STP_GIT_COMMIT=0000000000000000000000000000000000000000
RUN python -m ai_stp_platform.content.snapshot_cli \
      --hub /hub \
      --commit "$AI_STP_GIT_COMMIT" \
      --out /tmp/content-snapshot.json \
    && rm -rf /hub

FROM base AS content-import
USER root
COPY --from=content-snapshot /tmp/content-snapshot.json /app/content-snapshot.json
RUN test -s /app/content-snapshot.json \
    && chown appuser:appuser /app/content-snapshot.json
USER appuser
ENV AI_STP_CONTENT_SNAPSHOT=/app/content-snapshot.json
CMD ["python", "-m", "ai_stp_platform.content.importer"]
