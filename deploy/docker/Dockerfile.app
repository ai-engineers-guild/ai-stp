# Multi-stage image for the platform apps (SPEC-019, ADR-0040).
# Base installs the locked workspace; api, worker, content-import and
# worker-safety are minimal final stages over it. One file, one `base` —
# the scanner stage used to re-declare it as `app-base` in a second
# Dockerfile because Docker cannot `FROM` a stage in another file.

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
COPY --from=ghcr.io/astral-sh/uv:0.12.18@sha256:3adc3706091ce7c2fe595e669628caedd6d951551b92b258b7e7dbe06d9440bc /uv /bin/uv
RUN useradd --create-home --uid 10001 appuser \
    && mkdir /app \
    && chown appuser:appuser /app
WORKDIR /app

# Manifests first for layer caching, then sources.
# apps/web is excluded via .dockerignore (Node image has its own context).
COPY --chown=appuser:appuser pyproject.toml uv.lock ./
COPY --chown=appuser:appuser packages ./packages
COPY --chown=appuser:appuser apps/api ./apps/api
COPY --chown=appuser:appuser apps/cli ./apps/cli
COPY --chown=appuser:appuser apps/platform ./apps/platform
COPY --chown=appuser:appuser apps/worker ./apps/worker
COPY --chown=appuser:appuser docs-user-facing/legal ./docs-user-facing/legal
USER appuser
RUN uv sync --locked --no-dev --all-packages --no-cache

# Non-root runtime user; the log volume is mounted at /var/log/ai_stp.
# chown only runtime paths — never a multi-hundred-MB tree (was the hung step).
USER root
RUN mkdir -p /var/log/ai_stp \
    && chown appuser:appuser /var/log/ai_stp
USER appuser

FROM base AS worker
COPY --chown=appuser:appuser migrations ./migrations
COPY --chown=appuser:appuser alembic.ini ./
# Safety suite: in-proc engines always run. External CLIs stay off here;
# the worker-safety stage below turns them on. Compose runs this target for
# one-shot jobs (migrate, seed); the worker service itself is worker-safety.
ENV AI_STP_SAFETY_EXTERNAL_CLI=0 \
    AI_STP_SAFETY_SANDBOX=auto \
    AI_STP_OSV_OFFLINE_DIR=/var/lib/ai_stp/osv \
    OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=/var/lib/ai_stp/osv \
    AI_STP_OSV_MAX_AGE_HOURS=36
CMD ["python", "-m", "ai_stp_worker"]

