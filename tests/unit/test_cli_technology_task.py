"""Technology intent drains the unmapped queue and mapping publication."""

from __future__ import annotations

import json
from pathlib import Path

from ai_stp_cli.commands import task as task_command


def _facts(tmp_path: Path, body: dict[str, object]) -> str:
    place = tmp_path / "input.json"
    place.write_text(json.dumps(body), encoding="utf-8")
    return str(place)


def test_technology_intent_asks_for_the_action_first() -> None:
    started = task_command.start({"intent": "technology", "idempotency-key": "technology-ask-0001"})
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "blocked"
    question = continued.payload.questions[0]
    assert question.question_id == "action"
    assert question.choices == ["unmapped", "publish-mapping"]


def test_technology_intent_scans_a_root_and_lists_unmapped(tmp_path: Path) -> None:
    root = tmp_path / "work"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "work"\ndependencies = ["left-pad-xyz"]\n',
        encoding="utf-8",
    )
    started = task_command.start(
        {
            "intent": "technology",
            "idempotency-key": "technology-unmapped-0001",
            "input": _facts(tmp_path, {"action": "unmapped", "project_root": str(root)}),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "completed"
    outcome = continued.payload.outcome
    assert outcome is not None and outcome.kind == "technology"
    assert outcome.action == "unmapped"
    coordinates = {(item.kind, item.coordinate) for item in outcome.coordinates}
    assert ("package", "left-pad-xyz") in coordinates
    # Python itself resolves through the bundled seed — it is not in the queue.
    assert ("alias", "python") not in coordinates
    assert outcome.server_coordinates == []


def test_technology_intent_asks_for_publication_facts(tmp_path: Path) -> None:
    started = task_command.start(
        {
            "intent": "technology",
            "idempotency-key": "technology-publish-0001",
            "input": _facts(tmp_path, {"action": "publish-mapping"}),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "blocked"
    question_ids = {question.question_id for question in continued.payload.questions}
    assert question_ids == {
        "organization-id",
        "mapping-version",
        "authorization-revision",
    }
