# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportPrivateUsage=false, reportArgumentType=false
"""Explicit embedded update keeps the old setup selected until confirm (REQ-5712, REQ-5716)."""

from __future__ import annotations

from contextlib import closing
from typing import cast

import pytest

from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, content, embedded_update, revisions, selection, versions
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_contracts.first_party import FirstPartyVersion
from ai_stp_contracts.first_party import family as corpus_family
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_sources.definition import DEFINITION_V2, EmbeddedDraft, freeze_setup_definition
from ai_stp_sources.models import SourceSnapshot

EMBEDDED_A = "component_01ARZ3NDEKTSV4RRFFQ69G5FAW"
EMBEDDED_B = "component_01ARZ3NDEKTSV4RRFFQ69G5FAX"
PROJECT = "project_01ARZ3NDEKTSV4RRFFQ69G5FAV"
DEVICE = "device_test"
AT = "2026-09-01T00:00:00.000Z"
DIGEST = "sha256:" + "b" * 64


def _grok() -> tuple[tuple[FirstPartyVersion, ...], FirstPartyVersion]:
    family = list(corpus_family("grok-build", "nddev-builder"))
    components = tuple(item for item in family if item.kind == "component")
    (setup,) = [item for item in family if item.kind == "setup"]
    return components, setup


def _draft(stable_id: str, name: str, body: bytes) -> EmbeddedDraft:
    return EmbeddedDraft(
        snapshot=SourceSnapshot(
            kind="path",
            canonical_coordinate=f"path:skills/{name}",
            exact_identity=f"skills/{name}",
            component_digest=DIGEST,
            files={f"{name}/SKILL.md": body},
        ),
        component_type="skill",
        name=name,
        description="Embedded skill used for explicit update tests.",
        license_spdx="MIT",
        harness_id="grok-build",
        stable_id=stable_id,
        managed_paths=(f"skills/{name}/SKILL.md",),
    )


