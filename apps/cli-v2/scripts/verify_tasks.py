"""Actual native task commands consumed by the existing Python machine models."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from ai_stp_cli.local import content, revisions, versions
from ai_stp_contracts.cli.tasks import TaskIntentsCatalog, TaskListView, TaskView
from ai_stp_foundation.digests import digest_canonical
from ai_stp_passports import ComponentVersionPassport, SetupVersionPassport
from ai_stp_sources.definition import validate_setup_definition


def prove(binary: Path, home: Path, root: Path, state: Path, run: Any) -> None:
    place = root / "task-proof"
    place.mkdir()
    source = place / "review source é"
    source.mkdir()
    original = (
        "---\nname: native-review\ndescription: Review code.\n---\nReport concrete findings.\n"
    )
    (source / "SKILL.md").write_text(original, encoding="utf-8")
    database = state / "ai-stp-v2-state" / "registry.sqlite3"

    def invoke(command: list[str], status: int = 0) -> dict[str, Any]:
        return run(binary, home, ["task", *command, "--state-dir", str(state)], status)

    def start(key: str, facts: dict[str, Any], status: int = 0) -> dict[str, Any]:
        path = place / "input.json"
        path.write_text(json.dumps(facts), encoding="utf-8")
        return invoke(
            ["start", "--intent", "author", "--idempotency-key", key, "--input", str(path)], status
        )

    def answer(view: dict[str, Any], question: str, value: str, status: int = 0) -> dict[str, Any]:
        return invoke(
            [
                "answer",
                "--task",
                view["task_id"],
                "--revision",
                str(view["revision"]),
                "--question-id",
                question,
                "--value",
                value,
            ],
            status,
        )

    def counts() -> tuple[int, ...]:
        with closing(sqlite3.connect(database)) as db:
            return tuple(
                db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in ("revision", "content", "operation", "object_version")
            )

    catalog = run(binary, home, ["task", "intents"])["data"]
    TaskIntentsCatalog.model_validate(catalog)
    assert [row["name"] for row in catalog["intents"]] == ["author"]
    fields = {row["name"]: row for row in catalog["intents"][0]["input_fields"]}
    assert "codex" in fields["harness_id"]["choices"]
    assert "cli" not in fields["component_type"]["choices"]
    before = counts()
    start("native-author-unsupported", {"harness_id": "codex", "component_type": "cli"}, 2)
    for invalid_key in ("short", "native author invalid", "x" * 129):
        start(invalid_key, {}, 2)
    assert counts() == before
    blocked = start("native-author-questions", {})
    view = blocked["data"]
    TaskView.model_validate(view)
    assert view["state"] == "blocked" and not view["goal_satisfied"]
    continuation = blocked["continuations"][0]
    assert continuation["actor"] == "human" and continuation["missing"] == ["value"]
    assert continuation["arguments"]["state-dir"] == str(state)
    assert continuation["argv"][:2] == ["task", "answer"]
    assert start("native-author-questions", {})["data"] == view
    start("native-author-questions", {"name": "different"}, 4)
    answer(view, "harness-id", "codex", 2)
    listing = invoke(["list"])["data"]
    TaskListView.model_validate(listing)
    assert view["task_id"] in {row["task_id"] for row in listing["tasks"]}
    assert invoke(["status", "--task", view["task_id"]])["data"] == view
    assert counts() == before

    argv = [*continuation["argv"][:-1], "--value", str(source)]
    view = run(binary, home, argv)["data"]
    stale = dict(view)
    conflict = start("native-author-overlap", {"harness_id": "codex"})["data"]
    answer(view, "harness-id", "codex", 4)
    assert invoke(["status", "--task", view["task_id"]])["data"] == view
    cancelled = invoke(
        ["cancel", "--task", conflict["task_id"], "--revision", str(conflict["revision"])]
    )["data"]
    assert cancelled["state"] == "cancelled" and not cancelled["goal_satisfied"]
    view = answer(view, "harness-id", "codex")["data"]
    answer(stale, "harness-id", "codex", 4)
    for question, value in [
        ("component-type", "skill"),
        ("name", "native-review"),
        ("license-spdx", "MIT"),
    ]:
        view = answer(view, question, value)["data"]
        TaskView.model_validate(view)
    assert view["state"] == "completed" and view["goal_satisfied"]
    assert len(view["child_operation_ids"]) == 1 and not view["questions"]
    outcome = view["outcome"]
    assert outcome["minted"] and outcome["component_version"] == outcome["setup_version"] == "1.0"
    with closing(sqlite3.connect(database)) as db:
        db.row_factory = sqlite3.Row
        passports: list[dict[str, Any]] = []
        for key in ("component_id", "setup_id"):
            held = versions.held(db, outcome[key], "1.0")
            assert held is not None
            recorded = revisions.get(db, held.revision_id)
            assert recorded is not None
            passports.append(recorded.envelope.model_dump(mode="json"))
        component = ComponentVersionPassport.model_validate(passports[0])
        setup = SetupVersionPassport.model_validate(passports[1])
        assert component.visibility == setup.visibility == "private"
        assert setup.components[0].stable_id == component.stable_id
        assert setup.components[0].passport_digest == digest_canonical(
            "ai-stp:passport:v1", passports[0]
        )
        definition = content.get(db, setup.artifact.digest)
        validate_setup_definition(definition)
        assert json.loads(definition)["embedded"][0]["passport"] == passports[0]
    facts = {
        "directory": str(source),
        "harness_id": "codex",
        "component_type": "skill",
        "name": "native-review",
        "license_spdx": "MIT",
    }
    reused = start("native-author-same-content", facts)["data"]
    assert reused["outcome"]["component_id"] == outcome["component_id"]
    assert reused["outcome"]["setup_id"] == outcome["setup_id"]
    assert not reused["outcome"]["minted"]
    assert (source / "SKILL.md").read_text(encoding="utf-8") == original
    source.rename(place / "source-unavailable")
    after = counts()
    assert start("native-author-questions", {})["data"] == view
    assert start("native-author-same-content", facts)["data"] == reused
    assert (
        invoke(["continue", "--task", view["task_id"], "--revision", str(view["revision"])])["data"]
        == view
    )
    assert (
        invoke(["cancel", "--task", view["task_id"], "--revision", str(view["revision"])])["data"]
        == view
    )
    assert invoke(["status", "--task", view["task_id"]])["continuations"] == []
    assert counts() == after
    assert invoke(["list"])["data"]["tasks"] == []
