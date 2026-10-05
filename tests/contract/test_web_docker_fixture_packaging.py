"""The web image is built from apps/web and user docs alone.

The corporate overview mock used to import its fixture JSON from
packages/contracts, so the image, its build context and the dev mount each
carried that one file. The fixture now reaches the app as a generated
projection under apps/web (`ai_stp_contracts.web_projections`), and nothing
outside apps/web and docs-user-facing enters the web context.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_web_context_carries_no_contract_package_files() -> None:
    mock = (ROOT / "apps/web/src/lib/api/mock-corporate.ts").read_text(encoding="utf-8")
    fixture = (ROOT / "apps/web/src/mocks/corporate-overview-fixture.ts").read_text(
        encoding="utf-8"
    )
    dockerfile = (ROOT / "deploy/docker/Dockerfile.web").read_text(encoding="utf-8")
    dockerignore = (ROOT / "deploy/docker/Dockerfile.web.dockerignore").read_text(encoding="utf-8")
    compose = (ROOT / "deploy/compose.dev.yml").read_text(encoding="utf-8")

    assert "@/mocks/corporate-overview-fixture" in mock
    assert '"@/lib/generated/corporate-overview-fixture"' in fixture
    assert (ROOT / "apps/web/src/lib/generated/corporate-overview-fixture.ts").is_file()

    rules = [line.strip() for line in dockerignore.splitlines() if line.strip()]
    assert rules[0] == "*"
    assert [line for line in rules if line.startswith("!") and "/" in line] == [
        "!apps/",
        "!apps/web/",
        "!apps/web/**",
        "!docs-user-facing/",
        "!docs-user-facing/**",
    ]
    assert "packages/" not in dockerfile
    assert "../packages" not in compose
