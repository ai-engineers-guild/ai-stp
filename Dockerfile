# Multi-stage image for the platform apps (SPEC-019, ADR-0040).
# Base installs the locked workspace; api and worker are minimal final stages.

FROM python:3.12-slim AS base
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
