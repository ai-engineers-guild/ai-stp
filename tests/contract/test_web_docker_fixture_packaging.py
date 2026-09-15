"""The production web context carries only the canonical mock fixture it imports."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = "packages/contracts/src/ai_stp_contracts/fixtures/v1/corporate-overview.json"


def test_web_production_context_allows_and_copies_the_canonical_fixture() -> None:
    source = (ROOT / "apps/web/src/lib/api/mock-corporate.ts").read_text(encoding="utf-8")
    dockerfile = (ROOT / "apps/web/Dockerfile.prod").read_text(encoding="utf-8")
    dockerignore = (ROOT / "apps/web/Dockerfile.prod.dockerignore").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8")

    assert f"../../../../../{FIXTURE}" in source
    assert f"COPY {FIXTURE} /{FIXTURE}" in dockerfile
    rules = [line.strip() for line in dockerignore.splitlines() if line.strip()]
    assert [line for line in rules if line.startswith(("!apps/", "apps/**"))] == [
        "!apps/",
        "!apps/web/",
        "apps/**",
        "!apps/web/**",
    ]
    assert [line for line in rules if line.startswith(("!packages/", "packages/**"))] == [
        "!packages/",
        "!packages/contracts/",
        "!packages/contracts/src/",
        "!packages/contracts/src/ai_stp_contracts/",
        "!packages/contracts/src/ai_stp_contracts/fixtures/",
        "!packages/contracts/src/ai_stp_contracts/fixtures/v1/",
        "packages/**",
        f"!{FIXTURE}",
    ]
    dev_mount = f"- ./{FIXTURE}:/{FIXTURE}:ro"
    assert compose.count(dev_mount) == 1
    assert "- ./packages:/packages" not in compose
