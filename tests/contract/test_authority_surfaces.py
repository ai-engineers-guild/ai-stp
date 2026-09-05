"""Agent-facing instructions cannot demand pauses ADR-0150 already removed."""

from __future__ import annotations

from pathlib import Path

from docs_scripts import authority_surfaces

from ai_stp_cli.registry import COMMANDS

ROOT = Path(__file__).resolve().parents[2]


def test_the_inventory_covers_the_required_agent_surfaces() -> None:
    held = {path.relative_to(ROOT).as_posix() for path in authority_surfaces.inventory(ROOT)}
    for relative in (
        "AGENTS.md",
        ".claude/CLAUDE.md",
        "skills/canonical/ai-stp/SKILL.md",
        "skills/canonical/ai-stp/references/decisions.md",
        "skills/canonical/ai-stp/references/compose.md",
        "docs/agent/interaction-policy.md",
        "docs/agent/integration-skill.md",
        "docs/agent/machine-help.md",
    ):
        assert relative in held, relative
    assert any("first_party" in path and path.endswith(".md") for path in held)
    assert any(path.startswith("skills/projections/") for path in held)


def test_canonical_decisions_name_the_remaining_stops() -> None:
    text = (ROOT / "skills" / "canonical" / "ai-stp" / "references" / "decisions.md").read_text(
        encoding="utf-8"
    )
    for phrase in authority_surfaces.REMAINING_STOPS:
        assert phrase in text, phrase


def test_a_planted_ask_the_owner_instruction_is_detected(tmp_path: Path) -> None:
    planted = tmp_path / "AGENTS.md"
    planted.write_text(
        "Ask the owner before committing, merging, or publishing.\n",
        encoding="utf-8",
    )
    findings = authority_surfaces.scan([planted], root=tmp_path)
    assert any(item.kind == "ask_the_owner" for item in findings), findings


def test_repository_surfaces_match_canonical_authority() -> None:
    findings = authority_surfaces.scan_tree(ROOT)
    assert findings == (), "\n".join(
        f"{item.path}:{item.line} {item.kind}: {item.excerpt}" for item in findings
    )


def test_in_task_apply_does_not_demand_a_second_confirm() -> None:
    """Plan digest is the decision. A second --confirm is the A07 pause."""
    by_path = {tuple(command.descriptor.path): command for command in COMMANDS}
    for path in authority_surfaces.IN_TASK_APPLY:
        command = by_path[path]
        names = {parameter.name for parameter in command.descriptor.parameters}
        assert command.descriptor.confirmation in {"none", "plan_digest"}, (
            f"{command.name} confirmation={command.descriptor.confirmation}"
        )
        assert "confirm" not in names, command.name
