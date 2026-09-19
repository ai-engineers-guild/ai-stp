"""Change intent mints a new setup identity and drains install in-process."""

from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path

import pytest

from ai_stp_cli import identity
from ai_stp_cli.answer import Answer
from ai_stp_cli.application import change as change_service
from ai_stp_cli.application import install as install_service
from ai_stp_cli.application.install_task import recommend_setup
from ai_stp_cli.commands import task as task_command
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import passports, revisions, setup_compose, setup_derive, versions
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.first_party import FirstPartyCatalogMember, catalog_identity
from ai_stp_contracts.machine_help import InstallationView
from ai_stp_foundation.ids import new_id
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports.versions import SetupVersionPassport


def test_change_asks_for_harness_once() -> None:
    started = task_command.start({"intent": "change", "idempotency-key": "change-ask-harness-0001"})
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.state == "blocked"
    assert continued.payload.questions[0].question_id == "harness-id"
    assert continued.continuations[0].actor == "human"
    assert continued.continuations[0].argv[:2] == ["task", "answer"]
    assert "--value" not in continued.continuations[0].argv


def test_change_asks_for_component_once(tmp_path: Path) -> None:
    started = task_command.start(
        {
            "intent": "change",
            "idempotency-key": "change-ask-component-0001",
            "input": _facts(tmp_path, {"harness_id": "cursor"}),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.questions[0].question_id == "component-ref"
    assert continued.payload.questions[0].choices == []


def test_change_asks_for_absolute_project_root(tmp_path: Path) -> None:
    extra = _extra_cursor_component()
    started = task_command.start(
        {
            "intent": "change",
            "idempotency-key": "change-ask-project-0001",
            "input": _facts(
                tmp_path,
                {
                    "harness_id": "cursor",
                    "component_id": extra.stable_id,
                    "component_version": extra.version,
                },
            ),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    question = continued.payload.questions[0]
    assert question.question_id == "project-root"


def test_derived_setup_id_is_stable_for_the_same_delta() -> None:
    first = setup_derive.derived_setup_id(
        "account_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "setup_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "1.4",
        "add",
        "component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "1.0",
    )
    second = setup_derive.derived_setup_id(
        "account_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "setup_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "1.4",
        "add",
        "component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "1.0",
    )
    assert first == second
    assert first.startswith("setup_")
    assert first != "setup_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def test_next_members_add_is_noop_when_the_pin_is_already_present() -> None:
    member = _baseline_member()
    members, unchanged = setup_derive.next_members((member,), "add", member)
    assert unchanged is True
    assert members == (member,)


def test_next_members_add_mints_a_new_graph() -> None:
    held = _baseline_member()
    extra = _component_ref(_extra_cursor_component())
    members, unchanged = setup_derive.next_members((held,), "add", extra)
    assert unchanged is False
    assert extra in members
    assert held in members


def test_next_members_refuse_removing_the_last_component() -> None:
    member = _baseline_member()
    with pytest.raises(CliFailure) as raised:
        setup_derive.next_members((member,), "remove", member)
    assert raised.value.code == "AI_STP_VALIDATION_ERROR"


def test_record_mints_new_identity_and_keeps_the_source() -> None:
    pin = recommend_setup("cursor")
    assert pin is not None
    extra = _extra_cursor_component()
    current, _warning = identity.load_or_create()
    at = passports.moment()
    with closing(open_registry(configured_path(), create=True)) as connection:
        source = setup_derive.remember_corpus_setup(
            connection,
            pin.setup_id,
            pin.setup_version,
            device_id=current.device_id,
            at=at,
        )
        source_item = setup_derive.corpus_item("setup", pin.setup_id, pin.setup_version)
        extra_item = setup_derive.corpus_item("component", extra.stable_id, extra.version)
        assert source_item is not None
        assert extra_item is not None
        catalog = (
            *_source_catalog(source),
            setup_derive.catalog_material(extra_item),
        )
        derived = setup_derive.record(
            connection,
            source=source,
            source_digest=source_item.passport_digest,
            action="add",
            component=_component_ref(extra),
            catalog=catalog,
            publisher_id=passports.owner().account_id,
            device_id=current.device_id,
            at=at,
        )
        assert derived.minted is True
        assert derived.setup_id != pin.setup_id
        assert versions.held(connection, pin.setup_id, pin.setup_version) is not None
        assert versions.held(connection, derived.setup_id, derived.setup_version) is not None
        origin = versions.forked_from(connection, derived.setup_id)
        assert origin is not None
        assert origin.source_stable_id == pin.setup_id
        replay = setup_derive.record(
            connection,
            source=source,
            source_digest=source_item.passport_digest,
            action="add",
            component=_component_ref(extra),
            catalog=catalog,
            publisher_id=passports.owner().account_id,
            device_id=current.device_id,
            at=at,
        )
        assert replay.setup_id == derived.setup_id
        stored = versions.held(connection, derived.setup_id, derived.setup_version)
        assert stored is not None
        held_revision = revisions.get(connection, stored.revision_id)
        assert held_revision is not None
        passport = SetupVersionPassport.model_validate(
            held_revision.envelope.model_dump(mode="json")
        )
        assert pin.setup_id in passport.related_setup_ids


def test_record_does_not_mint_when_the_member_is_already_present() -> None:
    pin = recommend_setup("cursor")
    assert pin is not None
    current, _warning = identity.load_or_create()
    at = passports.moment()
    with closing(open_registry(configured_path(), create=True)) as connection:
        source = setup_derive.remember_corpus_setup(
            connection,
            pin.setup_id,
            pin.setup_version,
            device_id=current.device_id,
            at=at,
        )
        source_item = setup_derive.corpus_item("setup", pin.setup_id, pin.setup_version)
        assert source_item is not None
        member = source.components[0]
        derived = setup_derive.record(
            connection,
            source=source,
            source_digest=source_item.passport_digest,
            action="add",
            component=member,
            catalog=(),
            publisher_id=passports.owner().account_id,
            device_id=current.device_id,
            at=at,
        )
        assert derived.minted is False
        assert derived.setup_id == pin.setup_id


def test_change_drains_derive_then_install_without_returning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin = recommend_setup("cursor")
    assert pin is not None
    extra = _extra_cursor_component()
    derived_id = new_id("setup")
    seen: list[str] = []

    def derive_setup(**kwargs: object) -> setup_derive.DerivedSetup:
        source = kwargs["source"]
        assert isinstance(source, SetupVersionPassport)
        seen.append(source.stable_id)
        return setup_derive.DerivedSetup(
            setup_id=derived_id,
            setup_version="1.0",
            minted=True,
            source_setup_id=pin.setup_id,
            source_setup_version=pin.setup_version,
        )

    monkeypatch.setattr(change_service, "derive_setup", derive_setup)
    operation_id = _stub_install(monkeypatch)
    started = task_command.start(
        {
            "intent": "change",
            "idempotency-key": "change-drain-in-process-01",
            "input": _facts(
                tmp_path,
                {
                    "harness_id": "cursor",
                    "component_id": extra.stable_id,
                    "component_version": extra.version,
                    "project_root": str(tmp_path.resolve()),
                },
            ),
        }
    )
    continued = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert continued.payload.questions == []
    assert continued.payload.state == "completed"
    assert continued.payload.outcome is not None
    assert continued.payload.outcome.kind == "change"
    assert continued.payload.outcome.setup_id == derived_id
    assert continued.payload.outcome.source_setup_id == pin.setup_id
    assert continued.payload.outcome.minted is True
    assert continued.payload.outcome.operation_id == operation_id
    assert seen == [pin.setup_id]


def test_change_maps_compensated_install_to_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra = _extra_cursor_component()

    def derive_setup(**kwargs: object) -> setup_derive.DerivedSetup:
        source = kwargs["source"]
        assert isinstance(source, SetupVersionPassport)
        return setup_derive.DerivedSetup(
            setup_id=new_id("setup"),
            setup_version="1.0",
            minted=True,
            source_setup_id=source.stable_id,
            source_setup_version=source.version,
        )

    monkeypatch.setattr(change_service, "derive_setup", derive_setup)
    operation_id = new_id("operation")
    digest = "sha256:" + "c" * 64

    def plan(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return Answer(_installation(operation_id, "planned", digest))

    def approve(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return Answer(_installation(operation_id, "approved", digest))

    def apply(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        raise CliFailure("AI_STP_COMPENSATED", "rolled back")

    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(install_service, "approve", approve)
    monkeypatch.setattr(install_service, "apply", apply)
    with pytest.raises(CliFailure) as raised:
        task_command.start(
            {
                "intent": "change",
                "idempotency-key": "change-compensated-0001",
                "input": _facts(
                    tmp_path,
                    {
                        "harness_id": "cursor",
                        "component_id": extra.stable_id,
                        "component_version": extra.version,
                        "project_root": str(tmp_path.resolve()),
                    },
                ),
            }
        )
    assert raised.value.code == "AI_STP_COMPENSATED"
    assert raised.value.details.get("state") == "failed"
    status = task_command.status({"task": raised.value.details["task"]})
    assert status.payload.state == "failed"


def test_change_adds_a_locally_authored_component_without_cloud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = tmp_path / "demo-skill"
    tree.mkdir()
    (tree / "SKILL.md").write_text("# Demo\n\nA local skill.\n", encoding="utf-8")
    author_in = tmp_path / "author-in"
    author_in.mkdir()
    authored = task_command.start(
        {
            "intent": "author",
            "idempotency-key": "change-local-author-0001",
            "input": _facts(
                author_in,
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
    authored = task_command.continue_(
        {"task": authored.payload.task_id, "revision": authored.payload.revision}
    )
    assert authored.payload.state == "completed"
    assert authored.payload.outcome is not None
    authored_outcome = authored.payload.outcome
    assert authored_outcome.kind == "author"

    def boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("locally authored component must not hit the catalog")

    monkeypatch.setattr(change_service, "_acquire_component", boom)
    pin = recommend_setup("cursor")
    assert pin is not None
    _stub_install(monkeypatch)
    change_in = tmp_path / "change-in"
    change_in.mkdir()
    started = task_command.start(
        {
            "intent": "change",
            "idempotency-key": "change-local-component-01",
            "input": _facts(
                change_in,
                {
                    "harness_id": "cursor",
                    "component_id": authored_outcome.component_id,
                    "component_version": authored_outcome.component_version,
                    "project_root": str(tmp_path.resolve()),
                },
            ),
        }
    )
    finished = task_command.continue_(
        {"task": started.payload.task_id, "revision": started.payload.revision}
    )
    assert finished.payload.state == "completed"
    assert finished.payload.outcome is not None
    assert finished.payload.outcome.kind == "change"
    assert finished.payload.outcome.source_setup_id == pin.setup_id
    assert finished.payload.outcome.setup_id != pin.setup_id
    assert finished.payload.outcome.minted is True


def test_change_module_does_not_start_a_process() -> None:
    source = Path("apps/cli/src/ai_stp_cli/application/change.py").read_text("utf-8")
    assert "Popen" not in source
    assert "subprocess" not in source
    derive = Path("apps/cli/src/ai_stp_cli/local/setup_derive.py").read_text("utf-8")
    assert "Popen" not in derive
    assert "subprocess" not in derive


def _stub_install(monkeypatch: pytest.MonkeyPatch) -> str:
    operation_id = new_id("operation")
    digest = "sha256:" + "b" * 64

    def plan(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return Answer(_installation(operation_id, "planned", digest))

    def approve(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return Answer(_installation(operation_id, "approved", digest))

    def apply(_parameters: Mapping[str, object]) -> Answer[InstallationView]:
        return Answer(_installation(operation_id, "verified", digest))

    monkeypatch.setattr(install_service, "plan", plan)
    monkeypatch.setattr(install_service, "approve", approve)
    monkeypatch.setattr(install_service, "apply", apply)
    return operation_id


def _installation(operation_id: str, state: str, digest: str) -> InstallationView:
    return InstallationView.model_validate(
        {
            "operation_id": operation_id,
            "action": "install",
            "state": state,
            "plan_digest": digest,
            "target_id": "project:cursor",
            "expected_target_digest": digest,
            "expires_at": "2026-09-16T00:00:00.000Z",
        }
    )


def _facts(tmp_path: Path, body: dict[str, str]) -> str:
    place = tmp_path / "input.json"
    place.write_text(json.dumps(body), encoding="utf-8")
    return str(place)


def _extra_cursor_component() -> FirstPartyCatalogMember:
    base = catalog_identity("cursor", "baseline")
    full = catalog_identity("cursor", "full-auto")
    held = {item.stable_id for item in base.component_refs}
    return next(item for item in full.component_refs if item.stable_id not in held)


def _component_ref(item: FirstPartyCatalogMember) -> ComponentRef:
    return ComponentRef(
        stable_id=item.stable_id,
        version=item.version,
        passport_digest=item.passport_digest,
    )


def _baseline_member() -> ComponentRef:
    return _component_ref(catalog_identity("cursor", "baseline").component_refs[0])


def _source_catalog(source: SetupVersionPassport) -> tuple[setup_compose.CatalogMaterial, ...]:
    materials: list[setup_compose.CatalogMaterial] = []
    for member in source.components:
        item = setup_derive.corpus_item("component", member.stable_id, member.version)
        assert item is not None
        materials.append(setup_derive.catalog_material(item, variant_id=member.variant_id))
    return tuple(materials)
