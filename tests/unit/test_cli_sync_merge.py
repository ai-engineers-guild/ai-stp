"""Local sync merges fields without last-write-wins or lost changes."""

from copy import deepcopy

from hypothesis import given
from hypothesis import strategies as st

from ai_stp_cli.local.sync_merge import merge_documents
from ai_stp_foundation.canonical import JsonValue


def test_one_sided_and_independent_changes_merge() -> None:
    outcome = merge_documents(
        {"profile": {"theme": "dark", "role": "backend"}, "kept": True},
        {"profile": {"theme": "light", "role": "backend"}, "kept": True},
        {"profile": {"theme": "dark", "role": "frontend"}, "kept": True},
    )

    assert outcome.conflicts == ()
    assert outcome.document == {
        "kept": True,
        "profile": {"role": "frontend", "theme": "light"},
    }


def test_same_field_change_is_an_explicit_conflict() -> None:
    outcome = merge_documents({"role": "fullstack"}, {"role": "backend"}, {"role": "frontend"})

    assert outcome.document is None
    assert [conflict.path for conflict in outcome.conflicts] == ["/role"]
    conflict = outcome.conflicts[0]
    assert conflict.base.value == "fullstack"
    assert conflict.local.value == "backend"
    assert conflict.remote.value == "frontend"


def test_delete_and_edit_conflict_but_unchanged_peer_accepts_delete() -> None:
    conflict = merge_documents({"role": "backend"}, {}, {"role": "frontend"})
    deleted = merge_documents({"role": "backend"}, {}, {"role": "backend"})

    assert conflict.document is None
    assert conflict.conflicts[0].path == "/role"
    assert conflict.conflicts[0].local.present is False
    assert deleted.document == {}


def test_new_nested_objects_merge_by_field_and_escape_json_pointer() -> None:
    outcome = merge_documents(
        {},
        {"a/b~c": {"left": 1}},
        {"a/b~c": {"right": 2}},
    )

    assert outcome.document == {"a/b~c": {"left": 1, "right": 2}}
    assert outcome.conflicts == ()

    conflict = merge_documents(
        {"a/b~c": {"value": 0}},
        {"a/b~c": {"value": 1}},
        {"a/b~c": {"value": 2}},
    )
    assert conflict.conflicts[0].path == "/a~1b~0c/value"


def test_arrays_are_atomic_fields() -> None:
    outcome = merge_documents({"tags": ["base"]}, {"tags": ["one"]}, {"tags": ["two"]})

    assert outcome.document is None
    assert outcome.conflicts[0].path == "/tags"


@given(
    st.dictionaries(st.text(min_size=1, max_size=8), st.integers(), max_size=8),
    st.dictionaries(st.text(min_size=1, max_size=8), st.integers(), max_size=8),
)
def test_disjoint_additions_are_commutative(
    left_source: dict[str, int], right_source: dict[str, int]
) -> None:
    left: dict[str, JsonValue] = {f"left:{key}": value for key, value in left_source.items()}
    right: dict[str, JsonValue] = {f"right:{key}": value for key, value in right_source.items()}

    forward = merge_documents({}, left, right)
    reverse = merge_documents({}, right, left)

    assert forward.document == left | right
    assert reverse.document == forward.document
    assert forward.conflicts == reverse.conflicts == ()


def test_inputs_are_not_mutated() -> None:
    base: dict[str, JsonValue] = {"nested": {"base": 1}}
    local: dict[str, JsonValue] = {"nested": {"base": 1, "local": 2}}
    remote: dict[str, JsonValue] = {"nested": {"base": 1, "remote": 3}}
    before = deepcopy((base, local, remote))

    outcome = merge_documents(base, local, remote)

    assert (base, local, remote) == before
    assert outcome.document is not None
    nested = outcome.document["nested"]
    assert isinstance(nested, dict)
    nested["after"] = 4
    assert (base, local, remote) == before
