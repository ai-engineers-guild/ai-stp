"""Every declared command is inspect, task_covered, task_pending, expert, or obsolete."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ai_stp_cli.application.inventory import (
    EVERYDAY_JOURNEYS,
    EXPERT,
    INSPECT,
    OBSOLETE,
    TASK_COVERED,
    TASK_PENDING,
    classified_paths,
    classify,
    everyday_intent,
    everyday_success_start_intent,
    expert_reason,
)
from ai_stp_cli.registry import DECLARATIONS


def test_every_declared_command_is_classified() -> None:
    declared = {tuple(item.path) for item in DECLARATIONS}
    classified = classified_paths()
    unlabeled = declared - classified
    extra = classified - declared
    assert not unlabeled, f"unlabeled leftover: {sorted(unlabeled)}"
    assert not extra, f"classified but undeclared: {sorted(extra)}"
    buckets = (INSPECT, TASK_COVERED, TASK_PENDING, frozenset(EXPERT), frozenset(OBSOLETE))
    for index, left in enumerate(buckets):
        for right in buckets[index + 1 :]:
            assert not (left & right)
    for path in declared:
        assert classify(path) in {
            "inspect",
            "task_covered",
            "task_pending",
            "expert",
            "obsolete",
        }


def test_everyday_journeys_are_not_expert() -> None:
    declared = {tuple(item.path) for item in DECLARATIONS}
    assert declared >= EVERYDAY_JOURNEYS
    assert TASK_PENDING | TASK_COVERED >= EVERYDAY_JOURNEYS
    assert EVERYDAY_JOURNEYS.isdisjoint(EXPERT)
    assert EVERYDAY_JOURNEYS.isdisjoint(INSPECT)


def test_task_lifecycle_is_covered_and_intents_are_inspect() -> None:
    declared = {tuple(item.path) for item in DECLARATIONS}
    assert declared >= TASK_COVERED
    assert classify(("task", "intents")) == "inspect"
    for path in TASK_COVERED:
        assert classify(path) == "task_covered"


def test_every_everyday_journey_has_a_draining_intent() -> None:
    missing = [path for path in sorted(EVERYDAY_JOURNEYS) if everyday_intent(path) is None]
    assert not missing


def test_component_publish_is_not_task_covered() -> None:
    assert classify(("component", "publish")) == "task_pending"
    assert ("component", "publish") in EVERYDAY_JOURNEYS
    assert everyday_intent(("component", "publish")) == "publish"


def test_setup_publish_leaves_drain_to_publish() -> None:
    assert classify(("setup", "publish", "plan")) == "task_pending"
    assert ("setup", "publish", "plan") in EVERYDAY_JOURNEYS
    assert everyday_intent(("setup", "publish", "plan")) == "publish"
    assert everyday_intent(("setup", "publish", "confirm")) == "publish"


def test_everyday_success_start_covers_read_and_plan_not_apply() -> None:
    assert (
        everyday_success_start_intent(("install", "status"), "read", has_continuations=False)
        == "install"
    )
    assert (
        everyday_success_start_intent(("install", "plan"), "plan", has_continuations=False)
        == "install"
    )
    assert (
        everyday_success_start_intent(("publication", "plan"), "plan", has_continuations=False)
        == "publish"
    )
    assert (
        everyday_success_start_intent(
            ("setup", "preserve", "plan"), "plan", has_continuations=False
        )
        == "switch"
    )
    assert (
        everyday_success_start_intent(("install", "apply"), "apply", has_continuations=False)
        is None
    )
    assert (
        everyday_success_start_intent(("install", "approve"), "apply", has_continuations=False)
        is None
    )
    assert (
        everyday_success_start_intent(("auth", "login"), "apply", has_continuations=False)
        == "account"
    )
    assert (
        everyday_success_start_intent(("registry", "acquire"), "apply", has_continuations=False)
        == "install"
    )
    assert (
        everyday_success_start_intent(
            ("setup", "compose", "apply"), "apply", has_continuations=False
        )
        is None
    )
    assert (
        everyday_success_start_intent(("auth", "complete"), "apply", has_continuations=False)
        is None
    )
    assert (
        everyday_success_start_intent(("install", "plan"), "plan", has_continuations=True) is None
    )
    assert (
        everyday_success_start_intent(("setup", "restore", "plan"), "plan", has_continuations=False)
        == "switch"
    )


def test_install_leaves_are_task_covered() -> None:
    for name in ("plan", "approve", "apply", "cancel", "status", "recover", "resume"):
        assert classify(("install", name)) == "task_covered"
    assert classify(("registry", "acquire")) == "task_covered"
    assert classify(("setup", "compose", "apply")) == "task_covered"
    assert classify(("setup", "preserve", "plan")) == "task_covered"
    assert classify(("setup", "preserved", "list")) == "task_covered"
    assert classify(("setup", "restore", "plan")) == "task_covered"
    assert classify(("auth", "login")) == "task_covered"
    assert classify(("auth", "complete")) == "task_covered"
    assert classify(("auth", "logout")) == "task_covered"
    assert classify(("publication", "plan")) == "task_covered"
    assert classify(("publication", "confirm")) == "task_covered"
    assert classify(("sync", "push")) == "task_covered"
    assert classify(("sync", "pull")) == "task_covered"


def test_classify_rejects_an_unknown_path() -> None:
    with pytest.raises(KeyError):
        classify(("not-a-command",))


def test_every_expert_path_has_a_reason() -> None:
    for path in EXPERT:
        reason = expert_reason(path)
        assert reason
        assert "\n" not in reason


def test_application_layer_does_not_start_another_cli_process() -> None:
    root = (
        Path(__file__).resolve().parents[2] / "apps" / "cli" / "src" / "ai_stp_cli" / "application"
    )
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "os.system" not in text, f"{path.name} mentions os.system"
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node.func) not in {"subprocess.run", "subprocess.Popen", "Popen"}:
                continue
            assert not _literal_ai_stp(node), f"{path.name} starts a nested ai-stp process"


def test_application_layer_does_not_import_command_handlers() -> None:
    root = (
        Path(__file__).resolve().parents[2] / "apps" / "cli" / "src" / "ai_stp_cli" / "application"
    )
    banned = ("from ai_stp_cli.commands", "import ai_stp_cli.commands")
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name} imports command handlers"


def test_application_layer_does_not_dispatch_registry_handlers() -> None:
    root = (
        Path(__file__).resolve().parents[2] / "apps" / "cli" / "src" / "ai_stp_cli" / "application"
    )
    banned = ("COMMANDS", "handler_ref", "importlib")
    text = (root / "task.py").read_text(encoding="utf-8")
    for token in banned:
        assert token not in text, f"task.py mentions {token}"


def test_install_command_handlers_call_the_application_service() -> None:
    from ai_stp_cli.application import install as install_service
    from ai_stp_cli.commands import install as install_command

    assert install_command.apply.__globals__["install_service"] is install_service
    assert install_command.plan.__globals__["install_service"].plan is install_service.plan


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return ""


def _literal_ai_stp(node: ast.Call) -> bool:
    for arg in (*node.args, *[keyword.value for keyword in node.keywords]):
        if isinstance(arg, ast.Constant) and arg.value == "ai-stp":
            return True
        if isinstance(arg, ast.List | ast.Tuple):
            for element in arg.elts:
                if isinstance(element, ast.Constant) and element.value == "ai-stp":
                    return True
    return False
