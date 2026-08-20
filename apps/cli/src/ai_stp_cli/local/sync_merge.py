"""Deterministic field-aware three-way merge for local revision sync.

`SPEC-009` REQ-905 and REQ-906 require independent fields to merge and a
concurrent incompatible edit to remain an explicit conflict. This module is
pure: it does not move a head, write a revision or choose a winner. A caller may
seal a two-parent revision only when ``document`` is present.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from ai_stp_foundation.canonical import JsonValue


@dataclass(frozen=True)
class FieldVersion:
    """One side of a field, distinguishing JSON null from an absent key."""

    present: bool
    value: JsonValue = None


@dataclass(frozen=True)
class FieldConflict:
    """One JSON-pointer field changed incompatibly on both sides."""

    path: str
    base: FieldVersion
    local: FieldVersion
    remote: FieldVersion


@dataclass(frozen=True)
class MergeOutcome:
    """A complete merged document, or every conflict and no partial result."""

    document: dict[str, JsonValue] | None
    conflicts: tuple[FieldConflict, ...]

    @property
    def merged(self) -> bool:
        return self.document is not None


_ABSENT = FieldVersion(False)


def _version(mapping: dict[str, JsonValue], key: str) -> FieldVersion:
    if key not in mapping:
        return _ABSENT
    return FieldVersion(True, deepcopy(mapping[key]))


def _segment(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _pointer(parent: str, key: str) -> str:
    return f"{parent}/{_segment(key)}"


def _merge_field(
    base: FieldVersion,
    local: FieldVersion,
    remote: FieldVersion,
    *,
    path: str,
) -> tuple[FieldVersion, tuple[FieldConflict, ...]]:
    if local == remote:
        return local, ()
    if local == base:
        return remote, ()
    if remote == base:
        return local, ()

    base_value = base.value if base.present else {}
    if (
        local.present
        and remote.present
        and isinstance(local.value, dict)
        and isinstance(remote.value, dict)
        and isinstance(base_value, dict)
    ):
        merged, conflicts = _merge_objects(base_value, local.value, remote.value, path=path)
        if not conflicts:
            return FieldVersion(True, merged), ()
        return _ABSENT, conflicts

    return _ABSENT, (FieldConflict(path, base, local, remote),)


def _merge_objects(
    base: dict[str, JsonValue],
    local: dict[str, JsonValue],
    remote: dict[str, JsonValue],
    *,
    path: str,
) -> tuple[dict[str, JsonValue], tuple[FieldConflict, ...]]:
    merged: dict[str, JsonValue] = {}
    conflicts: list[FieldConflict] = []
    for key in sorted(set(base) | set(local) | set(remote)):
        field, found = _merge_field(
            _version(base, key),
            _version(local, key),
            _version(remote, key),
            path=_pointer(path, key),
        )
        conflicts.extend(found)
        if field.present:
            merged[key] = deepcopy(field.value)
    return merged, tuple(conflicts)


def merge_documents(
    base: dict[str, JsonValue],
    local: dict[str, JsonValue],
    remote: dict[str, JsonValue],
) -> MergeOutcome:
    """Merge three JSON objects without mutating inputs or preferring a side."""
    document, conflicts = _merge_objects(base, local, remote, path="")
    return MergeOutcome(None if conflicts else document, conflicts)