def _store_setup(*, two_named_demo: bool = False) -> tuple[str, str, str]:
    components, setup = _grok()
    catalog_refs = tuple(
        ComponentRef(
            stable_id=item.passport.stable_id,
            version=item.passport.version,
            passport_digest=item.passport_digest,
        )
        for item in components
    )
    embedded = (
        (
            _draft(EMBEDDED_A, "demo", b"# Demo A\n"),
            _draft(EMBEDDED_B, "demo", b"# Demo B\n"),
        )
        if two_named_demo
        else (_draft(EMBEDDED_A, "demo", b"# Demo A\n"),)
    )
    frozen = freeze_setup_definition(
        setup_id=setup.passport.stable_id,
        version=setup.passport.version,
        harness_id=setup.passport.harness_id,
        input_digest=DIGEST,
        publisher_id=setup.passport.owner_id,
        created_at=AT,
        catalog_members=catalog_refs,
        embedded_members=embedded,
        catalog_ids=frozenset(item.passport.stable_id for item in components),
    )
    document = cast(dict[str, JsonValue], setup.passport.model_dump(mode="json"))
    document["components"] = frozen.document["components"]
    document["artifact"] = {
        "digest": digest_bytes("ai-stp:artifact:v1", frozen.payload),
        "size_bytes": len(frozen.payload),
    }
    document["artifact_format"] = DEFINITION_V2
    facts = document.get("facts")
    if isinstance(facts, dict):
        members = facts.get("members")
        if isinstance(members, dict):
            members["value"] = frozen.document["components"]
    document.pop("revision_id", None)
    document["revision_id"] = derive_revision_id(document)
    document.pop("revision_id", None)
    with closing(open_registry(configured_path(), create=True)) as connection:
        content.put(connection, frozen.payload, at=AT)
        stored = revisions.commit(connection, document, device_id=DEVICE)
        versions.record(
            connection,
            stable_id=setup.passport.stable_id,
            version=setup.passport.version,
            passport_digest=cache.digest_of(
                cast(JsonValue, stored.envelope.model_dump(mode="json"))
            ),
            revision_id=stored.revision_id,
            at=AT,
        )
        connection.execute(
            "INSERT INTO entity (stable_id, kind, created_at) VALUES (?, 'project', ?)",
            (PROJECT, AT),
        )
        connection.execute(
            """
            INSERT INTO selected_version
                (project_id, harness_id, stable_id, version, state, selected_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                PROJECT,
                setup.passport.harness_id,
                setup.passport.stable_id,
                setup.passport.version,
                selection.PENDING_INSTALL,
                AT,
            ),
        )
        connection.commit()
    return setup.passport.stable_id, setup.passport.version, setup.passport.harness_id


def _newer_snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        kind="path",
        canonical_coordinate="path:skills/demo",
        exact_identity="skills/demo",
        component_digest=DIGEST,
        files={"demo/SKILL.md": b"# Demo A updated\n"},
    )


def test_plan_does_not_change_selected_setup() -> None:
    setup_id, version, harness = _store_setup()
    with closing(open_registry(configured_path(), create=True)) as connection:
        planned = embedded_update.plan(
            connection,
            setup_id=setup_id,
            version=version,
            component_id=EMBEDDED_A,
            snapshot=_newer_snapshot(),
            project_id=PROJECT,
            harness_id=harness,
            at=AT,
        )
        pinned = selection.selected(connection, project_id=PROJECT, harness_id=harness)
    assert planned.from_version == version
    assert planned.to_version != version
    assert pinned == (setup_id, version, selection.PENDING_INSTALL)


def test_apply_without_confirm_leaves_old_version_selected() -> None:
    setup_id, version, harness = _store_setup()
    with closing(open_registry(configured_path(), create=True)) as connection:
        planned = embedded_update.plan(
            connection,
            setup_id=setup_id,
            version=version,
            component_id=EMBEDDED_A,
            snapshot=_newer_snapshot(),
            project_id=PROJECT,
            harness_id=harness,
            at=AT,
        )
        with pytest.raises(CliFailure, match="setup update apply requires explicit confirmation"):
            embedded_update.apply(
                connection,
                setup_id=setup_id,
                version=version,
                component_id=EMBEDDED_A,
                snapshot=_newer_snapshot(),
                project_id=PROJECT,
                harness_id=harness,
                expected_plan_digest=planned.plan_digest,
                device_id=DEVICE,
                at=AT,
                confirm=False,
            )
        pinned = selection.selected(connection, project_id=PROJECT, harness_id=harness)
        assert versions.held(connection, setup_id, planned.to_version) is None
    assert pinned == (setup_id, version, selection.PENDING_INSTALL)


def test_confirmed_apply_creates_new_immutable_version_and_selects_it() -> None:
    setup_id, version, harness = _store_setup()
    with closing(open_registry(configured_path(), create=True)) as connection:
        planned = embedded_update.plan(
            connection,
            setup_id=setup_id,
            version=version,
            component_id=EMBEDDED_A,
            snapshot=_newer_snapshot(),
            project_id=PROJECT,
            harness_id=harness,
            at=AT,
        )
        result = embedded_update.apply(
            connection,
            setup_id=setup_id,
            version=version,
            component_id=EMBEDDED_A,
            snapshot=_newer_snapshot(),
            project_id=PROJECT,
            harness_id=harness,
            expected_plan_digest=planned.plan_digest,
            device_id=DEVICE,
            at=AT,
            confirm=True,
        )
        pinned = selection.selected(connection, project_id=PROJECT, harness_id=harness)
        recorded = versions.held(connection, setup_id, result.to_version)
        old = versions.held(connection, setup_id, version)
    assert result.created is True
    assert result.from_version == version
    assert result.to_version != version
    assert pinned == (setup_id, result.to_version, selection.PENDING_INSTALL)
    assert recorded is not None
    assert old is not None
    assert old.passport_digest != recorded.passport_digest


def test_update_rejects_a_display_name_and_keeps_equal_names_distinct() -> None:
    setup_id, version, harness = _store_setup(two_named_demo=True)
    with closing(open_registry(configured_path(), create=True)) as connection:
        with pytest.raises(
            CliFailure, match="the update requires an exact component identifier, not a name"
        ):
            embedded_update.plan(
                connection,
                setup_id=setup_id,
                version=version,
                component_id="demo",
                snapshot=_newer_snapshot(),
                project_id=PROJECT,
                harness_id=harness,
                at=AT,
            )
        planned = embedded_update.plan(
            connection,
            setup_id=setup_id,
            version=version,
            component_id=EMBEDDED_A,
            snapshot=_newer_snapshot(),
            project_id=PROJECT,
            harness_id=harness,
            at=AT,
        )
        embedded_update.apply(
            connection,
            setup_id=setup_id,
            version=version,
            component_id=EMBEDDED_A,
            snapshot=_newer_snapshot(),
            project_id=PROJECT,
            harness_id=harness,
            expected_plan_digest=planned.plan_digest,
            device_id=DEVICE,
            at=AT,
            confirm=True,
        )
        from ai_stp_sources.definition import try_parse_setup_definition

        recorded = versions.held(connection, setup_id, planned.to_version)
        assert recorded is not None
        stored = revisions.get(connection, recorded.revision_id)
        assert stored is not None
        artifact = stored.envelope.model_dump(mode="json")["artifact"]
        definition = try_parse_setup_definition(content.get(connection, str(artifact["digest"])))
        assert definition is not None
        embedded = definition["embedded"]
        assert isinstance(embedded, list)
        ids = sorted(
            str(cast(dict[str, object], item["ref"])["stable_id"])
            for item in embedded
            if isinstance(item, dict)
        )
        assert ids == [EMBEDDED_A, EMBEDDED_B]
        names = [
            str(cast(dict[str, object], item["passport"])["name"])
            for item in embedded
            if isinstance(item, dict)
        ]
        assert names.count("demo") == 2


def test_matching_catalog_is_a_dismissible_suggestion_and_apply_keeps_embedded_id() -> None:
    from ai_stp_cli.local.catalog_replacement import (
        CatalogMatchInput,
        artifact_digest_for_snapshot,
    )

    setup_id, version, harness = _store_setup()
    snapshot = _newer_snapshot()
    digest = artifact_digest_for_snapshot(snapshot)
    catalog = (
        CatalogMatchInput(
            stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAY",
            version="2.0",
            canonical_coordinate=snapshot.canonical_coordinate,
            artifact_digest=digest,
        ),
    )
    with closing(open_registry(configured_path(), create=True)) as connection:
        planned = embedded_update.plan(
            connection,
            setup_id=setup_id,
            version=version,
            component_id=EMBEDDED_A,
            snapshot=snapshot,
            project_id=PROJECT,
            harness_id=harness,
            at=AT,
            catalog=catalog,
        )
        assert planned.suggested_catalog_dismissible is True
        assert planned.suggested_catalog_stable_id == "component_01ARZ3NDEKTSV4RRFFQ69G5FAY"
        result = embedded_update.apply(
            connection,
            setup_id=setup_id,
            version=version,
            component_id=EMBEDDED_A,
            snapshot=snapshot,
            project_id=PROJECT,
            harness_id=harness,
            expected_plan_digest=planned.plan_digest,
            device_id=DEVICE,
            at=AT,
            confirm=True,
        )
        from ai_stp_sources.definition import try_parse_setup_definition

        recorded = versions.held(connection, setup_id, result.to_version)
        assert recorded is not None
        stored = revisions.get(connection, recorded.revision_id)
        assert stored is not None
        artifact = stored.envelope.model_dump(mode="json")["artifact"]
        definition = try_parse_setup_definition(content.get(connection, str(artifact["digest"])))
        assert definition is not None
        embedded = definition["embedded"]
        assert isinstance(embedded, list)
        ids = [
            str(cast(dict[str, object], item["ref"])["stable_id"])
            for item in embedded
            if isinstance(item, dict)
        ]
        assert EMBEDDED_A in ids
        assert "component_01ARZ3NDEKTSV4RRFFQ69G5FAY" not in ids
