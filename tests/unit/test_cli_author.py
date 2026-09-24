"""Author intent registers a directory as one component and one setup identity."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli import identity
from ai_stp_cli.application import author as author_service
from ai_stp_cli.application import select as select_service
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import content, passports, revisions, setup_author, setup_compose, versions
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


@pytest.mark.parametrize("with_script", [False, True])
def test_authored_antigravity_skill_preserves_native_files(
    tmp_path: Path, with_script: bool
) -> None:
    tree = _skill_tree(tmp_path)
    expected = {"config/skills/demo/SKILL.md": (tree / "SKILL.md").read_bytes()}
    if with_script:
        (tree / "scripts").mkdir()
        (tree / "scripts" / "check.py").write_bytes(b"print('checked')\n")
        expected["config/skills/demo/scripts/check.py"] = b"print('checked')\n"
    (tree / "GENERATED.md").write_text("Generated source notes.\n", encoding="utf-8")
    authored = author_service.persist(
        directory=tree,
        harness_id="antigravity",
        component_type="skill",
        name="demo",
        license_spdx="MIT",
    )
    with closing(open_registry(configured_path(), create=True)) as connection:
        held = versions.held(connection, authored.setup_id, authored.setup_version)
        assert held is not None
        stored = revisions.get(connection, held.revision_id)
        assert stored is not None
        definition = content.get(connection, stored.envelope.model_dump()["artifact"]["digest"])
        assert definition is not None
        embedded = json.loads(definition)["embedded"][0]
        artifact = base64.urlsafe_b64decode(embedded["artifact_b64"] + "===")
        with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
            assert {name: archive.read(name) for name in archive.namelist()} == expected
    replay = author_service.persist(
        directory=tree,
        harness_id="antigravity",
        component_type="skill",
        name="demo",
        license_spdx="MIT",
    )
    assert replay.setup_id == authored.setup_id
    assert replay.component_id == authored.component_id
    assert replay.minted is False


@pytest.mark.parametrize("kind", ["skill", "setting"])
def test_authored_setup_compiles_immediately_without_a_change_task(
    tmp_path: Path, kind: str
) -> None:
    tree = tmp_path / "native-component"
    tree.mkdir()
    filename = "SKILL.md" if kind == "skill" else "settings.json"
    payload = b"# Native skill\n" if kind == "skill" else b'{"toolPermission":"accept-edits"}\n'
    (tree / filename).write_bytes(payload)
    authored = author_service.persist(
        directory=tree,
        harness_id="antigravity",
        component_type=kind,
        name="native-component",
        license_spdx="MIT",
    )
    with closing(open_registry(configured_path(), create=True)) as connection:
        compiled = select_service.compile_setup_version_bundle(
            connection, authored.setup_id, authored.setup_version, expected_harness="antigravity"
        )
        with zipfile.ZipFile(io.BytesIO(compiled.archive)) as archive:
            names = archive.namelist()
            assert any(name.endswith(filename) for name in names)
            assert any(archive.read(name) == payload for name in names if name.endswith(filename))


def test_author_replay_repairs_legacy_embedded_storage_without_reissuing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = _skill_tree(tmp_path)

    def author() -> setup_author.AuthoredSetup:
        return author_service.persist(
            directory=tree,
            harness_id="antigravity",
            component_type="skill",
            name="demo",
            license_spdx="MIT",
        )

    def omit_embedded(*args: object, **kwargs: object) -> None:
        pass

    with monkeypatch.context() as legacy:
        legacy.setattr(setup_compose, "retain_embedded", omit_embedded)
        original = author()
    with closing(open_registry(configured_path(), create=True)) as connection:
        before = versions.held(connection, original.setup_id, original.setup_version)
        assert versions.held(connection, original.component_id, original.component_version) is None
    replay = author()
    assert not replay.minted
    with closing(open_registry(configured_path(), create=True)) as connection:
        assert versions.held(connection, replay.setup_id, replay.setup_version) == before
        compiled = select_service.compile_setup_version_bundle(
            connection, replay.setup_id, replay.setup_version, expected_harness="antigravity"
        )
        assert compiled.archive


def test_author_refuses_multiple_files_for_a_single_file_surface(tmp_path: Path) -> None:
    tree = tmp_path / "settings"
    tree.mkdir()
    (tree / "settings.json").write_text("{}\n", encoding="utf-8")
    (tree / "other.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(CliFailure) as raised:
        task_command.start(
            {
                "intent": "author",
                "idempotency-key": "author-file-surface-0001",
                "input": _facts(
                    tmp_path,
                    {
                        "directory": str(tree),
                        "harness_id": "antigravity",
                        "component_type": "setting",
                        "name": "demo",
                        "license_spdx": "MIT",
                    },
                ),
            }
        )
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert "one source file" in raised.value.message
    status = task_command.status({"task": raised.value.details["task"]})
    assert status.payload.state == "failed"


@pytest.mark.parametrize("name", ["..", "../outside", "nested/name", "nested\\name"])
def test_author_refuses_names_that_are_not_native_path_segments(tmp_path: Path, name: str) -> None:
    with pytest.raises(CliFailure, match="one native path segment"):
        author_service.persist(
            directory=_skill_tree(tmp_path),
            harness_id="antigravity",
            component_type="skill",
            name=name,
            license_spdx="MIT",
        )


def test_author_refuses_a_tree_with_only_generated_notes(tmp_path: Path) -> None:
    tree = tmp_path / "notes"
    tree.mkdir()
    (tree / "GENERATED.md").write_text("Generated notes.\n", encoding="utf-8")
    with pytest.raises(CliFailure) as raised:
        author_service.persist(
            directory=tree,
            harness_id="antigravity",
            component_type="skill",
            name="demo",
            license_spdx="MIT",
        )
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"
    assert raised.value.details["source_code"] == "incomplete_passport"


def test_author_answer_failure_emits_resumable_revision_without_reminting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    persist = author_service.persist
    written: list[setup_author.AuthoredSetup] = []

    def interrupted(
        *, directory: Path, harness_id: str, component_type: str, name: str, license_spdx: str
    ) -> setup_author.AuthoredSetup:
        result = persist(
            directory=directory,
            harness_id=harness_id,
            component_type=component_type,
            name=name,
            license_spdx=license_spdx,
        )
        written.append(result)
        if len(written) == 1:
            raise RuntimeError("interrupted after persisting the authored setup")
        return result

    monkeypatch.setattr(author_service, "persist", interrupted)
    started = task_command.start(
        {
            "intent": "author",
            "idempotency-key": "author-answer-interrupted-01",
            "input": _facts(
                tmp_path,
                {
                    "directory": str(_skill_tree(tmp_path)),
                    "harness_id": "antigravity",
                    "component_type": "skill",
                    "name": "demo",
                },
            ),
        }
    )
    with pytest.raises(CliFailure) as raised:
        task_command.answer(
            {
                "task": started.payload.task_id,
                "revision": started.payload.revision,
                "question-id": "license-spdx",
                "value": "MIT",
            }
        )
    assert raised.value.code == "AI_STP_INTERNAL"
    status = task_command.status({"task": started.payload.task_id})
    assert status.payload.state == "running"
    resume = raised.value.continuations[0]
    assert resume.actor == "cli"
    assert resume.path == ["task", "continue"]
    assert resume.arguments == {
        "task": started.payload.task_id,
        "revision": status.payload.revision,
    }
    assert status.continuations == (resume,)
    assert len(written) == 1  # Reading status never drains.
    finished = task_command.continue_(resume.arguments)
    assert finished.payload.goal_satisfied is True
    assert finished.payload.state == "completed"
    assert written[1].setup_id == written[0].setup_id
    assert written[0].minted is True
    assert written[1].minted is False


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
