"""Setup-definition freeze (SPEC-057 REQ-5705, REQ-5706, REQ-5707, REQ-5718)."""

from __future__ import annotations

from typing import cast

import pytest

from ai_stp_foundation.canonical import JsonValue, canonize, from_json_bytes
from ai_stp_foundation.refs import ComponentRef
from ai_stp_passports.versions import ComponentType, ComponentVersionPassport
from ai_stp_sources import (
    CATALOG_COLLISION,
    DEFINITION_V1,
    DEFINITION_V2,
    INCOMPLETE_PASSPORT,
    INTEGRITY_MISMATCH,
    INVALID_SOURCE,
    UNSAFE_ARCHIVE,
    EmbeddedDraft,
    NpmEvidence,
    SourceError,
    SourceSnapshot,
    freeze_setup_definition,
    validate_setup_definition,
)
from ai_stp_sources.definition import MAX_DEFINITION_BYTES

OWNER = "account_01ARZ3NDEKTSV4RRFFQ69G5FAV"
SETUP = "setup_01ARZ3NDEKTSV4RRFFQ69G5FAV"
CATALOG_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAV"
EMBEDDED_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAW"
PATH_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAX"
PACKAGE_ID = "component_01ARZ3NDEKTSV4RRFFQ69G5FAY"
DIGEST = "sha256:" + "b" * 64
AT = "2026-09-01T00:00:00.000Z"
COMMIT = "a" * 40
KINDS: tuple[ComponentType, ...] = (
    "instruction",
    "skill",
    "mcp",
    "hook",
    "command",
    "agent",
    "plugin",
    "setting",
)


def _catalog_ref() -> ComponentRef:
    return ComponentRef(stable_id=CATALOG_ID, version="1.0", passport_digest=DIGEST)


def _git_snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        kind="git",
        canonical_coordinate=f"git:https://github.com/acme/tool@{COMMIT}:skills/demo",
        exact_identity=COMMIT,
        archive_digest=DIGEST,
        component_digest=DIGEST,
        subpath="skills/demo",
        repository_url="https://github.com/acme/tool",
        github_owner="acme",
        github_name="tool",
        files={"SKILL.md": b"# Demo\n"},
    )


def _path_snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        kind="path",
        canonical_coordinate="path:skills/demo",
        exact_identity="skills/demo",
        component_digest=DIGEST,
        files={"SKILL.md": b"# Local\n"},
    )


def _package_snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        kind="package",
        canonical_coordinate="package:npm:demo@1.2.3",
        exact_identity="1.2.3",
        archive_digest=DIGEST,
        component_digest=DIGEST,
        files={"package.json": b'{"name":"demo"}\n'},
        package_evidence=NpmEvidence(lockfile_name="package-lock.json"),
    )


def _draft(
    snapshot: SourceSnapshot,
    *,
    stable_id: str | None,
    component_type: ComponentType = "skill",
    name: str = "demo",
) -> EmbeddedDraft:
    return EmbeddedDraft(
        snapshot=snapshot,
        component_type=component_type,
        name=name,
        description="Embedded component used in a mixed setup.",
        license_spdx="MIT",
        harness_id="claude-code",
        stable_id=stable_id,
        managed_paths=("skills/demo/SKILL.md",),
        upstream_project="acme/tool",
        upstream_maintainers=("acme",),
    )


def _freeze(
    *,
    catalog: tuple[ComponentRef, ...] = (),
    embedded: tuple[EmbeddedDraft, ...] = (),
    catalog_ids: frozenset[str] | None = None,
    known: dict[str, str] | None = None,
):
    return freeze_setup_definition(
        setup_id=SETUP,
        version="1.0",
        harness_id="claude-code",
        input_digest=DIGEST,
        publisher_id=OWNER,
        created_at=AT,
        catalog_members=catalog,
        embedded_members=embedded,
        catalog_ids=catalog_ids or frozenset(),
        known_identities=known,
    )


