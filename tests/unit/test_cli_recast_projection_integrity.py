"""Recast must preserve file identity before reporting a derivable member."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from typing import cast

import pytest

from ai_stp_cli.local import setup_recast
from ai_stp_cli.local.components import Rule
from ai_stp_contracts.machine_help import SetupRecastMember
from ai_stp_passports import ComponentVersionPassport, SetupVersionPassport


@pytest.fixture
def skill_rules(monkeypatch: pytest.MonkeyPatch) -> tuple[Rule, Rule]:
    source = Rule("skill", "skills", "directory", "claude-code", "test:source")
    target = Rule("skill", "skills", "directory", "grok-build", "test:target")

    def source_rule(*_args: object, **_kwargs: object) -> Rule:
        return source

    monkeypatch.setattr(setup_recast.composition, "rule_for", source_rule)
    return source, target


def test_recast_preserves_nested_siblings(skill_rules: tuple[Rule, Rule]) -> None:
    _source, target = skill_rules
    files = {
        "skills/review/SKILL.md": b"# Review\n",
        "skills/review/scripts/run.sh": b"#!/bin/sh\n",
        "skills/review/references/run.sh": b"reference, not the script\n",
    }
    assert setup_recast._remap_files(  # pyright: ignore[reportPrivateUsage]
        files, "skill", "claude-code", "global", target
    ) == files


@pytest.mark.parametrize(
    "files",
    [
        {"other/review/SKILL.md": b"foreign root"},
        {"skills/run.sh": b"first", "other/run.sh": b"second"},
        {"skills-extra/review/SKILL.md": b"prefix is not a path segment"},
        {"skills/review/A.md": b"first", "skills/review/a.md": b"case collision"},
        {"skills/": b"no member name"},
    ],
)
def test_recast_refuses_lossy_directory_mapping(
    skill_rules: tuple[Rule, Rule], files: dict[str, bytes]
) -> None:
    _source, target = skill_rules
    assert setup_recast._remap_files(  # pyright: ignore[reportPrivateUsage]
        files, "skill", "claude-code", "global", target
    ) is None


def test_recast_does_not_invent_an_unknown_source_root(
    skill_rules: tuple[Rule, Rule], monkeypatch: pytest.MonkeyPatch
) -> None:
    _source, target = skill_rules

    def no_rule(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(setup_recast.composition, "rule_for", no_rule)
    assert setup_recast._remap_files(  # pyright: ignore[reportPrivateUsage]
        {"unknown/SKILL.md": b"unknown"}, "skill", "claude-code", "global", target
    ) is None


def test_recast_uses_the_same_mapping_for_modes(skill_rules: tuple[Rule, Rule]) -> None:
    _source, target = skill_rules
    modes = {"skills/review/SKILL.md": 0o644, "skills/review/scripts/run.sh": 0o755}
    assert setup_recast._remap_files(  # pyright: ignore[reportPrivateUsage]
        modes, "skill", "claude-code", "global", target
    ) == modes


@pytest.mark.parametrize("mode", [0o400, 0o600, 0o644, 0o700, 0o755])
def test_recast_keeps_the_recorded_file_mode(mode: int) -> None:
    member = setup_recast._projection_member(  # pyright: ignore[reportPrivateUsage]
        "skills/review/scripts/run.sh", "sha256:" + "a" * 64, 10, None, mode=mode
    )
    assert member["mode"] == mode
    assert member["ownership"] == "whole"


def test_recast_blocks_a_member_whose_actual_projection_cannot_be_mapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    passport = cast(ComponentVersionPassport, SimpleNamespace(component_type="skill"))

    def held_passport(*_args: object) -> ComponentVersionPassport:
        return passport

    monkeypatch.setattr(setup_recast, "_component_passport", held_passport)

    def no_target_adaptation(*_args: object) -> None:
        raise ValueError("target adaptation is absent")

    monkeypatch.setattr(setup_recast, "adaptation_for", no_target_adaptation)

    def unavailable(*_args: object) -> None:
        return None

    def next_minor(*_args: object) -> str:
        return "1.1"

    monkeypatch.setattr(setup_recast, "_blocked_reason", unavailable)
    monkeypatch.setattr(setup_recast, "_preview_projection", unavailable, raising=False)
    monkeypatch.setattr(setup_recast.versions, "next_minor", next_minor)
    result = setup_recast._classify(  # pyright: ignore[reportPrivateUsage]
        cast(sqlite3.Connection, object()),
        "claude-code",
        "grok-build",
        ("component_01ARZ3NDEKTSV4RRFFQ69G5FAV", "1.0", "sha256:" + "a" * 64),
    )
    assert result.disposition == "blocked"
    assert result.target_version == "1.0"


def test_recast_preview_carries_source_modes_without_writing(
    skill_rules: tuple[Rule, Rule], monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = skill_rules
    scope = SimpleNamespace(
        scope="global",
        projection_artifact=SimpleNamespace(digest="sha256:" + "a" * 64),
        members=[
            SimpleNamespace(path="skills/review/SKILL.md", mode=0o644, object_type="file"),
            SimpleNamespace(path="skills/review/scripts/run.sh", mode=0o755, object_type="file"),
        ],
    )
    passport = cast(ComponentVersionPassport, SimpleNamespace(component_type="skill"))

    def permitted(*_args: object) -> None:
        return None

    def source_adaptation(*_args: object) -> SimpleNamespace:
        return SimpleNamespace(scope_adaptations=[scope])

    def rule_for(_kind: object, harness: object, **_kwargs: object) -> Rule:
        return source if harness == "claude-code" else target

    def projection_bytes(*_args: object) -> bytes:
        return b"projection"

    def projection_files(*_args: object) -> dict[str, bytes]:
        return {"skills/review/SKILL.md": b"# Review", "skills/review/scripts/run.sh": b"sh"}

    monkeypatch.setattr(setup_recast, "_blocked_reason", permitted)
    monkeypatch.setattr(setup_recast, "adaptation_for", source_adaptation)
    monkeypatch.setattr(setup_recast.composition, "rule_for", rule_for)
    monkeypatch.setattr(setup_recast, "PROVIDER_SURFACES", {("grok-build", "global"): object()})
    monkeypatch.setattr(setup_recast.content, "get", projection_bytes)
    monkeypatch.setattr(setup_recast, "_projection_files", projection_files)

    def no_writes(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("planning wrote to the content store")

    monkeypatch.setattr(setup_recast.content, "put", no_writes)
    result = setup_recast._preview_projection(  # pyright: ignore[reportPrivateUsage]
        cast(sqlite3.Connection, object()), passport, "claude-code", "grok-build"
    )
    assert result is not None
    assert result[3] == {"skills/review/SKILL.md": 0o644, "skills/review/scripts/run.sh": 0o755}


def test_recast_plan_binds_the_transform_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    source = cast(
        SetupVersionPassport,
        SimpleNamespace(
            stable_id="setup_01ARZ3NDEKTSV4RRFFQ69G5FAV", version="1.0", harness_id="claude-code"
        ),
    )
    members = (
        SetupRecastMember(
            stable_id="component_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            source_version="1.0",
            target_version="1.1",
            component_type="instruction",
            disposition="derive",
            reason="derive a native adaptation for the target harness",
        ),
    )
    setup_id = "setup_01ARZ3NDEKTSV4RRFFQ69G5FB0"
    created_at = "2026-09-06T00:00:00.000Z"
    monkeypatch.setattr(setup_recast, "TRANSFORM_VERSION", "1.0")
    previous = setup_recast._plan_view(  # pyright: ignore[reportPrivateUsage]
        source, "codex", setup_id, created_at, members
    )
    monkeypatch.setattr(setup_recast, "TRANSFORM_VERSION", "1.1")
    current = setup_recast._plan_view(  # pyright: ignore[reportPrivateUsage]
        source, "codex", setup_id, created_at, members
    )
    assert current.plan_digest != previous.plan_digest
