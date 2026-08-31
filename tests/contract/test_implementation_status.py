"""The roadmap cannot send a later agent back to already-shipped CLI phases."""

import tomllib
from pathlib import Path

from ai_stp_cli.commands.machine_help import registry

ROADMAP = Path(__file__).parents[2] / "docs" / "engineering" / "implementation-roadmap.md"
ROOT = Path(__file__).parents[2]
PUBLISHABLE_PROJECTS = (
    ROOT / "packages" / "foundation" / "pyproject.toml",
    ROOT / "packages" / "passports" / "pyproject.toml",
    ROOT / "packages" / "assurance" / "pyproject.toml",
    ROOT / "packages" / "contracts" / "pyproject.toml",
    ROOT / "apps" / "cli" / "pyproject.toml",
)

IMPLEMENTED_COMMAND_EVIDENCE = {
    ("config", "validate"),
    ("passport", "developer", "init"),
    ("sync", "preview"),
    ("doctor",),
    ("toolchain", "install"),
    ("project", "index"),
    ("project", "symbols"),
    ("component", "adopt"),
    ("component", "version", "release"),
    ("consent", "allow"),
    ("select", "eligibility"),
    ("select", "graph"),
    ("select", "bundle"),
    ("provider", "conformance"),
    ("provider", "trust"),
    ("install", "plan"),
    ("install", "resume"),
    ("setup", "import", "register"),
    ("target", "rollback"),
}


def test_the_current_roadmap_still_names_the_implemented_surfaces() -> None:
    commands = {tuple(descriptor.path) for descriptor in registry({}).payload.commands}
    roadmap = ROADMAP.read_text(encoding="utf-8")
    assert commands >= IMPLEMENTED_COMMAND_EVIDENCE, sorted(IMPLEMENTED_COMMAND_EVIDENCE - commands)
    for marker in ("| Local-first CLI |", "| Platform |", "| Web |", "| Providers |"):
        assert marker in roadmap


def test_the_roadmap_does_not_describe_the_local_core_as_future_work() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    stale_claims = (
        "Implement SQLite",
        "Implement discovery",
        "Implement components",
        "Implement mechanical constraints",
        "Freeze the shared protocol",
        "The project index, project passport, and goal-changing commands remain",
    )
    assert not any(claim in roadmap for claim in stale_claims)


def test_historical_sprint_reports_are_not_active_dependencies() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    assert "close `#86`" not in roadmap.lower()
    for name in (
        "sprint1-completion-report.md",
        "sprint1-cli-review-pack.md",
        "sprint1-external-review-prompt.md",
    ):
        assert not (ROADMAP.parent / name).exists(), name


def test_release_platform_claim_matches_the_current_product_decision() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    classifier_sets: list[set[str]] = []
    for project_path in PUBLISHABLE_PROJECTS:
        metadata = tomllib.loads(project_path.read_text(encoding="utf-8"))["project"]
        classifiers = set(metadata["classifiers"])
        classifier_sets.append(
            {item for item in classifiers if item.startswith("Operating System ::")}
        )
        assert "Operating System :: POSIX :: Linux" in classifiers, project_path
    assert all(items == classifier_sets[0] for items in classifier_sets[1:])
    macos = "Operating System :: MacOS"
    windows = "Operating System :: Microsoft :: Windows"
    if macos in classifier_sets[0] or windows in classifier_sets[0]:
        assert {macos, windows} <= classifier_sets[0]
    else:
        assert "update them after the evidence is complete" in roadmap
    assert "Linux, Windows, and macOS" in roadmap
    assert "`x86_64`/`arm64`" in roadmap