def test_catalog_only_freeze_stays_definition_version_1() -> None:
    frozen = _freeze(catalog=(_catalog_ref(),), catalog_ids=frozenset({CATALOG_ID}))
    assert frozen.format == DEFINITION_V1
    document = from_json_bytes(frozen.payload)
    assert isinstance(document, dict)
    assert document == {
        "schema_version": 1,
        "format": DEFINITION_V1,
        "stable_id": SETUP,
        "version": "1.0",
        "harness_id": "claude-code",
        "input_digest": DIGEST,
        "components": [
            {
                "stable_id": CATALOG_ID,
                "version": "1.0",
                "passport_digest": DIGEST,
            }
        ],
    }
    assert "embedded" not in document
    assert frozen.payload == canonize(cast(JsonValue, document))


def test_cli_authoring_uses_the_shared_freeze() -> None:
    from ai_stp_cli.local.embedded import author_mixed_setup, local_component_identity

    known: dict[str, str] = {}
    assert local_component_identity(known, "k") == local_component_identity(known, "k")
    frozen = author_mixed_setup(
        setup_id=SETUP,
        version="1.0",
        harness_id="claude-code",
        input_digest=DIGEST,
        publisher_id=OWNER,
        created_at=AT,
        catalog_members=(_catalog_ref(),),
        embedded_members=(),
        catalog_ids=frozenset({CATALOG_ID}),
    )
    assert frozen.format == DEFINITION_V1


def test_mixed_freeze_uses_definition_version_2_and_exact_refs() -> None:
    frozen = _freeze(
        catalog=(_catalog_ref(),),
        embedded=(
            _draft(_git_snapshot(), stable_id=EMBEDDED_ID),
            _draft(_path_snapshot(), stable_id=PATH_ID, name="local-demo"),
            _draft(_package_snapshot(), stable_id=PACKAGE_ID, name="pkg-demo"),
        ),
        catalog_ids=frozenset({CATALOG_ID}),
    )
    assert frozen.format == DEFINITION_V2
    document = from_json_bytes(frozen.payload)
    assert isinstance(document, dict)
    assert document["format"] == DEFINITION_V2
    assert document["schema_version"] == 2
    embedded = document["embedded"]
    assert isinstance(embedded, list)
    assert len(embedded) == 3
    ids = [
        str(cast(dict[str, JsonValue], cast(dict[str, JsonValue], item)["ref"])["stable_id"])
        for item in embedded
    ]
    assert ids == sorted(ids)
    git_record = next(
        item
        for item in embedded
        if cast(dict[str, JsonValue], cast(dict[str, JsonValue], item)["ref"])["stable_id"]
        == EMBEDDED_ID
    )
    assert isinstance(git_record, dict)
    passport = ComponentVersionPassport.model_validate(git_record["passport"])
    assert passport.owner_id == OWNER
    assert passport.component_type == "skill"
    assert passport.source is not None
    assert passport.source.repository == "https://github.com/acme/tool"
    assert "reactions" not in passport.model_dump(mode="json")
    assert passport.facts["upstream_project"].value == "acme/tool"
    snapshot = git_record["snapshot"]
    assert isinstance(snapshot, dict)
    assert "files" not in snapshot
    assert "\\" not in str(snapshot["canonical_coordinate"])
    validate_setup_definition(frozen.payload, catalog_ids=frozenset({CATALOG_ID}))


@pytest.mark.parametrize("component_type", KINDS)
def test_embedded_passport_covers_each_component_kind(component_type: ComponentType) -> None:
    frozen = _freeze(
        embedded=(_draft(_path_snapshot(), stable_id=PATH_ID, component_type=component_type),)
    )
    document = from_json_bytes(frozen.payload)
    assert isinstance(document, dict)
    record = cast(list[object], document["embedded"])[0]
    assert isinstance(record, dict)
    passport = ComponentVersionPassport.model_validate(record["passport"])
    assert passport.component_type == component_type
    assert passport.requires_components == []
    assert passport.license.spdx_id == "MIT"


