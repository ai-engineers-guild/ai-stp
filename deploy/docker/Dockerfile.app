# Locked application and static scanner runtimes.
FROM python:3.14.10-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS base
ARG DEBIAN_SNAPSHOT=20261111T000000Z
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:${PATH}"
COPY --from=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 /uv /bin/uv
RUN sed -i \
      -e "s|http://deb.debian.org/debian-security|https://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}|g" \
      -e "s|http://deb.debian.org/debian|https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}|g" \
      /etc/apt/sources.list.d/debian.sources \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app /var/log/ai_stp \
    && chown appuser:appuser /app /var/log/ai_stp
WORKDIR /app

COPY --chown=appuser:appuser pyproject.toml uv.lock ./
COPY --chown=appuser:appuser packages ./packages
COPY --chown=appuser:appuser apps/api ./apps/api
COPY --chown=appuser:appuser apps/platform ./apps/platform
COPY --chown=appuser:appuser apps/worker ./apps/worker
COPY --chown=appuser:appuser docs-user-facing/legal ./docs-user-facing/legal
USER appuser
RUN --mount=type=cache,target=/home/appuser/.cache/uv,uid=10001,gid=10001 \
    uv sync --locked --no-dev --all-packages

FROM base AS worker
COPY --chown=appuser:appuser migrations ./migrations
COPY --chown=appuser:appuser alembic.ini ./
ENV AI_STP_SAFETY_EXTERNAL_CLI=0 \
    AI_STP_SAFETY_SANDBOX=auto \
    AI_STP_OSV_OFFLINE_DIR=/var/lib/ai_stp/osv \
    OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=/var/lib/ai_stp/osv \
    AI_STP_OSV_MAX_AGE_HOURS=36
CMD ["python", "-m", "ai_stp_worker"]

FROM base AS api
USER root
RUN apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends ffmpeg=7:7.1.5-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*
USER appuser
COPY --chown=appuser:appuser migrations ./migrations
COPY --chown=appuser:appuser alembic.ini ./
EXPOSE 8000
CMD ["python", "-m", "ai_stp_api"]

FROM base AS content-import
USER appuser
ENV AI_STP_CONTENT_SNAPSHOT=/tmp/content-snapshot.json \
    AI_STP_CONTENT_HUB=/content
CMD ["python", "-m", "ai_stp_platform.content.importer"]

# The worker and tool installer share the same distro package closure.
FROM worker AS scanner-runtime
USER root
RUN apt-get -o Acquire::Check-Valid-Until=false update \
    && test -s /etc/ssl/certs/ca-certificates.crt \
    && apt-get install -y --no-install-recommends \
      curl=8.14.1-2+deb13u7 \
      bubblewrap=0.12.0-1~deb13u1 \
      clamav=1.4.3+dfsg-1 \
      yara=4.5.2-1 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/lib/ai_stp/osv \
    && chown appuser:appuser /var/lib/ai_stp /var/lib/ai_stp/osv
USER appuser

FROM golang:1.27.3-trixie@sha256:af1bfc2614ebb1dbd31af514b78740fd678850e76498762b425ecee4c5c6ea80 AS go-tools
COPY scripts/safety/versions.env /tmp/safety-versions.env
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    . /tmp/safety-versions.env \
    && GOBIN=/out CGO_ENABLED=0 go install "golang.org/x/vuln/cmd/govulncheck@${GOVULNCHECK_VERSION}" \
    && test -x /out/govulncheck

# Only scanner executables and their locked Python environments reach the final stage.
FROM scanner-runtime AS tools
# hadolint ignore=DL3002
USER root
ENV DEBIAN_FRONTEND=noninteractive \
    SAFETY_BIN_PREFIX=/opt/safety-bin \
    SAFETY_PIP_VENV=/opt/safety-venv \
    SAFETY_CISCO_ROOT=/opt/safety-cisco \
    PATH="/opt/safety-bin:${PATH}"
RUN apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends xz-utils=5.8.1-1+deb13u2 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=go-tools /out/govulncheck /opt/safety-bin/govulncheck
COPY scripts/safety/versions.env scripts/safety/requirements.lock scripts/safety/install_scanners.sh /tmp/safety/
COPY scripts/safety/cisco /opt/safety-cisco
RUN --mount=type=cache,target=/root/.cache/uv \
    chmod +x /tmp/safety/install_scanners.sh /opt/safety-bin/govulncheck \
    && /tmp/safety/install_scanners.sh \
    && rm -rf /tmp/safety

FROM scanner-runtime AS worker-safety
USER root
COPY --chown=appuser:appuser --from=tools /opt/safety-bin /opt/safety-bin
COPY --chown=appuser:appuser --from=tools /opt/safety-venv /opt/safety-venv
COPY --chown=appuser:appuser --from=tools /opt/safety-cisco /opt/safety-cisco
COPY --chown=appuser:appuser scripts/safety /opt/ai_stp/scripts/safety
RUN chmod +x /opt/ai_stp/scripts/safety/*.sh
ENV PATH="/opt/safety-bin:${PATH}" \
    AI_STP_SAFETY_EXTERNAL_CLI=1
USER appuser
