"""Qualified OpenCode path IDs coexist with exact retained 1.x declarations."""

from typing import cast

import pytest

from ai_stp_foundation.canonical import JsonValue
from ai_stp_passports import ComponentVersionPassport
from ai_stp_sources import EmbeddedDraft, SourceError, SourceSnapshot, freeze_setup_definition
from ai_stp_sources.native_identity import identities

FORMAT = "ai-stp-adaptation-projection/2"


def current(files: dict[str, bytes]) -> dict[str, list[str]]:
    return identities("opencode", "skill", files, projection_format=FORMAT)


@pytest.mark.parametrize(
    "payload",
    [
        b"Controlled fixture.\n",
        b"---\nname: Display name\n---\nControlled fixture.\n",
        b"---\ndescription: Controlled\n---\nControlled fixture.\n",
        b"---\nname: ''\ndescription: ''\n---\nControlled fixture.\n",
        b"---\n---\nControlled fixture.\n",
    ],
)
def test_current_skill_identity_comes_from_its_path(payload: bytes) -> None:
    assert current({"skills/path-name/SKILL.md": payload}) == {
        "skills/path-name/SKILL.md": ["path-name"]
    }


def test_retained_declaration_does_not_switch_to_current_path_semantics() -> None:
    files = {"skills/path-name/SKILL.md": b"---\nname: Display name\n---\nFixture.\n"}
    assert identities("opencode", "skill", files) == {"skills/path-name/SKILL.md": ["Display name"]}
    assert current(files) == {"skills/path-name/SKILL.md": ["path-name"]}


def test_parent_skill_blocks_children_and_sidecars_have_no_names() -> None:
    files = {
        "skills/parent/SKILL.md": b"Controlled fixture.\n",
        "skills/parent/README.md": b"Controlled sidecar.\n",
        "skills/parent/child/SKILL.md": b"Controlled blocked skill.\n",
    }
    assert current(files) == {
        "skills/parent/SKILL.md": ["parent"],
        "skills/parent/README.md": [],
        "skills/parent/child/SKILL.md": [],
    }


def test_scan_uses_flat_paths_ignored_directories_and_depth_six() -> None:
    files = {
        "skills/flat.md": b"Fixture.\n",
        "skills/a/b/c/d/e/depth-six/SKILL.md": b"Fixture.\n",
        "skills/a/b/c/d/e/f/depth-seven/SKILL.md": b"Fixture.\n",
        "skills/.hidden/hidden/SKILL.md": b"Fixture.\n",
        "skills/node_modules/dependency/SKILL.md": b"Fixture.\n",
        "skills/category/ignored.md": b"Fixture.\n",
    }
    result = current(files)
    assert {path: values for path, values in result.items() if values} == {
        "skills/flat.md": ["flat"],
        "skills/a/b/c/d/e/depth-six/SKILL.md": ["depth-six"],
    }


def test_duplicate_display_names_do_not_conflict_but_duplicate_ids_do() -> None:
    payload = b"---\nname: Shared display\n---\nFixture.\n"
    assert current({"skills/first/SKILL.md": payload, "skills/second/SKILL.md": payload}) == {
        "skills/first/SKILL.md": ["first"],
        "skills/second/SKILL.md": ["second"],
    }
    with pytest.raises(SourceError):
        current({"skills/a/same/SKILL.md": payload, "skills/b/same/SKILL.md": payload})


@pytest.mark.parametrize("field", ["name", "description"])
def test_numeric_optional_fields_refuse_authoring(field: str) -> None:
    with pytest.raises(SourceError):
        current({"skills/path/SKILL.md": f"---\n{field}: 123\n---\nFixture.\n".encode()})


def test_current_format_cannot_reinterpret_other_harnesses_or_kinds() -> None:
    for harness, kind in [("codex", "skill"), ("opencode", "agent"), ("opencode", "command")]:
        with pytest.raises(SourceError):
            identities(
                harness, kind, {"skills/path/SKILL.md": b"Fixture.\n"}, projection_format=FORMAT
            )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("skills/SKILL.md", "skills"),
        ("skill/SKILL.md", "skill"),
        (".opencode/skill/SKILL.md", "skill"),
        (".agents/skills/SKILL.md", "skills"),
    ],
)
def test_root_skill_uses_the_actual_native_directory_name(path: str, expected: str) -> None:
    assert current({path: b"Controlled fixture.\n"}) == {path: [expected]}


def test_public_embedded_writer_and_retained_reader_keep_the_same_exact_projection() -> None:
    snapshot = SourceSnapshot(
        kind="path",
        canonical_coordinate="path:skills/source",
        exact_identity="skills/source",
        component_digest="sha256:" + "a" * 64,
        files={
            "SKILL.md": b"---\nname: Display name\n---\nControlled fixture.\n",
            "README.md": b"Controlled sidecar.\n",
        },
    )
    draft = EmbeddedDraft(
        snapshot=snapshot,
        component_type="skill",
        name="folder",
        description="Controlled fixture",
        license_spdx="MIT",
        harness_id="opencode",
        target_scope="global",
        managed_paths=("skills/folder/README.md", "skills/folder/SKILL.md"),
    )

    def freeze(members: tuple[EmbeddedDraft, ...], retained: tuple[dict[str, JsonValue], ...] = ()):
        return freeze_setup_definition(
            setup_id="setup_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            version="1.0",
            harness_id="opencode",
            input_digest="sha256:" + "b" * 64,
            publisher_id="account_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            created_at="2026-11-12T00:00:00.000Z",
            catalog_members=(),
            embedded_members=members,
            retained_embedded=retained,
        )

    first = freeze((draft,))
    records = cast(list[dict[str, JsonValue]], first.document["embedded"])
    passport = ComponentVersionPassport.model_validate(records[0]["passport"])
    scope = passport.adaptations[0].scope_adaptations[0]
    assert scope.projection_format == FORMAT
    assert scope.supported_harness_versions == ["2.2.7"]
    assert {member.path: member.native_ids for member in scope.members} == {
        "skills/folder/SKILL.md": ["folder"],
        "skills/folder/README.md": [],
    }
    assert freeze((), (records[0],)).document["embedded"] == first.document["embedded"]