def test_same_source_reuses_local_identity() -> None:
    first = _freeze(embedded=(_draft(_git_snapshot(), stable_id=EMBEDDED_ID),))
    second = _freeze(
        embedded=(_draft(_git_snapshot(), stable_id=None),),
        known=first.identities,
    )
    assert second.components[0].stable_id == EMBEDDED_ID
    assert len(cast(list[object], second.document["embedded"])) == 1


def test_catalog_identity_collision_fails_closed() -> None:
    with pytest.raises(SourceError) as raised:
        _freeze(
            catalog=(_catalog_ref(),),
            embedded=(_draft(_git_snapshot(), stable_id=CATALOG_ID),),
            catalog_ids=frozenset({CATALOG_ID}),
        )
    assert raised.value.code == CATALOG_COLLISION


def test_duplicate_ref_with_different_bytes_fails_closed() -> None:
    other = SourceSnapshot(
        kind="path",
        canonical_coordinate="path:skills/other",
        exact_identity="skills/other",
        component_digest=DIGEST,
        files={"OTHER.md": b"# Other\n"},
    )
    with pytest.raises(SourceError) as raised:
        _freeze(
            embedded=(
                _draft(_path_snapshot(), stable_id=PATH_ID),
                _draft(other, stable_id=PATH_ID, name="other"),
            )
        )
    assert raised.value.code == INTEGRITY_MISMATCH


def test_unknown_field_and_digest_mismatch_fail_closed() -> None:
    frozen = _freeze(embedded=(_draft(_path_snapshot(), stable_id=PATH_ID),))
    document = from_json_bytes(frozen.payload)
    assert isinstance(document, dict)
    document["unexpected"] = True
    with pytest.raises(SourceError) as unknown:
        validate_setup_definition(canonize(cast(JsonValue, document)))
    assert unknown.value.code == INVALID_SOURCE

    embedded = cast(list[object], document["embedded"])
    record = cast(dict[str, JsonValue], embedded[0])
    del document["unexpected"]
    record["artifact_digest"] = "sha256:" + "c" * 64
    with pytest.raises(SourceError) as mismatch:
        validate_setup_definition(canonize(cast(JsonValue, document)))
    assert mismatch.value.code == INTEGRITY_MISMATCH


def test_incomplete_passport_and_unbounded_payload_fail_closed() -> None:
    with pytest.raises(SourceError) as incomplete:
        _freeze(
            embedded=(
                EmbeddedDraft(
                    snapshot=_path_snapshot(),
                    component_type="skill",
                    name="",
                    description="x",
                    license_spdx="MIT",
                    harness_id="claude-code",
                    stable_id=PATH_ID,
                    tags=(),
                ),
            )
        )
    assert incomplete.value.code == INCOMPLETE_PASSPORT

    with pytest.raises(SourceError) as bounds:
        validate_setup_definition(b"{" + b"x" * (MAX_DEFINITION_BYTES + 1))
    assert bounds.value.code == UNSAFE_ARCHIVE


def test_secret_file_and_absolute_path_fail_closed() -> None:
    secret = SourceSnapshot(
        kind="path",
        canonical_coordinate="path:skills/demo",
        exact_identity="skills/demo",
        component_digest=DIGEST,
        files={".env": b"TOKEN=1\n"},
    )
    with pytest.raises(SourceError) as unsafe:
        _freeze(embedded=(_draft(secret, stable_id=PATH_ID),))
    assert unsafe.value.code == UNSAFE_ARCHIVE

    absolute = SourceSnapshot(
        kind="path",
        canonical_coordinate="path:/tmp/demo",
        exact_identity="/tmp/demo",
        component_digest=DIGEST,
        files={"SKILL.md": b"# Demo\n"},
    )
    with pytest.raises(SourceError) as invalid:
        _freeze(embedded=(_draft(absolute, stable_id=PATH_ID),))
    assert invalid.value.code == INVALID_SOURCE
