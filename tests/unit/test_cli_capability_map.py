"""Every declared command is inspect, a planned task family, or expert-only."""

from __future__ import annotations

from pathlib import Path

from ai_stp_cli.registry import DECLARATIONS

#: Cheap orientation. The task engine and `capabilities` share this set.
INSPECT: frozenset[tuple[str, ...]] = frozenset(
    {
        ("auth", "status"),
        ("capabilities",),
        ("config", "show"),
        ("config", "validate"),
        ("contract", "inventory"),
        ("doctor",),
        ("environment", "inspect"),
        ("help",),
        ("telemetry", "show"),
        ("toolchain", "harness-capabilities"),
        ("toolchain", "harnesses"),
        ("toolchain", "profile"),
        ("update", "check"),
        ("update", "status"),
        ("version",),
    }
)

#: Keep as leaf commands. Everyday journeys must not live only here.
EXPERT: frozenset[tuple[str, ...]] = frozenset(
    {
        ("attestation", "sign"),
        ("component", "source", "evidence", "history"),
        ("component", "source", "evidence", "refresh"),
        ("component", "source", "evidence", "show"),
        ("component", "source", "parse"),
        ("component", "source", "resolve"),
        ("component", "source", "search"),
        ("component", "template", "render"),
        ("eval", "component", "plan"),
        ("eval", "component", "run"),
        ("eval", "component", "show"),
        ("eval", "component", "status"),
        ("eval", "plan"),
        ("eval", "profile"),
        ("eval", "run"),
        ("eval", "show"),
        ("eval", "status"),
        ("github", "source", "prepare"),
        ("github", "status"),
        ("grant", "accept"),
        ("grant", "direct"),
        ("grant", "invitation", "revoke"),
        ("grant", "invite"),
        ("grant", "list"),
        ("grant", "revoke"),
        ("link", "web"),
        ("owner", "object", "show"),
        ("owner", "objects"),
        ("owner", "version", "show"),
        ("provider", "conformance"),
        ("provider", "network"),
        ("report", "confirm"),
        ("report", "list"),
        ("report", "preview"),
        ("report", "status"),
        ("select", "blast-radius"),
        ("select", "eligibility-matrix"),
        ("select", "impact"),
        ("select", "reports"),
        ("select", "session"),
    }
)

TASK_LIFECYCLE: frozenset[tuple[str, ...]] = frozenset(
    {
        ("task", "start"),
        ("task", "answer"),
        ("task", "continue"),
        ("task", "status"),
        ("task", "cancel"),
    }
)

#: Everyday journeys the task engine will drain. They stay callable leaves.
EVERYDAY_TASK: frozenset[tuple[str, ...]] = frozenset(
    {
        ("install", "plan"),
        ("install", "apply"),
        ("registry", "search"),
        ("target", "status"),
        ("target", "diff"),
        ("target", "rollback"),
        ("component", "adopt"),
    }
)


def _kind(path: tuple[str, ...]) -> str:
    if path in INSPECT:
        return "inspect"
    if path in EXPERT:
        return "expert"
    return "task"


def test_every_declared_command_is_classified() -> None:
    declared = {tuple(item.path) for item in DECLARATIONS}
    assert declared >= INSPECT
    assert declared >= EXPERT
    assert not (INSPECT & EXPERT)
    leftover = declared - INSPECT - EXPERT
    assert leftover, "the task class must cover everyday journeys"
    assert leftover >= EVERYDAY_TASK
    assert leftover >= TASK_LIFECYCLE
    for path in leftover:
        assert _kind(path) == "task"


def test_task_lifecycle_paths_are_declared() -> None:
    declared = {tuple(item.path) for item in DECLARATIONS}
    assert declared >= TASK_LIFECYCLE


def test_application_layer_does_not_start_another_cli_process() -> None:
    root = (
        Path(__file__).resolve().parents[2] / "apps" / "cli" / "src" / "ai_stp_cli" / "application"
    )
    banned = ("subprocess", "os.system", "Popen")
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name} mentions {token}"


def test_application_layer_does_not_dispatch_registry_handlers() -> None:
    root = (
        Path(__file__).resolve().parents[2] / "apps" / "cli" / "src" / "ai_stp_cli" / "application"
    )
    banned = ("COMMANDS", "handler_ref", "importlib")
    text = (root / "task.py").read_text(encoding="utf-8")
    for token in banned:
        assert token not in text, f"task.py mentions {token}"
