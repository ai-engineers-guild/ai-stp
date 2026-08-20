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

PHASE_COMMAND_EVIDENCE = {
    2: {
        ("config", "validate"),
        ("passport", "developer", "init"),
        ("sync", "preview"),
        ("doctor",),
    },
    3: {("toolchain", "install"), ("project", "index"), ("project", "symbols")},
    4: {("component", "adopt"), ("component", "version", "release"), ("consent", "allow")},
    5: {("select", "eligibility"), ("select", "graph"), ("select", "bundle")},
    6: {("provider", "conformance"), ("provider", "trust"), ("install", "plan")},
    7: {("install", "resume"), ("setup", "import", "register"), ("target", "rollback")},
}


def test_every_implemented_cli_phase_still_has_public_command_evidence() -> None:
    commands = {tuple(descriptor.path) for descriptor in registry({}).payload.commands}
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for phase, expected in PHASE_COMMAND_EVIDENCE.items():
        heading = next(
            line for line in roadmap.splitlines() if line.startswith(f"## Фаза {phase}.")
        )
        assert "реализ" in heading, heading
        assert expected <= commands, f"phase {phase}: {sorted(expected - commands)}"


def test_the_roadmap_does_not_describe_the_local_core_as_future_work() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    stale_claims = (
        "Реализовать SQLite",
        "Реализовать обнаружение",
        "Реализовать компоненты",
        "Реализовать механические ограничения",
        "Заморозить общий протокол",
        "Индекс проекта, паспорт проекта и изменяющие цель команды остаются",
    )
    assert not any(claim in roadmap for claim in stale_claims)


def test_closed_sprint_report_is_not_a_future_release_dependency() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    assert "Задача `#86` уже завершена" in roadmap
    assert "закрыть `#86`" not in roadmap.lower()


def test_release_platform_claim_matches_the_current_product_decision() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    for project_path in PUBLISHABLE_PROJECTS:
        metadata = tomllib.loads(project_path.read_text(encoding="utf-8"))["project"]
        classifiers = set(metadata["classifiers"])
        assert "Operating System :: POSIX :: Linux" in classifiers, project_path
        assert "Operating System :: MacOS" not in classifiers, project_path
    assert "ADR-0062" in roadmap
    assert "macOS не входит в текущую support matrix" in roadmap
