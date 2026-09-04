# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportPrivateUsage=false, reportPrivateImportUsage=false, reportArgumentType=false
"""Explicit from-setup promotion reuses or mints identity and never runs on setup publish."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import cast

import pytest

from ai_stp_cli.commands import component_publish, setup_publication
from ai_stp_cli.errors import CliFailure
from ai_stp_cli.local import cache, content, embedded_promotion, revisions, versions
from ai_stp_cli.local.database import configured_path, open_registry
from ai_stp_cli.local.embedded_promotion import _public_fields_complete
from ai_stp_contracts.first_party import FirstPartyVersion
from ai_stp_contracts.first_party import family as corpus_family
from ai_stp_foundation.canonical import JsonValue
from ai_stp_foundation.digests import digest_bytes
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports.envelope import derive_revision_id
from ai_stp_passports.versions import SetupVersionPassport
from ai_stp_sources.definition import DEFINITION_V2, EmbeddedDraft, freeze_setup_definition
from ai_stp_sources.models import SourceSnapshot

pytestmark = pytest.mark.cli

EMBEDDED_A = "component_01ARZ3NDEKTSV4RRFFQ69G5FAW"
PROJECT = "project_01ARZ3NDEKTSV4RRFFQ69G5FAV"
DEVICE = "device_test"
AT = "2026-09-01T00:00:00.000Z"
DIGEST = "sha256:" + "b" * 64
COMMIT = "a" * 40


def _grok() -> tuple[tuple[FirstPartyVersion, ...], FirstPartyVersion]:
    family = list(corpus_family("grok-build", "nddev-builder"))
    components = tuple(item for item in family if item.kind == "component")
    (setup,) = [item for item in family if item.kind == "setup"]
    return components, setup


def _path_draft(
    stable_id: str, name: str, body: bytes, *, redistribute: bool = False
) -> EmbeddedDraft:
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
        description="Embedded skill used for explicit promotion tests.",
        license_spdx="MIT",
        harness_id="grok-build",
        target_scope="global",
        redistribution_allowed=redistribute,
        stable_id=stable_id,
        managed_paths=(f"skills/{name}/SKILL.md",),
    )


def _git_draft(stable_id: str, name: str, body: bytes) -> EmbeddedDraft:
    return EmbeddedDraft(
        snapshot=SourceSnapshot(
            kind="git",
            canonical_coordinate=f"https://github.com/example/demo@{COMMIT}",
            exact_identity=COMMIT,
            component_digest=DIGEST,
            archive_digest=DIGEST,
            repository_url="https://github.com/example/demo",
            subpath=f"skills/{name}",
            files={f"{name}/SKILL.md": body},
        ),
        component_type="skill",
        name=name,
        description="Embedded skill used for explicit promotion tests.",
        license_spdx="MIT",
        harness_id="grok-build",
        target_scope="global",
        redistribution_allowed=True,
        stable_id=stable_id,
        managed_paths=(f"skills/{name}/SKILL.md",),
    )


def _setup_artifact_digest(connection: sqlite3.Connection, setup_id: str, version: str) -> str:
    held = versions.held(connection, setup_id, version)
    assert held is not None
    stored = revisions.get(connection, held.revision_id)
    assert stored is not None
    artifact = stored.envelope.model_dump(mode="json")["artifact"]
    assert isinstance(artifact, dict)
    return str(artifact["digest"])


def _store_setup(*, complete: bool = False) -> tuple[str, str]:
    components, setup = _grok()
    catalog_refs = tuple(
        ComponentRef(
            stable_id=item.passport.stable_id,
            version=item.passport.version,
            passport_digest=item.passport_digest,
        )
        for item in components
    )
    draft = (
        _git_draft(EMBEDDED_A, "demo", b"# Demo A\n")
        if complete
        else _path_draft(EMBEDDED_A, "demo", b"# Demo A\n")
    )
    assert isinstance(setup.passport, SetupVersionPassport)
    frozen = freeze_setup_definition(
        setup_id=setup.passport.stable_id,
        version=setup.passport.version,
        harness_id=setup.passport.harness_id,
        input_digest=DIGEST,
        publisher_id=setup.passport.owner_id,
        created_at=AT,
        catalog_members=catalog_refs,
        embedded_members=(draft,),
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
        connection.commit()
    return setup.passport.stable_id, setup.passport.version


def test_incomplete_embedded_passport_mints_a_new_catalog_identity() -> None:
    setup_id, version = _store_setup(complete=False)
    with closing(open_registry(configured_path(), create=True)) as connection:
        result = embedded_promotion.materialize(
            connection,
            setup_id=setup_id,
            version=version,
            component_id=EMBEDDED_A,
            device_id=DEVICE,
            at=AT,
        )
        recorded = versions.held(connection, result.catalog_stable_id, result.catalog_version)
        remaining = embedded_promotion.embedded_component_ids(
            connection, _setup_artifact_digest(connection, setup_id, version)
        )
    assert result.reused_passport is False
    assert result.catalog_stable_id != EMBEDDED_A
    assert result.catalog_version == "1.0"
    assert result.still_embedded is True
    assert EMBEDDED_A in remaining
    assert recorded is not None


def test_complete_embedded_passport_reuses_the_exact_identity() -> None:
    setup_id, version = _store_setup(complete=True)
    with closing(open_registry(configured_path(), create=True)) as connection:
        result = embedded_promotion.materialize(
            connection,
            setup_id=setup_id,
            version=version,
            component_id=EMBEDDED_A,
            device_id=DEVICE,
            at=AT,
        )
        remaining = embedded_promotion.embedded_component_ids(
            connection, _setup_artifact_digest(connection, setup_id, version)
        )
    assert result.reused_passport is True
    assert result.catalog_stable_id == EMBEDDED_A
    assert result.still_embedded is True
    assert EMBEDDED_A in remaining


def test_public_fields_gate_requires_license_and_source() -> None:
    incomplete: dict[str, JsonValue] = {
        "owner_id": "account_01KZET6ZKJN7S72T5H4WDV62T0",
        "name": "demo",
        "description": "desc",
        "source": {"repository": "https://github.com/example/demo"},
        "license": {"spdx_id": "MIT", "redistribution_allowed": False},
    }
    complete: dict[str, JsonValue] = {
        **incomplete,
        "license": {"spdx_id": "MIT", "redistribution_allowed": True},
    }
    assert _public_fields_complete(incomplete) is False
    assert _public_fields_complete(complete) is True


class _Plan:
    def __init__(self) -> None:
        self.plan_id = "plan_01ARZ3NDEKTSV4RRFFQ69G5FAW"
        self.plan_hash = "sha256:" + "c" * 64
        self.state = "draft"


class _Answer:
    def __init__(self, payload: _Plan) -> None:
        self.payload = payload


def test_component_publish_enters_ordinary_publication_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup_id, version = _store_setup(complete=False)
    captured: dict[str, object] = {}

    def _plan(parameters: dict[str, object]) -> _Answer:
        captured.update(parameters)
        return _Answer(_Plan())

    monkeypatch.setattr(component_publish.publication, "plan", _plan)
    answer = component_publish.publish(
        {
            "from-setup": setup_id,
            "setup-version": version,
            "component-id": EMBEDDED_A,
        }
    )
    assert answer.payload.still_embedded is True
    assert answer.payload.reused_passport is False
    assert captured["id"] == answer.payload.catalog_stable_id
    assert captured["version"] == answer.payload.catalog_version
    assert answer.payload.plan_id.startswith("plan_")


def test_component_publish_requires_setup_version_and_component_id() -> None:
    with pytest.raises(CliFailure, match="a setup identifier, version, and exact component id"):
        component_publish.publish({"from-setup": "", "setup-version": "", "component-id": ""})


def test_setup_publication_does_not_plan_embedded_members() -> None:
    setup_id, version = _store_setup(complete=False)
    with closing(open_registry(configured_path(), create=True)) as connection:
        setup = setup_publication._setup_passport(connection, setup_id, version)
        pins = setup_publication._catalog_pins(connection, setup)
        all_ids = {ref.stable_id for ref in setup.components}
    pin_ids = {stable_id for stable_id, _version in pins}
    assert EMBEDDED_A in all_ids
    assert EMBEDDED_A not in pin_ids
    assert pin_ids