FROM base AS api
USER root
RUN sed -i \
      -e 's|http://deb.debian.org/debian-security|https://snapshot.debian.org/archive/debian-security/20260927T000000Z|g' \
      -e 's|http://deb.debian.org/debian|https://snapshot.debian.org/archive/debian/20260927T000000Z|g' \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends ffmpeg=7:7.1.5-0+deb13u1 \
    && rm -r -f /var/lib/apt/lists/*
USER appuser
COPY --chown=appuser:appuser migrations ./migrations
COPY --chown=appuser:appuser alembic.ini ./
EXPOSE 8000
CMD ["python", "-m", "ai_stp_api"]

# Content is mounted into the one-shot importer at runtime. Local Compose mounts
# the checkout so it can resolve HEAD without a host-side build argument;
# production deploy passes the exact recorded commit to the importer.
FROM base AS content-import
USER appuser
ENV AI_STP_CONTENT_SNAPSHOT=/tmp/content-snapshot.json \
    AI_STP_CONTENT_HUB=/content
CMD ["python", "-m", "ai_stp_platform.content.importer"]

# -----------------------------------------------------------------------------
# Safety scanner toolchain. `tools` is an intermediate stage that never runs
# as a service; only its copied artifacts reach the final non-root stage.
# -----------------------------------------------------------------------------

# go-tools: build govulncheck only (no Go toolchain in the final image)
FROM golang:1.27-bookworm@sha256:69a7b9788769bec032d238959b61854e9ae87f57be9029ec04e9885fabf99195 AS go-tools
ARG GOVULNCHECK_VERSION=v1.1.4
RUN GOBIN=/out CGO_ENABLED=0 go install \
      "golang.org/x/vuln/cmd/govulncheck@${GOVULNCHECK_VERSION}" \
    && test -x /out/govulncheck

# tools: install OS packages + pinned scanner binaries. FROM base so the
# installer resolves with the same pinned uv the workspace was synced by.
FROM base AS tools
# `tools` is intermediate and never runs as a service; it ends as root and
# only its copied artifacts reach the non-root worker-safety stage.
# hadolint ignore=DL3002
USER root
ENV DEBIAN_FRONTEND=noninteractive \
    SAFETY_BIN_PREFIX=/opt/safety-bin \
    SAFETY_PIP_VENV=/opt/safety-venv \
    PATH="/opt/safety-bin:${PATH}"

RUN sed -i \
      -e 's|http://deb.debian.org/debian-security|https://snapshot.debian.org/archive/debian-security/20260927T000000Z|g' \
      -e 's|http://deb.debian.org/debian|https://snapshot.debian.org/archive/debian/20260927T000000Z|g' \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends \
      ca-certificates=20250419 \
      curl=8.14.1-2+deb13u5 \
      git=1:2.47.3-0+deb13u1 \
      xz-utils=5.8.1-1+deb13u1 \
      bubblewrap=0.12.0-1~deb13u1 \
      clamav=1.4.3+dfsg-1 \
      clamav-daemon=1.4.3+dfsg-1 \
      yara=4.5.2-1 \
    && rm -rf /var/lib/apt/lists/*

# Prebuilt scanner binaries + Python skill engines. govulncheck comes from
# go-tools (no golang-go apt package in this stage — keeps the image lean
# and avoids OOM).
COPY --from=go-tools /out/govulncheck /opt/safety-bin/govulncheck
COPY scripts/safety/versions.env /tmp/safety/versions.env
COPY scripts/safety/requirements.lock /tmp/safety/requirements.lock
COPY scripts/safety/install_scanners.sh /tmp/safety/install_scanners.sh
RUN chmod +x /tmp/safety/install_scanners.sh /opt/safety-bin/govulncheck \
    && /tmp/safety/install_scanners.sh \
    && rm -rf /tmp/safety /root/.cache /tmp/gopath /tmp/gocache /tmp/gomodcache \
    && mkdir -p /var/lib/ai_stp/osv \
    && echo "placeholder" > /var/lib/ai_stp/osv/README

# -----------------------------------------------------------------------------
# worker-safety: worker + scanners. Sets AI_STP_SAFETY_EXTERNAL_CLI=1 so
# adapters may invoke installed tools. OSV offline DB is mounted/refreshed
# at /var/lib/ai_stp/osv (see scripts/safety). Production also uses this
# image for the osv-refresh and clamav-refresh services.
# -----------------------------------------------------------------------------
FROM worker AS worker-safety
USER root
RUN sed -i \
      -e 's|http://deb.debian.org/debian-security|https://snapshot.debian.org/archive/debian-security/20260927T000000Z|g' \
      -e 's|http://deb.debian.org/debian|https://snapshot.debian.org/archive/debian/20260927T000000Z|g' \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends \
      ca-certificates=20250419 \
      curl=8.14.1-2+deb13u5 \
      bubblewrap=0.12.0-1~deb13u1 \
      clamav=1.4.3+dfsg-1 \
      yara=4.5.2-1 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/lib/ai_stp/osv \
    && chown appuser:appuser /var/lib/ai_stp /var/lib/ai_stp/osv

COPY --chown=appuser:appuser --from=tools /opt/safety-bin /opt/safety-bin
COPY --chown=appuser:appuser --from=tools /opt/safety-venv /opt/safety-venv
COPY --chown=appuser:appuser scripts/safety /opt/ai_stp/scripts/safety
RUN chmod +x /opt/ai_stp/scripts/safety/*.sh

# safety-bin holds native CLIs + symlinks to bandit/pip-audit in safety-venv.
# Do not put safety-venv/bin ahead of the app venv (would shadow `python`);
# /app/.venv/bin is already first on the inherited PATH.
ENV PATH="/opt/safety-bin:${PATH}" \
    AI_STP_SAFETY_EXTERNAL_CLI=1 \
    AI_STP_SAFETY_SANDBOX=auto \
    AI_STP_OSV_OFFLINE_DIR=/var/lib/ai_stp/osv \
    OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=/var/lib/ai_stp/osv \
    AI_STP_OSV_MAX_AGE_HOURS=36

USER appuser
