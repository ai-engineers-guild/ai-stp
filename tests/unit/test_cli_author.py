"""Author intent registers a directory as one component and one setup identity."""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli import identity
from ai_stp_cli.application import author as author_service
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import passports, setup_author, versions
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_passports.versions import COMPONENT_TYPES


def test_author_asks_for_directory_once() -> None:
    started = task_command.start({"intent": "author", "idempotency-key": "author-ask-dir-0001"})
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "blocked"
    assert continued.payload.questions[0].question_id == "directory"
    assert continued.continuations[0].actor == "human"
    assert continued.continuations[0].argv[:2] == ["task", "answer"]
    assert "--value" not in continued.continuations[0].argv


def test_author_asks_for_harness_once(tmp_path: Path) -> None:
    started = task_command.start(
        {
            "intent": "author",
            "idempotency-key": "author-ask-harness-0001",
            "input": _facts(tmp_path, {"directory": str(_skill_tree(tmp_path))}),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.questions[0].question_id == "harness-id"


def test_author_asks_for_kind_from_native_surfaces(tmp_path: Path) -> None:
    started = task_command.start(
        {
            "intent": "author",
            "idempotency-key": "author-ask-kind-0001",
            "input": _facts(
                tmp_path,
                {"directory": str(_skill_tree(tmp_path)), "harness_id": "cursor"},
            ),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    question = continued.payload.questions[0]
    assert question.question_id == "component-type"
    assert question.choices == list(setup_author.kinds_for("cursor"))
    assert "skill" in question.choices
    assert set(question.choices) <= set(COMPONENT_TYPES)


def test_author_asks_for_name_once(tmp_path: Path) -> None:
    tree = _skill_tree(tmp_path)
    started = task_command.start(
        {
            "intent": "author",
            "idempotency-key": "author-ask-name-0001",
            "input": _facts(
                tmp_path,
                {
                    "directory": str(tree),
                    "harness_id": "cursor",
                    "component_type": "skill",
                },
            ),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    question = continued.payload.questions[0]
    assert question.question_id == "name"
    assert question.recommended == tree.name


def test_author_asks_for_license_once(tmp_path: Path) -> None:
    started = task_command.start(
        {
            "intent": "author",
            "idempotency-key": "author-ask-license-0001",
            "input": _facts(
                tmp_path,
                {
                    "directory": str(_skill_tree(tmp_path)),
                    "harness_id": "cursor",
                    "component_type": "skill",
                    "name": "demo",
                },
            ),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    question = continued.payload.questions[0]
    assert question.question_id == "license-spdx"
    assert question.recommended == setup_author.PRIVATE_LICENSE


def test_authored_setup_id_is_stable_for_the_same_bytes() -> None:
    first = setup_author.authored_setup_id(
        "account_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "cursor",
        "skill",
        "sha256:" + "a" * 64,
    )
    second = setup_author.authored_setup_id(
        "account_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "cursor",
        "skill",
        "sha256:" + "a" * 64,
    )
    assert first == second
    assert first.startswith("setup_")


def test_record_mints_one_component_and_one_setup(tmp_path: Path) -> None:
    tree = _skill_tree(tmp_path)
    current, _warning = identity.load_or_create()
    at = passports.moment()
    with closing(open_registry(configured_path(), create=True)) as connection:
        authored = setup_author.record(
            connection,
            directory=tree,
            harness_id="cursor",
            component_type="skill",
            name="demo",
            license_spdx="MIT",
            publisher_id=passports.owner().account_id,
            device_id=current.device_id,
            at=at,
        )
        assert authored.minted is True
        assert authored.setup_id.startswith("setup_")
        assert authored.component_id.startswith("component_")
        assert versions.held(connection, authored.setup_id, authored.setup_version) is not None
        replay = setup_author.record(
            connection,
            directory=tree,
            harness_id="cursor",
            component_type="skill",
            name="demo",
            license_spdx="MIT",
            publisher_id=passports.owner().account_id,
            device_id=current.device_id,
            at=at,
        )
        assert replay.minted is False
        assert replay.setup_id == authored.setup_id
        assert replay.component_id == authored.component_id


def test_author_drains_without_returning_to_the_model(tmp_path: Path) -> None:
    tree = _skill_tree(tmp_path)
    started = task_command.start(
        {
            "intent": "author",
            "idempotency-key": "author-drain-complete-0001",
            "input": _facts(
                tmp_path,
                {
                    "directory": str(tree),
                    "harness_id": "cursor",
                    "component_type": "skill",
                    "name": "demo",
                    "license_spdx": "MIT",
                },
            ),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "completed"
    assert continued.payload.goal_satisfied is True
    outcome = continued.payload.outcome
    assert outcome is not None
    assert outcome.kind == "author"
    assert outcome.setup_id.startswith("setup_")
    assert outcome.component_id.startswith("component_")
    assert outcome.minted is True
    assert not continued.continuations


def test_author_refuses_a_kind_without_a_native_surface(tmp_path: Path) -> None:
    with pytest.raises(CliFailure) as raised:
        task_command.start(
            {
                "intent": "author",
                "idempotency-key": "author-refuse-mcp-0001",
                "input": _facts(
                    tmp_path,
                    {
                        "directory": str(_skill_tree(tmp_path)),
                        "harness_id": "claude-code",
                        "component_type": "mcp",
                        "name": "demo",
                        "license_spdx": "MIT",
                    },
                ),
            }
        )
    assert raised.value.code == "AI_STP_CONFLICT"
    status = task_command.status({"task": raised.value.details["task"]})
    assert status.payload.state == "failed"


def test_author_modules_do_not_spawn_nested_cli() -> None:
    author_source = Path(author_service.__file__).read_text(encoding="utf-8")
    derive = Path(setup_author.__file__).read_text(encoding="utf-8")
    assert "Popen" not in author_source
    assert "subprocess" not in author_source
    assert "Popen" not in derive
    assert "subprocess" not in derive


def _skill_tree(tmp_path: Path) -> Path:
    tree = tmp_path / "demo-skill"
    tree.mkdir()
    (tree / "SKILL.md").write_text("# Demo\n\nA local skill.\n", encoding="utf-8")
    return tree


def _facts(tmp_path: Path, body: dict[str, str]) -> str:
    place = tmp_path / "input.json"
    place.write_text(json.dumps(body), encoding="utf-8")
    return str(place)
