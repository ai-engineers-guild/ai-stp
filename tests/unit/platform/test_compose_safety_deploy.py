"""Static deploy checks: safety-worker, OSV volume, RustFS auth wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.platform

ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _executable(rel: str) -> str:
    """The file without its comments.

    A comment that explains why a path was replaced contains that path, so a
    plain substring check over the whole file matches the explanation and calls
    the fix a regression.
    """
    return "\n".join(line for line in _read(rel).splitlines() if not line.lstrip().startswith("#"))


def test_dev_compose_worker_uses_worker_safety_and_osv_volume() -> None:
    text = _read("docker-compose.dev.yml")
    assert "Dockerfile.worker-safety" in text
    assert "target: worker-safety" in text
    assert "AI_STP_SAFETY_EXTERNAL_CLI" in text
    assert "AI_STP_OSV_OFFLINE_DIR" in text
    assert "OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY" in text
    assert "osv_offline:" in text
    assert "/var/lib/ai_stp/osv" in text
    # RustFS keys aligned with storage defaults
    assert "RUSTFS_ACCESS_KEY: ai_stp" in text
    assert "RUSTFS_SECRET_KEY: ai_stp_dev" in text
    assert "AI_STP_STORAGE_ACCESS_KEY_ID: ai_stp" in text
    assert "9000/health" in text
    assert "minio/health/live" not in _executable("docker-compose.dev.yml")
    assert "rustfs:\n        condition: service_healthy" in text or (
        "rustfs:" in text and "service_healthy" in text
    )


def test_compose_imports_repository_snapshot_before_web() -> None:
    for name in ("docker-compose.prod.yml", "docker-compose.dev.yml"):
        text = _read(name)
        assert "content-import:" in text
        assert "ai_stp_platform.content.importer" in text
        assert "target: content-import" in text
        assert "AI_STP_GIT_COMMIT: ${AI_STP_API_GIT_COMMIT:-" in text
        web_block = text.split("\n  web:\n", 1)[1]
        assert "content-import:" in web_block
        assert "service_completed_successfully" in web_block


def test_content_import_image_bakes_snapshot_then_drops_hub() -> None:
    dockerfile = _read("Dockerfile")
    ignore = _read(".dockerignore")
    snapshot, remainder = dockerfile.split("FROM base AS content-snapshot", 1)
    runtime = remainder.split("FROM base AS content-import", 1)[1]
    assert "COPY docs-user-facing/content /hub" in remainder
    assert "COPY docs-user-facing/content" not in snapshot
    assert "rm -rf /hub" in remainder
    assert "COPY --from=content-snapshot /tmp/content-snapshot.json" in runtime
    assert "test -s /app/content-snapshot.json" in runtime
    assert "COPY docs-user-facing/content" not in runtime
    assert "ARG AI_STP_GIT_COMMIT=" in remainder
    assert "ai_stp_platform.content.snapshot_cli" in remainder
    web_ignore = ignore.split("apps/web\n", 1)[1]
    assert "!docs-user-facing/**" in web_ignore
    assert ignore.find("docs-user-facing") < ignore.find("!docs-user-facing/**")


def test_deploy_scripts_always_rerun_content_import() -> None:
    for name in ("deploy/deploy.sh", "deploy/rollback.sh", "deploy/restore.sh"):
        text = _read(name)
        assert "compose rm -fs content-import" in text
        assert "compose up -d api worker content-import web docs" in text
        assert text.find("compose rm -fs content-import") < text.find(
            "compose up -d api worker content-import web docs"
        )


def test_prod_compose_worker_safety_and_rustfs_health() -> None:
    text = _read("docker-compose.prod.yml")
    assert "Dockerfile.worker-safety" in text
    assert "target: worker-safety" in text
    assert "AI_STP_SAFETY_EXTERNAL_CLI" in text
    assert "OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY" in text
    assert "PyPI,npm,Go,crates.io" in text
    assert "clamav-refresh:" in text
    assert "clamav_db:/var/lib/clamav:ro" in text
    assert "freshclam --datadir=/var/lib/clamav" in text
    assert 'AI_STP_SAFETY_REQUIRE_BWRAP: "1"' in text
    assert "seccomp=unconfined" in text
    assert "apparmor=ai-stp-worker" in text
    worker_block = text.split("\n  worker:\n", 1)[1].split("\n  web:\n", 1)[0]
    worker_runnable = "\n".join(
        line for line in worker_block.splitlines() if not line.lstrip().startswith("#")
    )
    assert "privileged:" not in worker_runnable
    assert "user: root" not in worker_runnable
    assert "apparmor=unconfined" not in worker_runnable
    assert "osv_offline:" in text
    assert "9000/health" in text
    assert "minio/health/live" not in _executable("docker-compose.prod.yml")
    # API/worker wait on storage
    assert "service_healthy" in text


def test_worker_safety_dockerfile_enables_external_cli() -> None:
    text = _read("Dockerfile.worker-safety")
    assert "AI_STP_SAFETY_EXTERNAL_CLI=1" in text
    assert "AI_STP_OSV_OFFLINE_DIR" in text
    assert "OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY" in text
    assert "install_scanners.sh" in text
    assert "snapshot.debian.org/archive/debian/20260822T000000Z" in text
    assert "requirements.lock" in text
    assert text.count("FROM python:3.12-slim@sha256:") == 2
    # Required skill engines + govulncheck (not optional extras).
    assert "golang.org/x/vuln/cmd/govulncheck" in text
    assert "go-tools" in text


def test_install_scanners_requires_govulncheck_and_skill_engines() -> None:
    script = _read("scripts/safety/install_scanners.sh")
    pins = _read("scripts/safety/versions.env")
    assert "SKILL_SCANNER_VERSION" in pins
    assert "cisco-ai-skill-scanner" in pins
    assert "govulncheck missing and go not available" in script
    assert "skill-scanner" in script
    assert "--require-hashes" in script
    assert "SKILL_SCANNER_WHEEL_SHA256" in pins
    # Final gate: required tools must exist or install fails.
    assert "required tool missing after install" in script


def test_seo_enrichment_overlay_routes_alias_through_litellm_not_worker() -> None:
    overlay = _read("docker-compose.seo-enrichment.yml")
    config = _read("deploy/litellm/seo-writer.yaml")
    cliproxy_config = _read("deploy/cliproxy/config.example.yaml")
    default_dev = _read("docker-compose.dev.yml")
    default_prod = _read("docker-compose.prod.yml")
    overlay_exec = _executable("docker-compose.seo-enrichment.yml")
    assert "seo_enrichment" in overlay
    assert "litellm:" in overlay
    assert "cliproxy:" in overlay
    assert "eceasy/cli-proxy-api:" in overlay
    assert "CLIPROXY_API_BASE" in overlay
    assert "CLIPROXY_API_KEY" in overlay
    assert "http://cliproxy:8317/v1" in overlay
    assert "host.docker.internal" not in overlay
    assert "extra_hosts" not in overlay
    assert "8317:8317" not in overlay_exec
    assert "127.0.0.1:51121:51121" in overlay
    assert "AI_STP_SEO_ENRICHMENT_ENABLED: ${AI_STP_SEO_ENRICHMENT_ENABLED:-true}" in overlay
    worker_env = overlay.split("\n  worker:\n", 1)[1]
    assert "CLIPROXY_API_KEY" not in worker_env
    assert "AI_STP_CLIPROXY_API_KEY" not in worker_env
    assert "model_name: seo-writer" in config
    assert "os.environ/CLIPROXY_API_BASE" in config
    assert "os.environ/CLIPROXY_API_KEY" in config
    assert 'alias: "seo-writer"' in cliproxy_config
    assert "litellm:" not in default_dev
    assert "litellm:" not in default_prod
    assert "cliproxy:" not in default_dev
    assert "cliproxy:" not in default_prod
    assert "main-latest" not in overlay
    assert ":latest" not in overlay_exec


def test_no_compose_file_resolves_an_image_by_a_moving_tag() -> None:
    """Every third-party image is pinned, and `:latest` is the one that moved.

    On 2026-08-20 `rustfs/rustfs:latest` resolved to a build whose health
    endpoint had changed. The healthcheck failed 34 times, `api` never left
    `Created` because it waits on a healthy `rustfs`, and the site served 502 —
    a dependency change that arrived looking like a broken deployment, because
    a tag cannot record that it moved (`#394`).

    Asserted across both files: development that resolves a different build
    cannot reproduce what production hit.
    """
    for name in (
        "docker-compose.prod.yml",
        "docker-compose.dev.yml",
        "docker-compose.seo-enrichment.yml",
    ):
        for line in _executable(name).splitlines():
            stripped = line.strip()
            if not stripped.startswith("image:"):
                continue
            reference = stripped.removeprefix("image:").strip()
            if "${" in reference or "@sha256:" in reference:
                continue
            # A major tag is a pin in this repository's sense: `postgres:16`
            # moves within a major and keeps its interface, which is
            # the same discipline `check.yml` uses. `:latest` is the one that
            # crosses majors and changed endpoints under us, and an untagged
            # reference is `:latest` spelled shorter.
            _, _, tag = reference.rpartition(":")
            assert tag and tag != reference, f"{name}: {reference} has no tag"
            assert tag != "latest", f"{name}: {reference} resolves through a moving tag"
